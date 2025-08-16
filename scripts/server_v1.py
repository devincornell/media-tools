import typing
import os
from fastapi import FastAPI, Request, Header, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import argparse
from dataclasses import dataclass

@dataclass
class ServerConfig:
    root_path: Path|None = None

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

        # Store the path in an environment variable
        os.environ['VIDEO_SERVER_ROOT_PATH'] = str(root_path)
        self.root_path = root_path
        return self
    
    @classmethod
    def load_from_env(cls) -> 'ServerConfig':
        """Load configuration from environment variables."""
        root_path = os.environ.get('VIDEO_SERVER_ROOT_PATH')
        if not root_path:
            raise ValueError("VIDEO_SERVER_ROOT_PATH environment variable not set")
        return cls(root_path=Path(root_path))

# Initialize the config from environment if available
app = FastAPI()
try:
    config = ServerConfig.load_from_env()
    print(f"Loaded config from environment: {config.root_path}")
except ValueError:
    config = ServerConfig()
    print("Starting with empty config (will be set from command line)")

# Add CORS middleware
#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=["*"],
#    allow_credentials=True,
#    allow_methods=["*"],
#    allow_headers=["*"],
#)

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

#@app.get("/thumb")
#async def thumbnail():
#    if not config.thumb_path or not config.thumb_path.exists():
#        return Response(content="Thumbnail not found", status_code=404)
#    return FileResponse(config.thumb_path, media_type="image/jpeg")


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

def run_server(root_path: str, port: int = 8001):
    """Configure and run the server with the given parameters."""
    # Set up initial configuration
    config.set_values_from_args(argparse.Namespace(root_path=root_path))
    
    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{port}")
    print("Visit http://0.0.0.0:8001/page to see available videos")
    
    import uvicorn
    uvicorn.run(
        "server_v1:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["."],  # Watch current directory for changes
    )

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('root_path', type=str, help='Root directory containing video files')
    parser.add_argument('--port', type=int, default=8001, help='Port to run the server on (default: 8001)')
    
    args = parser.parse_args()
    run_server(args.root_path, args.port)

