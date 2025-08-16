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

@dataclass
class ServerConfig:
    root_path: Path|None = None
    thumb_path: Path|None = None
    _config_file: Path = Path(tempfile.gettempdir()) / "video_server_config.pkl"

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

        if args.thumbs:
            thumb_path = Path(args.thumbs).resolve()
            if not thumb_path.exists():
                raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")
            self.thumb_path = thumb_path

        # Save config to pickle file
        self.save_to_file()
        return self

    def save_to_file(self):
        """Save configuration to pickle file."""
        with open(self._config_file, 'wb') as f:
            # Convert Paths to strings for pickling
            config_dict = {
                'root_path': str(self.root_path) if self.root_path else None,
                'thumb_path': str(self.thumb_path) if self.thumb_path else None
            }
            pickle.dump(config_dict, f)
            print(f"Saved config to {self._config_file}")

    @classmethod
    def load_from_file(cls) -> 'ServerConfig':
        """Load configuration from pickle file."""
        config_file = Path(tempfile.gettempdir()) / "video_server_config.pkl"
        if not config_file.exists():
            raise ValueError(f"Config file not found: {config_file}")
        
        with open(config_file, 'rb') as f:
            config_dict = pickle.load(f)
            print(f"Loaded config from {config_file}")
            return cls(
                root_path=Path(config_dict['root_path']) if config_dict['root_path'] else None,
                thumb_path=Path(config_dict['thumb_path']) if config_dict['thumb_path'] else None
            )
        return cls(
            root_path=Path(root_path),
            thumb_path=Path(thumb_path) if thumb_path else None
        )

app = FastAPI()

# Try to load config from pickle file, or start with empty config
try:
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

@app.get("/thumb")
async def thumbnail():
    if not config.thumb_path or not config.thumb_path.exists():
        return Response(content="Thumbnail not found", status_code=404)
    return FileResponse(config.thumb_path, media_type="image/jpeg")


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
    parser.add_argument('root_path', type=str, help='Root directory containing video files')
    parser.add_argument('--port', type=int, default=8001, help='Port to run the server on (default: 8001)')
    parser.add_argument('--thumbs', type=Path, default=Path("_thumbs"), help='Directory for thumbnail images (default: _thumbs)')

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
