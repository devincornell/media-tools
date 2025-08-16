from fastapi import FastAPI, Request, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path

app = FastAPI()

# Define paths
thumb_path = Path("_thumbs/my_thumb_50.jpg")  # Adjust this path to your thumbnail

# Add CORS middleware
#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=["*"],
#    allow_credentials=True,
#    allow_methods=["*"],
#    allow_headers=["*"],
#)

video_path = Path("my_montage2.mp4")
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
    if not thumb_path.exists():
        return Response(content="Thumbnail not found", status_code=404)
    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/video")
async def video_endpoint(range: str = Header(None)):
    file_size = video_path.stat().st_size
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
    with open(video_path, "rb") as f:
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)

