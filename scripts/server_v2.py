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

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools

@dataclass
class ServerConfig:
    root_path: Path|None = None
    thumb_path: Path|None = None
    template_path: Path|None = None
    _config_file: Path = Path(tempfile.gettempdir()) / "video_server_config3.pkl"

    def set_values_from_args(
        self,
        args: argparse.Namespace,
    ) -> typing.Self:
        '''Set configuration values from args.'''
        if args.root_path is None:
            raise ValueError("Root path must be provided")
        root_path = Path(args.root_path).resolve()  # Get absolute path

        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        self.root_path = root_path

        thumb_path = (Path(args.root_path) / args.thumbs).resolve()
        if not thumb_path.exists():
            raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")
        self.thumb_path = thumb_path

        template_path = (Path(args.root_path) / args.template).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template path not found: {template_path}")
        self.template_path = template_path

        self.save_to_file()
        return self

    def save_to_file(self):
        """Save configuration to pickle file."""
        with open(self._config_file, 'wb') as f:
            # Convert Paths to strings for pickling
            #config_dict = {
            #    'root_path': str(self.root_path) if self.root_path else None,
            #    'thumb_root_path': str(self.thumb_root_path) if self.thumb_root_path else None
            #}
            pickle.dump(self, f)
            print(f"Saved config to {self._config_file}")

    @classmethod
    def load_from_file(cls) -> 'ServerConfig':
        """Load configuration from pickle file."""
        config_file = Path(tempfile.gettempdir()) / "video_server_config.pkl"
        if not config_file.exists():
            raise ValueError(f"Config file not found: {config_file}")
        
        with open(config_file, 'rb') as f:
            config = pickle.load(f)
            #print(config)
            #print(f"Loaded config from {config_file}")
            #return cls(
            #    root_path=Path(config_dict['root_path']) if config_dict['root_path'] else None,
            #    thumb_root_path=Path(config_dict['thumb_root_path']) if config_dict['thumb_root_path'] else None
            #)
        return cls(**config)



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

@app.get('/page/{video_path:path}', response_class=HTMLResponse)
async def page_with_video(video_path: str):
    return f'''
    <html>
        <head>
            <title>Video Player - {video_path}</title>
        </head>
        <body>
            <h1>{video_path}</h1>
            <video src="/video/{video_path}" controls style="max-width: 100%; height: auto;">
                Your browser does not support the video tag.
            </video>
            <p><a href="/page">Back to video list</a></p>
        </body>
    </html>
    '''

@app.get("/thumb/{video_path:path}")
async def thumbnail(video_path: str):
    thumb_path = config.thumb_path / video_path
    if not thumb_path.exists():
        print(f"Thumbnail not found: {thumb_path}")
        return Response(content="Thumbnail not found", status_code=404)
    return FileResponse(thumb_path, media_type="image/gif")


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





def make_site(root: pathlib.Path, template_path: pathlib.Path, thumb_folder: str = '_thumbs', page_name: str = 'web3.html'):
    '''Make the site from the root directory and template.'''
    pathlib.Path(thumb_folder).mkdir(exist_ok=True)
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=(thumb_folder,))
    
    print(f'reading template {template_path}')
    template_path = pathlib.Path(template_path)
    with template_path.open('r') as f:
        template_html = f.read()
    environment = jinja2.Environment()
    template = environment.from_string(template_html)

    make_pages(root, mdir, template, thumbs_path=root / thumb_folder, page_name=page_name)

