import typing
import os
import pickle
import tempfile
from fastapi import FastAPI, Request, Header, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, PlainTextResponse
from pathlib import Path
import argparse

import pathlib
import jinja2
import PIL
import dataclasses
import json
import pprint
import random


import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util


TMP_CONFIG_FNAME = f"web_api_config.pkl"

@dataclasses.dataclass
class ServerConfig:
    root_path: Path|None = None
    thumb_path: Path|None = None
    template_path: Path|None = None
    site_index: dict|None = None
    template: jinja2.Template|None = None
    sort_by_name: bool|None = None
    max_clip_duration: float|None = None
    #_config_file: Path = TMP_CONFIG_FNAME

    def set_values_from_args(
        self,
        #args: argparse.Namespace,
        #site_index: dict,
        root_path: Path|str,
        thumb_path: Path|str,
        template_path: Path|str,
        index_path: Path|str,
        overwrite_index: bool,
        sort_by_name: bool,
        max_clip_duration: float,
    ) -> typing.Self:
        '''Set configuration values.'''
        if root_path is None:
            raise ValueError("Root path must be provided")
        root_path = Path(root_path).resolve()  # Get absolute path

        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        self.root_path = root_path

        thumb_path = root_path / thumb_path
        thumb_path.mkdir(parents=True, exist_ok=True)
        if not thumb_path.exists():
            raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")
        self.thumb_path = thumb_path

        template_path = Path(template_path).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template path not found: {template_path}")
        self.template_path = template_path

        self.sort_by_name = bool(sort_by_name)

        index_path = root_path / index_path
        if index_path.exists() and not overwrite_index:
            print(f'reading index {index_path}')
            with index_path.open('r') as f:
                self.site_index = json.load(f)
        else:
            print(f'creating index {index_path}')
            self.site_index = create_site_index(root_path, thumb_path, sort_by_name, max_clip_duration)
            with index_path.open('w') as f:
                json.dump(self.site_index, f, indent=2)

        self.max_clip_duration = float(max_clip_duration)

        #self.save_to_file()
        return self

    #def save_to_file(self):
    #    """Save configuration to pickle file."""
    #    with open(TMP_CONFIG_FNAME, 'wb') as f:
    #        pickle.dump(dataclasses.asdict(self), f)
    #        print(f"Saved config to {TMP_CONFIG_FNAME}")

    #@classmethod
    #def load_from_file(cls) -> 'ServerConfig':
    #    """Load configuration from pickle file."""
    #    config_file = TMP_CONFIG_FNAME
    #    if not config_file.exists():
    #        raise ValueError(f"Config file not found: {config_file}")
    #    
    #    with open(config_file, 'rb') as f:
    #        config = pickle.load(f)
    #    return cls(**config)

def get_thumb_path(vid_path_rel: Path|str, thumbs_path: Path|str) -> Path:
    return thumbs_path / str(Path(vid_path_rel).with_suffix('.gif')).replace('/', '.')


def create_site_index(root: pathlib.Path, thumbs_path: Path|str, sort_by_name: bool, max_clip_duration: float) -> dict:
    '''Create the index page for the site.'''
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=(Path(thumbs_path).name,))
    #index, _ = create_page_index(mdir, root, thumbs_path=Path(thumbs_path), sort_by_name=sort_by_name, max_clip_duration=max_clip_duration)
    return create_page_index(mdir, root, thumbs_path=Path(thumbs_path), max_clip_duration=max_clip_duration)



