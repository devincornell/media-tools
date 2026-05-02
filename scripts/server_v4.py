from __future__ import annotations
import typing
import datetime
import dataclasses
from contextlib import asynccontextmanager
from pathlib import Path
import pathlib

from fastapi import FastAPI, Header, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, PlainTextResponse
import jinja2
import pymongo
import pydantic_settings

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
from mediatools.index_db import MediaIndexDB, MediaDirIndexDoc, VideoIndexDoc, MediaDirIndexNotFoundError
from mediatools.index_db.mediadir_index_collection import IndexVideoFile, IndexImageFile


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    site_root_path: Path
    site_template_path: Path
    site_thumb_path: Path
    site_mongodb_url: str
    site_database_name: str
    site_port: int
    site_sort_by_name: bool = False
    site_max_clip_duration: float = 0.0


@dataclasses.dataclass
class ServerConfig:
    root_path: Path
    thumb_path: Path
    template_path: Path
    sort_by_name: bool
    max_clip_duration: float
    mongodb_url: str
    database_name: str

    @classmethod
    def from_settings(cls, settings: Settings) -> typing.Self:
        '''Create config from a Settings instance, validating that all paths exist.'''
        root_path = settings.site_root_path.resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        thumb_path = settings.site_thumb_path.resolve()
        if not thumb_path.exists():
            raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")

        template_path = settings.site_template_path.resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template path not found: {template_path}")

        return cls(
            root_path=root_path,
            thumb_path=thumb_path,
            template_path=template_path,
            sort_by_name=settings.site_sort_by_name,
            max_clip_duration=settings.site_max_clip_duration,
            mongodb_url=settings.site_mongodb_url,
            database_name=settings.site_database_name,
        )