def make_pages(root: pathlib.Path, mdir: mediatools.MediaDir, template: jinja2.Template, thumbs_path: pathlib.Path, page_name: str):
    '''Make pages for the media directory and its subdirectories.'''
    rel_path = mdir.fpath.relative_to(root)

    best_subpage_thumb, best_local_thumb = BestThumbTracker(), BestThumbTracker()
    
    child_paths = list()
    for sdir in sorted(mdir.subdirs, key=lambda sd: sd.fpath):
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            subpage_data = make_pages(root=root, mdir=sdir, template=template, thumbs_path=thumbs_path, page_name=page_name)
            child_paths.append(subpage_data)

            best_subpage_thumb.update(
                new_path=subpage_data['subfolder_thumb'],
                new_aspect=subpage_data['subfolder_aspect'],
            )

    clips = list()
    vids = list()
    for vfile in mdir.videos:
        rp = vfile.fpath.relative_to(root)
        thumb_fp = thumbs_path / str(rp.with_suffix('.gif')).replace('/', '.')
        rel_thumb_fp = thumb_fp.relative_to(root)

        try:
            info = vfile.get_info()
        except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
            print(f'Error: {vfile.fpath} could not be probed. Skipping.')
            continue
        else:
            info_dict = {
                'vid_web': mediatools.parse_url(vfile.fpath.name),
                'vid_title': info.title(),
                'thumb_web': mediatools.parse_url('/'+str(rel_thumb_fp)),
                'vid_size': info.size,
                'vid_size_str': info.size_str(),
                'duration': info.probe.duration,
                'duration_str': info.duration_str(),
                'res_str': info.resolution_str(),
                'aspect': info.aspect_ratio(),
                'idx': info.id(),
            }
            if info.probe.duration < 60:
                clips.append(info_dict)
            else:
                vids.append(info_dict)

            best_local_thumb.update(
                new_path=mediatools.parse_url('/'+str(rel_thumb_fp)),
                new_aspect=info.aspect_ratio(),
            )

            # select a good thumb
            #if best_aspect is None or info.aspect_ratio() > best_aspect:
            #    best_aspect = info.aspect_ratio()
            #    best_thumb =  mediatools.parse_url('/'+str(rel_thumb_fp))#str(rel_thumb_fp.with_suffix('.gif')).replace('/', '.')

            if not thumb_fp.is_file():
                try:
                    #mediatools.ffmpeg.make_thumb(vfile.fpath, thumb_fp, width=400)
                    import random
                    random.seed(0)
                    rnum = random.uniform(-0.2, 0.2)
                    print(f'Creating thumb {thumb_fp}')
                    mediatools.ffmpeg.make_animated_thumb_v2(vfile.fpath, thumb_fp, framerate=2+rnum, sample_period=120, width=400)
                    #vfile.ffmpeg.make_thumb(str(thumb_fp), width=400)
                except mediatools.ffmpeg.FFMPEGExecutionError as e:
                    print(f'FFMPEG ERROR: \n{e.stderr}\n\n')
            

    images = list()
    for ifile in mdir.images:
        rp = ifile.fpath.relative_to(root)
        try:
            info = ifile.get_info()
        except PIL.UnidentifiedImageError:
            print(f'Error: {ifile.fpath} is not a valid image file.')
            continue
        else:
            images.append({
                'path': mediatools.parse_url(rp.name),
                'title': info.title(),
                'aspect': info.aspect_ratio(),
            })
            #if best_thumb is None or info.aspect_ratio() > best_aspect:
            #    best_aspect = info.aspect_ratio()
            #    best_thumb = f'/{mediatools.parse_url(str(rp))}'#ifile.fpath.with_suffix('.gif')
            best_local_thumb.update(
                new_path=f'/{mediatools.parse_url(str(rp))}',
                new_aspect=info.aspect_ratio(),
            )


    html_str = template.render(
        vids = list(sorted(vids, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        #vids = list(sorted(vids, key=lambda vi: vi['vid_title'])),
        clips = list(sorted(clips, key=lambda vi: (-vi['aspect'], -vi['duration']))),
        imgs = list(sorted(images, key=lambda i: -i['aspect'])),
        #child_paths = list(sorted(child_paths, key=lambda i: -i['subfolder_aspect'])), 
        child_paths = list(sorted(child_paths, key=lambda i: i['path_rel'])), 
        page_name = page_name,
    )

    #with (mdir.fpath / page_name).open('w') as f:
    #    f.write(html_str)
    #print('wrote', mdir.fpath / page_name)

    best_local_thumb.update_from_other(best_subpage_thumb)
    
    return {
        'path': f'/{str(rel_path)}/{page_name}', 
        'path_rel': f'{str(rel_path)}/{page_name}',
        'name': mediatools.fname_to_title(rel_path.name), 
        'subfolder_thumb': best_local_thumb.get_final_path(),
        'subfolder_aspect': best_local_thumb.get_final_aspect(),
        'num_vids': len(vids),
        'num_imgs': len(images),
        'num_subfolders': len(child_paths),
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdir.all_files()])),
        'idx': mediatools.fname_to_id(mdir.fpath.name),
    }

@dataclasses.dataclass
class BestThumbTracker:
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









if __name__ == "__main__":
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('root_path', type=str, help='Root directory containing video files')
    parser.add_argument('--port', type=int, default=8001, help='Port to run the server on (default: 8001)')
    parser.add_argument('--thumbs', type=Path, default=Path("_thumbs"), help='Directory for thumbnail images (default: _thumbs)')
    parser.add_argument('--template', type=Path, default=Path("template.html"), help='Path to the HTML template file (default: template.html)')

    args = parser.parse_args()
    config.set_values_from_args(args)
    
    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{args.port}")
    print("Visit http://0.0.0.0:8001/page to see available videos")
    
    uvicorn.run(
        "server_v2:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        reload_dirs=["."],  # Watch current directory for changes
    )