def create_page_index(
    mdir: mediatools.MediaDir, 
    root: pathlib.Path, 
    thumbs_path: pathlib.Path,
    max_clip_duration: float,
    verbose: bool = True,
) -> None:
    
    all_vfs = mdir.all_video_files()
    elements = [(vf,root,thumbs_path, max_clip_duration) for vf in mdir.all_video_files()]
    video_infos = util.parallel_starmap(get_video_info, elements, num_processes=os.cpu_count(), use_tqdm=verbose)
    for vf,vi in zip(all_vfs, video_infos):
        vf.meta['info'] = vi

    all_imfs = mdir.all_image_files()
    elements = [(imf,root) for imf in mdir.all_image_files()]
    image_infos = util.parallel_starmap(get_image_info, elements, num_processes=os.cpu_count(), use_tqdm=verbose)
    for imf,ii in zip(all_imfs, image_infos):
        imf.meta['info'] = ii

    for mdir in mdir.all_dirs():
        mdir.meta['info'] = get_image_info(
            mdir=mdir, 
            root=root, 
        )

    exit()

    


def get_page_info(mdir: mediatools.MediaDir, root: pathlib.Path) -> dict[str,typing.Any]:
    '''Get page info dictionary. Assume image and video infos have already been populated.'''
    page_path_abs = mdir.fpath
    page_path_rel = mdir.fpath.relative_to(root)


    all_subdir_videos = mdir.all_video_files()
    all_subdir_images = mdir.all_image_files()


    all_subfolder_thumbs = list()
    for vf in all_subdir_videos:
        vi = vf.meta['info']
        if vi['thumb_exists']:
            all_subfolder_thumbs.append(vi['thumb_path_rel'])

    return {
        'page_path_abs': str(page_path_abs),
        'page_path_rel': str(page_path_rel),
        'idx': mediatools.fname_to_id(page_path_rel.name),
        'name': mediatools.fname_to_title(page_path_rel.name), 
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_file_paths()])),
        'subfolder_thumbs_all': all_subfolder_thumbs,
        'subfolder_thumb': '',#best_thumb.get_final_path(),
        'subfolder_aspect': '',#best_thumb.get_final_aspect(),
        'vids': [vf.meta['info'] for vf in mdir.videos if not vf.meta['info']['is_clip']],
        'clips': [vf.meta['info'] for vf in mdir.videos if vf.meta['info']['is_clip']],
        'images': [imf.meta['info'] for imf in mdir.images],
        'num_vids': len(all_subdir_videos) + len(all_subdir_images),
        'num_imgs': len(all_subdir_images),
        'num_subpages': len(mdir.subdirs),
    }



def get_video_info(
    vfile: mediatools.VideoFile, 
    root: pathlib.Path, 
    thumbs_path: pathlib.Path,
    max_clip_duration: float,
) -> dict[str,typing.Any]|None:
    '''Get video info dictionary and whether it's a clip.'''
    try:
        info = vfile.get_info()
    except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
        #print(f'Error: {vfile.fpath} could not be probed. Skipping.')
        return None
    else:
        vid_path_abs = vfile.fpath
        vid_path_rel = vfile.fpath.relative_to(root)
        hash_str = util.get_hash_hex_THUMB(vid_path_abs)
        thumb_path = thumbs_path / (hash_str + '.gif')
        thumb_path_rel = thumb_path.relative_to(root)

        return {
            'vid_path_abs': str(vid_path_abs),
            'vid_path_rel': str(vid_path_rel),
            'thumb_path_abs': str(thumb_path),
            'thumb_path_rel': str(thumb_path_rel),
            'thumb_exists': thumb_path.exists() and thumb_path.stat().st_size > 0,
            #'vid_web': mediatools.parse_url(vfile.fpath.name),
            #'thumb_web': mediatools.parse_url('/'+str(rel_thumb_fp)),
            'idx': info.id(),
            'vid_title': info.title(),
            'vid_size': info.size,
            'vid_size_str': info.size_str(),
            'duration': info.probe.duration,
            'duration_str': info.duration_str(),
            'res_str': info.resolution_str(),
            'aspect': info.aspect_ratio(),
            'hash': hash_str,
            'is_clip': info.probe.duration < max_clip_duration,
        }


def get_thumb_path2(vid_path_abs: Path|str, thumbs_path: Path|str) -> Path:
    return Path(thumbs_path) / Path(util.get_hash_hex(vid_path_abs, max_chunks=1000) + '.gif')



