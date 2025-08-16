import typing
from fastapi import FastAPI, Request, Header, Response
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
        root_path = Path(args.root_path)

        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        self.root_path = root_path
        return self

app = FastAPI()
config = ServerConfig()

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
    return '''
    <html>
        <head>
            <title>Video Player</title>
        </head>
        <body>
            <img src="/thumb" alt="Video thumbnail" style="max-width: 100%; height: auto;"><br>
            <video src="/video" controls style="max-width: 100%; height: auto;">
                Your browser does not support the video tag.
            </video>
        </body>
    </html>
    '''

@app.get("/thumb")
async def thumbnail():
    if not config.thumb_path or not config.thumb_path.exists():
        return Response(content="Thumbnail not found", status_code=404)
    return FileResponse(config.thumb_path, media_type="image/jpeg")


@app.get("/video")
async def video_endpoint(range: str = Header(None)):
    file_size = config.video_path.stat().st_size
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
    with open(config.video_path, "rb") as f:
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
    parser.add_argument('root_path', type=str, help='Path to the video file to serve')
    parser.add_argument('--port', type=int, default=8001, help='Port to run the server on (default: 8001)')
    
    args = parser.parse_args()
    config.set_values_from_args(args)
    
    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{args.port}")
    
    
    uvicorn.run(app, host="0.0.0.0", port=args.port, reload=True)