def create_app(config: ServerConfig) -> FastAPI:
    """Create a FastAPI application with the given configuration."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mongo_client = pymongo.AsyncMongoClient(config.mongodb_url)
        database = mongo_client[config.database_name]
        app.state.db = await MediaIndexDB.from_client(database)
        print("\nAvailable routes:")
        for route in app.routes:
            print(f"  {route.methods} {route.path}")
        print()
        yield
        await mongo_client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.state.config = config

    async def get_config() -> ServerConfig:
        return app.state.config

    async def get_db() -> MediaIndexDB:
        return app.state.db

    CHUNK_SIZE = 1024 * 1024  # 1 MB

    @app.get("/")
    async def root():
        return RedirectResponse(url='/page/')

    @app.get('/page')
    async def page_redirect():
        return RedirectResponse(url='/page/')

    @app.get('/page/', response_class=HTMLResponse)
    async def page_root(
        config: ServerConfig = Depends(get_config),
        db: MediaIndexDB = Depends(get_db),
    ):
        try:
            dir_doc = await db.dirs.find_by_path(config.root_path)
        except MediaDirIndexNotFoundError:
            raise HTTPException(status_code=404, detail=f"Root path not indexed: {config.root_path}")

        subdirs = await db.dirs.find_direct_subdirs(config.root_path)
        page_data = await build_page_dict(dir_doc, subdirs, db, config)

        with config.template_path.open('r') as f:
            template_str = f.read()
        environment = jinja2.Environment()
        template = environment.from_string(template_str)
        return template.render(**page_data)

    @app.get('/list_directories', response_class=PlainTextResponse)
    async def list_directories(
        config: ServerConfig = Depends(get_config),
        db: MediaIndexDB = Depends(get_db),
    ):
        docs = await db.dirs.find_by_path_prefix(config.root_path)
        return "\n".join(str(doc.path.relative_to(config.root_path)) for doc in docs)

    @app.get('/list_videos', response_class=PlainTextResponse)
    async def list_videos(
        config: ServerConfig = Depends(get_config),
        db: MediaIndexDB = Depends(get_db),
    ):
        docs = await db.dirs.find_by_path_prefix(config.root_path)
        lines = []
        for doc in docs:
            for ivf in doc.video_files.values():
                lines.append(str(Path(ivf.path_str).relative_to(config.root_path)))
        return "\n".join(lines)

    @app.get('/page/{page_path:path}', response_class=HTMLResponse)
    async def page_with_video(
        page_path: str,
        config: ServerConfig = Depends(get_config),
        db: MediaIndexDB = Depends(get_db),
    ):
        if page_path == '':
            page_path = '.'
        page_path_full = (config.root_path / page_path)#.resolve()

        try:
            dir_doc = await db.dirs.find_by_path(page_path_full)
        except MediaDirIndexNotFoundError:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_path}")

        subdirs = await db.dirs.find_direct_subdirs(page_path_full)
        page_data = await build_page_dict(dir_doc, subdirs, db, config)

        with config.template_path.open('r') as f:
            template_str = f.read()
        environment = jinja2.Environment()
        template = environment.from_string(template_str)
        return template.render(**page_data)

    @app.get("/file/{file_path:path}")
    async def file_endpoint(
        file_path: str,
        config: ServerConfig = Depends(get_config),
    ):
        full_path = Path(config.root_path) / file_path
        if not full_path.exists():
            return Response(content="File not found", status_code=404)
        return FileResponse(full_path)

    @app.get("/video/{video_path:path}")
    async def video_endpoint(
        video_path: str,
        range: str = Header(None),
        config: ServerConfig = Depends(get_config),
    ):
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
        return Response(
            content=data,
            status_code=206 if range else 200,
            headers=headers,
            media_type="video/mp4",
        )

    @app.get("/thumb/{file_hash}")
    async def thumb_endpoint(
        file_hash: str,
        config: ServerConfig = Depends(get_config),
    ):
        thumb_path = (config.thumb_path / file_hash).with_suffix('.gif')
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail=f"Thumbnail not found: {file_hash}")
        return FileResponse(thumb_path)

    return app


async def build_page_dict(
    dir_doc: MediaDirIndexDoc,
    subdirs: list[MediaDirIndexDoc],
    db: MediaIndexDB,
    config: ServerConfig,
) -> dict[str, typing.Any]:
    '''Build the full page template variables dict for a directory.'''
    video_items: list[dict[str, typing.Any]] = []
    for ivf in sorted(dir_doc.video_files.values(), key=lambda v: Path(v.path_str).name.lower()):
        try:
            vid_doc = await db.videos.find_by_hash(ivf.file_hash)
            video_items.append(build_video_info(ivf, vid_doc, config))
        except Exception:
            continue

    image_items = [
        build_image_info(iif, config)
        for iif in sorted(dir_doc.image_files.values(), key=lambda i: Path(i.path_str).name.lower())
    ]

    subpage_items = []
    for sd in sorted(subdirs, key=lambda d: d.path.name.lower()):
        subpage_items.append(await build_subdir_info(sd, db, config))

    total_size = sum(
        [ivf.stat.size for ivf in dir_doc.video_files.values()] +
        [iif.stat.size for iif in dir_doc.image_files.values()]
    )

    page_path_rel = dir_doc.path.relative_to(config.root_path)
    return {
        'page_path_rel': str(page_path_rel),
        'idx': mediatools.fname_to_id(dir_doc.path.name),
        'name': mediatools.fname_to_title(dir_doc.path.name),
        'files_size_str': mediatools.format_memory(total_size),
        'vids': [v for v in video_items if not v['is_clip']],
        'clips': [v for v in video_items if v['is_clip']],
        'images': image_items,
        'subpages': subpage_items,
        'num_vids': len(dir_doc.video_files),
        'num_imgs': len(dir_doc.image_files),
        'num_subpages': len(subdirs),
    }


def build_video_info(
    ivf: IndexVideoFile,
    vid_doc: VideoIndexDoc,
    config: ServerConfig,
) -> dict[str, typing.Any]:
    '''Build the video info dict for a single video.'''
    vid_path = Path(ivf.path_str)
    vid_path_rel = vid_path.relative_to(config.root_path)
    thumb_exists = (config.thumb_path / f"{vid_doc.file_hash}.gif").exists()

    tags = vid_doc.probe.tags or {}
    created_ts = None
    created_str = None
    if 'creation_time' in tags:
        try:
            created_ts = datetime.datetime.fromisoformat(str(tags['creation_time']))
            created_str = created_ts.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass

    try:
        aspect = vid_doc.probe.video.aspect_ratio
        res_str = vid_doc.probe.resolution_str()
    except Exception:
        aspect = 1.0
        res_str = ''

    return {
        'vid_path_rel': str(vid_path_rel),
        'thumb_exists': thumb_exists,
        'idx': mediatools.fname_to_id(vid_path.stem),
        'vid_title': mediatools.fname_to_title(vid_path.stem),
        'vid_size': vid_doc.stat.size,
        'vid_size_str': mediatools.format_memory(vid_doc.stat.size),
        'duration': vid_doc.probe.duration,
        'duration_str': vid_doc.probe.duration_str(),
        'res_str': res_str,
        'aspect': aspect,
        'hash': vid_doc.file_hash,
        'is_clip': vid_doc.probe.duration < config.max_clip_duration,
        'created_ts': created_ts.timestamp() if created_ts is not None else None,
        'created': created_str,
    }


def build_image_info(
    iif: IndexImageFile,
    config: ServerConfig,
) -> dict[str, typing.Any]:
    '''Build the image info dict for a single image.'''
    img_path = Path(iif.path_str)
    img_path_rel = img_path.relative_to(config.root_path)
    width, height = iif.res
    aspect = width / height if height else 1.0

    return {
        'img_path_rel': str(img_path_rel),
        'title': mediatools.fname_to_title(img_path.stem),
        'aspect': aspect,
    }


async def build_subdir_info(
    sd: MediaDirIndexDoc,
    db: MediaIndexDB,
    config: ServerConfig,
) -> dict[str, typing.Any]:
    '''Build the subpage summary dict for a subdirectory card.'''
    sd_path_rel = sd.path.relative_to(config.root_path)

    all_docs = await db.dirs.find_by_path_prefix(sd.path)
    subfolder_thumbs: list[str] = []
    for doc in all_docs:
        for ivf in doc.video_files.values():
            if (config.thumb_path / f"{ivf.file_hash}.gif").exists():
                subfolder_thumbs.append(ivf.file_hash)

    return {
        'page_path_rel': str(sd_path_rel),
        'idx': mediatools.fname_to_id(sd.path.name),
        'name': mediatools.fname_to_title(sd.path.name),
        'num_vids': len(sd.video_files),
        'num_imgs': len(sd.image_files),
        'num_subpages': len(sd.subpaths),
        'subfolder_thumbs_all': subfolder_thumbs,
    }


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('--root-path', type=Path, default=None, help='Root directory containing video files')
    parser.add_argument('--template-path', type=Path, default=None, help='Path to the HTML template file')
    parser.add_argument('--thumb-path', type=Path, default=None, help='Directory for thumbnail images')
    parser.add_argument('--mongodb-url', type=str, default=None, help='MongoDB connection URL')
    parser.add_argument('-d', '--database-name', type=str, default=None, help='MongoDB database name')
    parser.add_argument('-p', '--port', type=int, default=None, help='Port to run the server on')
    parser.add_argument('-s', '--sort-by-name', action='store_true', default=None, help='Sort directories by name')
    parser.add_argument('-m', '--max-clip-duration', type=float, default=None, help='Max duration (seconds) to treat a video as a clip')
    args = parser.parse_args()

    # Load base settings from .env / environment variables
    settings = Settings()

    # Override with any explicitly provided CLI args
    overrides = {k: v for k, v in vars(args).items() if v is not None}
    if overrides:
        settings = settings.model_copy(update={
            f'site_{k.replace("-", "_")}': v for k, v in overrides.items()
        })

    port = settings.site_port
    config = ServerConfig.from_settings(settings)
    app = create_app(config)

    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{port}")
    print(f"Visit http://0.0.0.0:{port}/page/ to browse videos")

    uvicorn.run(app, host="0.0.0.0", port=port)