def get_image_info(ifile: mediatools.ImageFile, root: pathlib.Path) -> dict[str,typing.Any]|None:
    '''Get image info dictionary. To be used in a map function.'''
    img_path_abs = ifile.fpath
    img_path_rel = ifile.fpath.relative_to(root)
    try:
        info = ifile.get_info()
    except PIL.UnidentifiedImageError:
        #print(f'Error: {ifile.fpath} is not a valid image file.')
        return None
    else:
        return {
            #'path': mediatools.parse_url(rp.name),
            'img_path_abs': str(img_path_abs),
            'img_path_rel': str(img_path_rel),
            'title': info.title(),
            'aspect': info.aspect_ratio(),
        }



def create_page_index_old(
    mdir: mediatools.MediaDir, 
    root: pathlib.Path, 
    thumbs_path: pathlib.Path,
    sort_by_name: bool,
    max_clip_duration: float,
) -> tuple[dict[Path,dict[str,typing.Any]],dict[str,typing.Any]]:

    print(f'entering {mdir.fpath}')
    full_index = dict() # this bubbles up

    page_path_abs = mdir.fpath
    page_path_rel = mdir.fpath.relative_to(root)

    best_subpage_thumb, best_video_thumb, best_image_thumb = BestThumbTracker(), BestThumbTracker(), BestThumbTracker()
    
    subpages = list()
    for sdir in sorted(mdir.subdirs.values(), key=lambda sd: sd.fpath):
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            full_subpage_index, subpage_index = create_page_index_old(mdir=sdir, root=root, thumbs_path=thumbs_path, sort_by_name=sort_by_name, max_clip_duration=max_clip_duration)

            subpages.append(subpage_index) # give this page access to all subpages
            full_index = {**full_index, **full_subpage_index} # add these subpages to the full index
            
            best_subpage_thumb.update(
                new_path=subpage_index['subfolder_thumb'],
                new_aspect=subpage_index['subfolder_aspect'],
            )

    clips = list()
    vids = list()
    for vfile in mdir.videos:
        vid_path_abs = vfile.fpath
        vid_path_rel = vfile.fpath.relative_to(root)
        thumb_path = thumbs_path / str(vid_path_rel.with_suffix('.gif')).replace('/', '.')
        thumb_path_rel = thumb_path.relative_to(root)

        try:
            info = vfile.get_info()
        except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
            print(f'Error: {vfile.fpath} could not be probed. Skipping.')
            continue
        else:
            info_dict = {
                'vid_path_abs': str(vid_path_abs),
                'vid_path_rel': str(vid_path_rel),
                'thumb_path_abs': str(thumb_path),
                'thumb_path_rel': str(thumb_path_rel),
                #'vid_web': mediatools.parse_url(vfile.fpath.name),
                #'thumb_web': mediatools.parse_url('/'+str(rel_thumb_fp)),
                'idx': info.id(),
                'vid_title': info.title(),
                'vid_size': info.size,
                'vid_size_str': info.size_str(),
                'duration': info.probe.duration,
                'duration_str': info.duration_str(),
                'res_str': info.resolution_str(),
                'aspect': info.aspect_ratio(),
            }
            if info.probe.duration < max_clip_duration:
                clips.append(info_dict)
            else:
                vids.append(info_dict)

            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                best_video_thumb.update(
                    new_path=str(thumb_path_rel),
                    new_aspect=info.aspect_ratio(),
                )
    
    images = list()
    for ifile in mdir.images:
        #rp = ifile.fpath.relative_to(root)
        img_path_abs = ifile.fpath
        img_path_rel = ifile.fpath.relative_to(root)
        try:
            info = ifile.get_info()
        except PIL.UnidentifiedImageError:
            print(f'Error: {ifile.fpath} is not a valid image file.')
            continue
        else:
            images.append({
                #'path': mediatools.parse_url(rp.name),
                'img_path_abs': str(img_path_abs),
                'img_path_rel': str(img_path_rel),
                'title': info.title(),
                'aspect': info.aspect_ratio(),
            })
            #if best_thumb is None or info.aspect_ratio() > best_aspect:
            #    best_aspect = info.aspect_ratio()
            #    best_thumb = f'/{mediatools.parse_url(str(rp))}'#ifile.fpath.with_suffix('.gif')
            if img_path_abs.exists() and img_path_abs.stat().st_size > 0:
                best_image_thumb.update(
                    new_path=img_path_rel,
                    new_aspect=info.aspect_ratio(),
                )

    if sort_by_name:
        vids = sorted(vids, key=lambda v: v['vid_path_rel'])
        clips = sorted(clips, key=lambda c: c['vid_path_rel'])
        images = sorted(images, key=lambda i: i['img_path_rel'])
    else:
        vids = sorted(vids, key=lambda v: v['aspect'])
        clips = sorted(clips, key=lambda c: c['aspect'])
        images = sorted(images, key=lambda i: i['aspect'])


    if best_subpage_thumb.has_value():
        best_thumb = best_subpage_thumb
    elif best_video_thumb.has_value():
        best_thumb = best_video_thumb
    elif best_image_thumb.has_value():
        best_thumb = best_image_thumb
    else:
        best_thumb = BestThumbTracker()
        best_thumb.update(new_path='', new_aspect=1.0)

    page_index = {
        'page_path_abs': str(page_path_abs),
        'page_path_rel': str(page_path_rel),
        'idx': mediatools.fname_to_id(page_path_rel.name),
        'name': mediatools.fname_to_title(page_path_rel.name), 
        'subfolder_thumb': best_thumb.get_final_path(),
        'subfolder_aspect': best_thumb.get_final_aspect(),
        'subfolder_thumbs_all': best_thumb.thumbs_list(),
        'subpages': subpages,
        'vids': vids,
        'clips': clips,
        'images': images,
        'num_vids': len(vids) + len(clips),
        'num_imgs': len(images),
        'num_subpages': len(subpages),
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_file_paths()])),
    }

    full_index[str(page_path_rel)] = page_index

    #pprint.pprint(full_index)
    #print(json.dumps(full_index, indent=2))
    #print('\n\n\n\n\n')

    return full_index, page_index


