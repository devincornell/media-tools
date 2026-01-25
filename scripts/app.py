import fastapi
import pydantic
import typing
import dataclasses
import jinja2
from pathlib import Path

from ..src.mediatools.mediadir import MediaDir


@dataclasses.dataclass
class ServerConfig:
    root_path: Path|None = None
    thumb_path: Path|None = None
    template_path: Path|None = None
    template: jinja2.Template|None = None
    sort_by_name: bool|None = None
    max_clip_duration: float|None = None
    index_path: Path|None = None



def create_app(config: ServerConfig) -> fastapi.FastAPI:
    app = fastapi.FastAPI()

    # Maintains configuration
    app.state.config = config
    async def get_config() -> ServerConfig:
        return app.state.config

    @app.get('/update', response_class=fastapi.responses.PlainTextResponse)
    async def list_pages(config: ServerConfig = fastapi.Depends(get_config)):
        msg = config.update_index()
        return f'Updated successfully!\n\nChanges:\n{msg}'

    @app.get('/list_directories', response_class=fastapi.responses.PlainTextResponse)
    async def list_pages(config: ServerConfig = fastapi.Depends(get_config)):
        return "\n".join([str(d.path) for d in config.site_index.all_dirs()])

    @app.get('/list_videos', response_class=fastapi.responses.PlainTextResponse)
    async def list_videos(config: ServerConfig = fastapi.Depends(get_config)):
        return "\n".join([vf.meta['info']['vid_path_rel'] for vf in config.site_index.all_videos() if vf.meta['info'] is not None])

    @app.get('/page/{page_path:path}', response_class=fastapi.responses.HTMLResponse)
    async def page_with_video(page_path: str, config: ServerConfig = fastapi.Depends(get_config)):
        if page_path == '':
            page_path = '.'

        try:
            page_data = config.get_template_vars(page_path)
        except FileNotFoundError:
            raise fastapi.HTTPException(status_code=404, detail=f"Page not found: {page_path}")
        
        #tmp = page_data.copy()
        #del tmp['subfolder_thumbs_all']
        #print(json.dumps(tmp, indent=2))
        print(f'rendering template {config.template_path}')
        with config.template_path.open('r') as f:
            template = f.read()
        environment = jinja2.Environment()
        template = environment.from_string(template)

        return template.render(**page_data)

    @app.get("/file/{file_path:path}")
    async def file_endpoint(file_path: Path|str, config: ServerConfig = fastapi.Depends(get_config)):
        file_path = Path(config.root_path) / file_path
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return fastapi.Response(content="File not found", status_code=404)
        return fastapi.responses.FileResponse(file_path)

    @app.get("/video/{video_path:path}")
    async def video_endpoint(
        video_path: str, 
        range: str = fastapi.Header(None),
        chunk_size: int = 1*1024*1024,
        config: ServerConfig = fastapi.Depends(get_config)
    ):
        # Construct full path and validate
        full_path = config.root_path / video_path
        if not full_path.exists():
            raise fastapi.HTTPException(status_code=404, detail=f"Video not found: {video_path}")
        if not full_path.is_file():
            raise fastapi.HTTPException(status_code=400, detail=f"Not a file: {video_path}")
        
        file_size = full_path.stat().st_size
        if range:
            start_str, end_str = range.replace("bytes=", "").split("-")
            start = int(start_str)
            end = int(end_str) if end_str else min(start + chunk_size, file_size - 1)
        else:
            # Serve from start if no range header
            start = 0
            end = min(chunk_size, file_size - 1)
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
        response = fastapi.responses.Response(
            content=data, 
            status_code=206 if range else 200, 
            headers=headers, 
            media_type="video/mp4"
        )
        return response

    return app
