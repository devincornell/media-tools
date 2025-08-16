import typing
import os
import pickle
import tempfile
from fastapi import FastAPI, Request, Header, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import argparse
from dataclasses import dataclass

import pathlib
import jinja2
import PIL
import dataclasses
import json
import pprint
import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools


TMP_CONFIG_FNAME = Path(tempfile.gettempdir()) / "cocksucker.pkl"

@dataclass
class ServerConfig:
    root_path: Path|None = None
    thumb_path: Path|None = None
    template_path: Path|None = None
    site_index: dict|None = None
    template: jinja2.Template|None = None
    sort_by_name: bool|None = None
    #_config_file: Path = TMP_CONFIG_FNAME

    def set_values_from_args(
        self,
        args: argparse.Namespace,
        #site_index: dict,
    ) -> typing.Self:
        '''Set configuration values from args.'''
        if args.root_path is None:
            raise ValueError("Root path must be provided")
        root_path = Path(args.root_path).resolve()  # Get absolute path

        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        self.root_path = root_path

        thumb_path = (Path(args.root_path) / args.thumbs).resolve()
        thumb_path.mkdir(parents=True, exist_ok=True)
        if not thumb_path.exists():
            raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")
        self.thumb_path = thumb_path

        template_path = Path(args.template).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template path not found: {template_path}")
        self.template_path = template_path

        self.sort_by_name = bool(args.sort_by_name)

        print(f'creating index')
        self.site_index = create_site_index(root_path, thumb_path)
        
        #print(f'reading template {template_path}')
        #with template_path.open('r') as f:
        #    template_html = f.read()
        #self.template = template_html
        
        self.save_to_file()
        return self

    def save_to_file(self):
        """Save configuration to pickle file."""
        with open(TMP_CONFIG_FNAME, 'wb') as f:
            pickle.dump(dataclasses.asdict(self), f)
            print(f"Saved config to {TMP_CONFIG_FNAME}")

    @classmethod
    def load_from_file(cls) -> 'ServerConfig':
        """Load configuration from pickle file."""
        config_file = TMP_CONFIG_FNAME
        if not config_file.exists():
            raise ValueError(f"Config file not found: {config_file}")
        
        with open(config_file, 'rb') as f:
            config = pickle.load(f)
        return cls(**config)







def create_site_index(root: pathlib.Path, thumbs_path: Path|str):
    '''Create the index page for the site.'''
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=(thumbs_path,))
    index, _ = create_page_index(mdir, root, thumbs_path=Path(thumbs_path))
    return index

def create_page_index(mdir: mediatools.MediaDir, root: pathlib.Path, thumbs_path: pathlib.Path) -> tuple[dict[Path,dict[str,typing.Any]],dict[str,typing.Any]]:

    print(f'entering {mdir.fpath}')
    full_index = dict() # this bubbles up

    page_path_abs = mdir.fpath
    page_path_rel = mdir.fpath.relative_to(root)

    best_subpage_thumb, best_video_thumb, best_image_thumb = BestThumbTracker(), BestThumbTracker(), BestThumbTracker()
    
    subpages = list()
    for sdir in sorted(mdir.subdirs, key=lambda sd: sd.fpath):
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            full_subpage_index, subpage_index = create_page_index(mdir=sdir, root=root, thumbs_path=thumbs_path)
            
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
            if info.probe.duration < 60:
                clips.append(info_dict)
            else:
                vids.append(info_dict)

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
            best_image_thumb.update(
                new_path=img_path_rel,
                new_aspect=info.aspect_ratio(),
            )

    if best_subpage_thumb.has_value():
        best_thumb = best_subpage_thumb
    elif best_video_thumb.has_value():
        best_thumb = best_video_thumb
    elif best_image_thumb.has_value():
        best_thumb = best_image_thumb

    page_index = {
        'page_path_abs': str(page_path_abs),
        'page_path_rel': str(page_path_rel),
        'idx': mediatools.fname_to_id(page_path_rel.name),
        'name': mediatools.fname_to_title(page_path_rel.name), 
        'subfolder_thumb': best_thumb.get_final_path(),
        'subfolder_aspect': best_thumb.get_final_aspect(),
        'subpages': subpages,
        'vids': vids,
        'clips': clips,
        'images': images,
        'num_vids': len(vids) + len(clips),
        'num_imgs': len(images),
        'num_subpages': len(subpages),
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_files()])),
    }

    full_index[str(page_path_rel)] = page_index

    #pprint.pprint(full_index)
    print(json.dumps(full_index, indent=2))
    print('\n\n\n\n\n')

    return full_index, page_index