@dataclasses.dataclass
class BestThumbTracker:
    desired_aspect: float = 0
    path: pathlib.Path|None = None
    aspect: float|None = None
    all_vids: list = dataclasses.field(default_factory=list)

    def update(self, new_path: pathlib.Path, new_aspect: float):
        '''Update the best thumb if the new one is better.'''
        if new_path is None or new_aspect is None:
            return
        self.all_vids.append((new_path, new_aspect))
        if self.path is None or new_path == '' or new_aspect > self.aspect:
            self.path = pathlib.Path(new_path)
            self.aspect = new_aspect
    
    def update_from_other(self, other: 'BestThumbTracker'):
        '''Update from another BestThumbTracker.'''
        return self.update(new_path=other.path, new_aspect=other.aspect)
    
    def get_final_path(self) -> str:
        '''Get the path as a string.'''
        return str(self.path) if self.path is not None else ''

    def get_final_aspect(self) -> float:
        '''Get the aspect ratio.'''
        return self.aspect if self.aspect is not None else 1.0
    
    def has_value(self) -> bool:
        return self.path is not None

    def thumbs_list(self) -> list[str]:
        return [str(p) for p, _ in self.all_vids]




from fastapi import Depends

def create_app(config: ServerConfig) -> FastAPI:
    """Create a new FastAPI application with the given configuration."""
    app = FastAPI()
    
    # Store config in app state
    app.state.config = config
    
    async def get_config() -> ServerConfig:
        """
        Dependency that provides the server configuration.
        """
        return app.state.config

    CHUNK_SIZE = 1024 * 1024 * 1 # 2 MB

    @app.on_event("startup")
    async def startup_event():
        print("\nAvailable routes:")
        for route in app.routes:
            print(f"  {route.methods} {route.path}")
        print()

    @app.get("/")
    async def root():
        return RedirectResponse(url='/page/')
    
    @app.get("/test")
    async def test():
        return {"message": "Hello World"}

    @app.get('/page')
    async def page_redirect():
        return RedirectResponse(url='/page/')

    @app.get('/list_directories', response_class=PlainTextResponse)
    async def list_pages(config: ServerConfig = Depends(get_config)):
        return "\n".join(config.site_index.keys())

    @app.get('/list_videos', response_class=PlainTextResponse)
    async def list_pages(config: ServerConfig = Depends(get_config)):
        vid_names = []
        for pi in config.site_index.values():
            for v in pi['vids']:
                vid_names.append(v['vid_path_rel'])
        return "\n".join(vid_names)


    @app.get('/page/{page_path:path}', response_class=HTMLResponse)
    async def page_with_video(page_path: str, config: ServerConfig = Depends(get_config)):
        if page_path == '':
            page_path = '.'

        try:
            page_data = config.site_index[page_path]
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_path}")
        
        with config.template_path.open('r') as f:
            template = f.read()
        environment = jinja2.Environment()
        template = environment.from_string(template)

        return template.render(**page_data)

    @app.get("/file/{file_path:path}")
    async def file_endpoint(file_path: Path|str, config: ServerConfig = Depends(get_config)):
        file_path = Path(config.root_path) / file_path
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return Response(content="File not found", status_code=404)
        return FileResponse(file_path)

    @app.get("/video/{video_path:path}")
    async def video_endpoint(
        video_path: str, 
        range: str = Header(None),
        config: ServerConfig = Depends(get_config)
    ):
        # Construct full path and validate
        full_path = config.root_path / video_path
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"Video not found: {video_path}")
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {video_path}")
        
        file_size = full_path.stat().st_size
        if range:
            start_str, end_str = range.replace("bytes=", "").split("-")
            start = int(start_str)
            end = int(end_str) if end_str else min(start + CHUNK_SIZE, file_size - 1)
        else:
            # Serve from start if no range header
            start = 0
            end = min(CHUNK_SIZE, file_size - 1)

        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": "video/mp4",
            "Cache-Control": "public, max-age=31536000",
            "Connection": "keep-alive",
        }
        with open(full_path, "rb") as f:
            f.seek(start)
            data = f.read(content_length)
        response = Response(
            content=data, 
            status_code=206 if range else 200, 
            headers=headers, 
            media_type="video/mp4"
        )
        return response

    return app





if __name__ == "__main__":
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('root_path', type=Path, help='Root directory containing video files')
    parser.add_argument('template', type=Path, help='Path to the HTML template file.')
    parser.add_argument('--port', type=int, default=8000, help='Port to run the server on (default: 8000)')
    parser.add_argument('-t', '--thumbs', type=Path, default=Path("_thumbs"), help='Directory for thumbnail images (default: _thumbs)')
    parser.add_argument('-s', '--sort_by_name', action='store_true', help='Rebuild the site index even if a cached version exists')
    parser.add_argument('-i', '--index', type=Path, default=Path("_site_index.json"), help='Path to the site index file (default: site_index.json)')
    parser.add_argument('-w', '--overwrite_index', action='store_true', help='Overwrite the site index file if it exists')
    parser.add_argument('-m', '--max_clip_duration', type=float, default=0, help='Maximum clip duration in seconds (default: 60)')

    print(f'creating index')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        # Create a new config instance
        config = ServerConfig()
        config.set_values_from_args(
            root_path=args.root_path,
            thumb_path=args.thumbs,
            template_path=args.template,
            index_path=args.index,
            overwrite_index=args.overwrite_index,
            sort_by_name=args.sort_by_name,
            max_clip_duration=args.max_clip_duration,
        )
        
        # Create the FastAPI application with this config
        app = create_app(config)
        
        print(f"\nStarting server: {config.root_path}")
        print(f"Server will be available at: http://0.0.0.0:{args.port}")
        print("Visit http://0.0.0.0:{args.port}/page to see available videos")
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=args.port,
        )