@dataclasses.dataclass
class BestThumbTracker:
    desired_aspect: float = 0
    path: pathlib.Path|None = None
    aspect: float|None = None

    def update(self, new_path: pathlib.Path, new_aspect: float):
        '''Update the best thumb if the new one is better.'''
        if new_path is None or new_aspect is None:
            return
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




app = FastAPI()

# Try to load config from pickle file, or start with empty config
try:
    #raise ValueError("Config file not found")
    config = ServerConfig.load_from_file()
    print(f"Loaded config: root_path={config.root_path}, thumb_path={config.thumb_path}")
except (ValueError, FileNotFoundError, pickle.UnpicklingError) as e:
    config = ServerConfig()
    print(f"Starting with empty config (will be set from command line): {e}")


CHUNK_SIZE = 1024 * 1024  # 1 MB

@app.on_event("startup")
async def startup_event():
    print("\nAvailable routes:")
    for route in app.routes:
        print(f"  {route.methods} {route.path}")
    print()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get('/page', response_class=HTMLResponse)
async def page():
    print(f"Current config in /page route: {config}")
    # Get list of video files
    video_files = []
    for ext in ['.mp4', '.mkv', '.avi', '.mov']:
        video_files.extend(config.root_path.glob(f'**/*{ext}'))
    
    # Create relative paths for videos
    video_links = [str(f.relative_to(config.root_path)) for f in video_files]
    
    video_list_html = '\n'.join([
        f'<li><a href="/page/{video}">{video}</a></li>'
        for video in video_links
    ])
    
    return f'''
    <html>
        <head>
            <title>Video Player</title>
        </head>
        <body>
            <h1>Available Videos</h1>
            <ul>
                {video_list_html}
            </ul>
        </body>
    </html>
    '''

@app.get('/page/{page_path:path}', response_class=HTMLResponse)
async def page_with_video(page_path: str):
    #print('index_keys: ', config.site_index.keys())
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
async def file_endpoint(file_path: Path|str):
    file_path = Path(config.root_path) / file_path
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return Response(content="File not found", status_code=404)
    return FileResponse(file_path)


@app.get("/video/{video_path:path}")
async def video_endpoint(video_path: str, range: str = Header(None)):
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





if __name__ == "__main__":
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('root_path', type=Path, help='Root directory containing video files')
    parser.add_argument('template', type=Path, help='Path to the HTML template file (default: template.html)')
    parser.add_argument('--port', type=int, default=8001, help='Port to run the server on (default: 8001)')
    parser.add_argument('--thumbs', type=Path, default=Path("_thumbs"), help='Directory for thumbnail images (default: _thumbs)')
    parser.add_argument('-s', '--sort_by_name', action='store_true', help='Rebuild the site index even if a cached version exists')

    args = parser.parse_args()
    config.set_values_from_args(
        args = args,
    )
    
    #print(json.dumps(config.site_index, indent=2))
    #exit()
    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{args.port}")
    print("Visit http://0.0.0.0:8001/page to see available videos")
    
    #TMP_CONFIG_FNAME.unlink(missing_ok=True)
    uvicorn.run(
        "server_v2:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        reload_dirs=["."],  # Watch current directory for changes
    )
