import asyncio
import typing
import os
import pickle
import tempfile
from fastapi import FastAPI, Request, Header, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, PlainTextResponse
from pathlib import Path
import argparse
import datetime
from fastapi import Depends
import pathlib
import jinja2
import PIL
import dataclasses
import json
import pprint
import random

import sys

import tqdm
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util


TMP_CONFIG_FNAME = f"web_api_config.pkl"

@dataclasses.dataclass
class ServerConfig:
    root_path: Path
    thumb_path: Path
    template_path: Path
    sort_by_name: bool
    max_clip_duration: float
    db: mediatools.MediaSiteIndexDB

    @classmethod
    def from_config_args(
        cls,
        root_path: Path|str,
        thumb_path: Path|str,
        template_path: Path|str,
        sort_by_name: bool,
        max_clip_duration: float,
        mongodb_url: str,
        database_name: str,
    ) -> typing.Self:
        '''Create config after checking if all paths exist.'''
        root_path = Path(root_path).resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"Root path not found: {root_path}")

        #thumb_path.mkdir(parents=True, exist_ok=True)
        thumb_path = Path(thumb_path).resolve()
        if not thumb_path.exists():
            raise FileNotFoundError(f"Thumbnail path not found: {thumb_path}")

        template_path = Path(template_path).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template path not found: {template_path}")

        db = mediatools.MediaSiteIndexDB(
            db_name=database_name,
            url=mongodb_url,
        )

        return cls(
            root_path=root_path,
            thumb_path=thumb_path,
            template_path=template_path,
            sort_by_name=sort_by_name,
            max_clip_duration=max_clip_duration,
            db=db,
        )
        
    def get_template_vars(self, path: Path) -> dict[str, typing.Any]:
        '''Get template variables.'''
        path = Path(path)
        if self.site_index is None:
            raise ValueError("Site index is not set")
        
        print(f'{path=}, {self.site_index=}')
        mdir = self.site_index.subdir(path)
        sorted_subdirs = sorted(mdir.subdirs.values(), key=lambda d: str(d.path.name).lower())
        #print([sd.path.name.lower() for sd in sorted_subdirs])
        print(f'{mdir=}')
        return {
            **mdir.meta['info'],
            'subpages': [sd.meta['info'] for sd in sorted_subdirs],
        }
    




def create_app(config: ServerConfig) -> FastAPI:
    """Create a new FastAPI application with the given configuration."""
    app = FastAPI(lifespan=config.db.lifespan)
    
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
    
    @app.get('/page')
    async def page_redirect():
        return RedirectResponse(url='/page/')

    @app.get('/rescan', response_class=PlainTextResponse)
    async def get_rescan(config: ServerConfig = Depends(get_config)):
        await config.db.insert_from_media_dir(
            mediatools.scan_directory(config.root_path),
            verbose=True,
        )

        all_dirs = await config.db.find_all_dirs()

        msg = ''
        for dir in all_dirs:
            msg += (f'({len(dir.video_files):03d} videos) {dir.path_abs}\n')

        return f'Updated successfully!\n\nChanges:\n{msg}'

    @app.get('/list_directories', response_class=PlainTextResponse)
    async def list_pages(config: ServerConfig = Depends(get_config)):
        return "\n".join([str(d.path) for d in config.site_index.all_dirs()])

    @app.get('/list_videos', response_class=PlainTextResponse)
    async def list_videos(config: ServerConfig = Depends(get_config)):
        return "\n".join([vf.meta['info']['vid_path_rel'] for vf in config.site_index.all_videos() if vf.meta['info'] is not None])

    @app.get('/page/{page_path:path}', response_class=HTMLResponse)
    async def page_with_video(page_path: str, config: ServerConfig = Depends(get_config)):
        if page_path == '':
            page_path = '.'

        page_path_full = config.root_path / page_path
        di = await config.db.dir_index.fetch_by_abs_path(page_path_full)
        page_info = await page_index_to_dict(di, config)
        return HTMLResponse(content=pprint.pformat(page_info), status_code=200)

        try:
            page_data = config.get_template_vars(page_path)
        except mediatools.DirectoryNotFoundError:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_path}")
        
        print(f'rendering template {config.template_path}')
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
            "Content-Type": f"video/mp4",
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
    
    @app.get("/thumb/{hash_firstlast1kb}")
    async def thumb_endpoint(hash_firstlast1kb: str, config: ServerConfig = Depends(get_config)):
        thumb_path = (config.thumb_path / hash_firstlast1kb).with_suffix('.gif')
        if not thumb_path.exists():
            raise HTTPException(status_code=404, detail=f"Thumbnail not found: {hash_firstlast1kb}")
        return FileResponse(thumb_path)

    return app


async def page_index_to_dict(mdi: mediatools.MediaDirIndex, config: ServerConfig) -> dict[str,typing.Any]:
    '''Get page info dictionary. Assume image and video infos have already been populated.'''
    vid_inds = list(sorted(await mdi.fetch_video_metas(), key=lambda v: v[0].path_abs.name.lower()))
    img_inds = list(sorted(mdi.image_files.values(), key=lambda i: i.path_abs.name.lower()))
    subpath_inds = list(sorted(await mdi.fetch_subdir_indexes(), key=lambda d: d.path_abs.name.lower()))

    video_infos = [get_video_info(ivf,vfi,config) for ivf,vfi in vid_inds]
    image_infos = [get_image_info(imi, config) for imi in img_inds]
    subpage_infos = [get_subpage_info(sd, config) for sd in subpath_inds]

    total_size = sum([vi[1].stat.size for vi in vid_inds] + [imi.stat.size for imi in img_inds])

    return {
        #'page_path_abs': str(mdi.path_abs),
        'page_path_rel': str(mdi.path_abs.relative_to(config.root_path)),
        'idx': mediatools.fname_to_id(mdi.path_abs.name),
        'name': mediatools.fname_to_title(mdi.path_abs.name), 
        'files_size_str': mediatools.format_memory(total_size),
        #'subfolder_thumbs_all': all_subfolder_thumbs,
        #'subfolder_thumb': all_subfolder_thumbs[0] if all_subfolder_thumbs else '',#best_thumb.get_final_path(),
        #'subfolder_aspect': '',#best_thumb.get_final_aspect(),
        'vids': video_infos,
        #'clips': [vi for vi in vid_infos if vi['is_clip']],
        'clips': [],
        'images': image_infos,
        'subpages': subpage_infos,
        'num_vids': len(vid_inds),
        'num_imgs': len(img_inds),
        'num_subpages': len(subpath_inds),
    }


async def get_page_info(mdi: mediatools.MediaDirIndex, config: ServerConfig) -> dict[str,typing.Any]:
    '''Get page info dictionary. Used to generate the thumbnail/icons when shown as a subfolder.'''
    vid_inds = list(sorted(await mdi.fetch_video_metas(), key=lambda v: v[0].path_abs.name.lower()))
    img_inds = list(sorted(mdi.image_files.values(), key=lambda i: i.path_abs.name.lower()))
    #subpath_inds = list(sorted(await mdi.fetch_subdir_indexes(), key=lambda d: d.path_abs.name.lower()))

    all_subfolder_thumbs = list()
    
    vid_infos: list[dict[str,typing.Any]] = list()
    for ivf,vfi in vid_inds:
        vid_info = get_video_info(vfi, ivf, config)
        if Path(vid_info['thumb_path_abs']).exists() and vfi.stat.size > 0:
            all_subfolder_thumbs.append(vid_info['thumb_name'])
    
    img_infos: list[dict[str,typing.Any]] = list()
    for imi in img_inds:
        img_info = get_image_info(imi, config)
        img_infos.append(img_info)
        all_subfolder_thumbs.append(img_info['img_path_rel'])

    return {
        #'page_path_abs': str(mdi.path_abs),
        'page_path_rel': str(mdi.path_abs.relative_to(config.root_path)),
        'idx': mediatools.fname_to_id(mdi.path_abs.name),
        'name': mediatools.fname_to_title(mdi.path_abs.name), 
        #'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdi.all_file_paths()])),
        #'subfolder_thumbs_all': all_subfolder_thumbs,
        #'subfolder_thumb': all_subfolder_thumbs[0] if all_subfolder_thumbs else '',
        'num_vids': len(mdi.video_files),
        'num_imgs': len(mdi.image_files),
        'num_subpages': len(mdi.subpaths_rel),
    }



async def get_subpage_info(mdi: mediatools.MediaDirIndex, config: ServerConfig) -> dict[str,typing.Any]:
    '''Get page info dictionary. Used to generate the thumbnail/icons when shown as a subfolder.'''
    vid_inds = list(sorted(await mdi.fetch_video_metas(), key=lambda v: v[0].path_abs.name.lower()))
    img_inds = list(sorted(mdi.image_files.values(), key=lambda i: i.path_abs.name.lower()))
    #subpath_inds = list(sorted(await mdi.fetch_subdir_indexes(), key=lambda d: d.path_abs.name.lower()))

    all_subfolder_thumbs = list()
    
    vid_infos: list[dict[str,typing.Any]] = list()
    for ivf,vfi in vid_inds:
        vid_info = get_video_info(vfi, ivf, config)
        if Path(vid_info['thumb_path_abs']).exists() and vfi.stat.size > 0:
            all_subfolder_thumbs.append(vid_info['thumb_name'])
    
    img_infos: list[dict[str,typing.Any]] = list()
    for imi in img_inds:
        img_info = get_image_info(imi, config)
        img_infos.append(img_info)
        all_subfolder_thumbs.append(img_info['img_path_rel'])

    return {
        #'page_path_abs': str(mdi.path_abs),
        'page_path_rel': str(mdi.path_abs.relative_to(config.root_path)),
        'idx': mediatools.fname_to_id(mdi.path_abs.name),
        'name': mediatools.fname_to_title(mdi.path_abs.name), 
        'files_size_str': mediatools.format_memory(sum([p.stat().st_size for p in mdi.all_file_paths()])),
        'subfolder_thumbs_all': all_subfolder_thumbs,
        'subfolder_thumb': all_subfolder_thumbs[0] if all_subfolder_thumbs else '',
        'num_vids': len(mdi.video_files),
        'num_imgs': len(mdi.image_files),
        'num_subpages': len(mdi.subpaths_rel),
    }

def get_video_info(
    ivf: mediatools.site.IndexVideoFile,
    vfi: mediatools.VideoFileIndex, 
    config: ServerConfig,
) -> dict[str,typing.Any]:
    '''Get video info dictionary and whether it's a clip.'''
    vid_path_abs = ivf.path_abs
    vid_path_rel = ivf.path_abs.relative_to(config.root_path)
    thumb_name = f"{vfi.hash_firstlast1kb}.gif"

    if vfi.probe.tags is not None and 'creation_time' in vfi.probe.tags:
        created_ts_str = vfi.probe.tags['creation_time']
        created_ts = datetime.datetime.fromisoformat(created_ts_str)
        created_str = created_ts.strftime('%Y-%m-%d %H:%M:%S')
    else:
        created_ts = None
        created_str = None

    return {
        #'vid_path_abs': str(vid_path_abs),
        'vid_path_rel': str(vid_path_rel),
        #'thumb_name': thumb_name,
        #'thumb_path_abs': str(config.thumb_path / thumb_name),
        'thumb_exists': (config.thumb_path / thumb_name).exists() and (config.thumb_path / thumb_name).stat().st_size > 0,
        'idx': mediatools.fname_to_id(ivf.path_abs.name),
        'vid_title': mediatools.fname_to_title(ivf.path_abs.name),
        'vid_size': vfi.stat.size,
        'vid_size_str': vfi.stat.size_str(),
        'duration': vfi.probe.duration,
        'duration_str': vfi.probe.duration_str(),
        'res_str': vfi.probe.resolution_str(),
        'aspect': vfi.probe.video.aspect_ratio,
        'hash': vfi.hash_firstlast1kb,
        'is_clip': vfi.probe.duration < config.max_clip_duration,
        'created_ts': created_ts.timestamp() if created_ts is not None else None,
        'created': created_str,
    }



def get_image_info(
    iif: mediatools.site.IndexImageFile, 
    config: ServerConfig, 
) -> dict[str,typing.Any]:
    '''Get image info dictionary. To be used in a map function.'''
    img_path_abs = iif.path_abs
    img_path_rel = iif.path_abs.relative_to(config.root_path)
    hash_str = util.get_hash_hex_THUMB(img_path_abs)

    return {
        #'img_path_abs': str(img_path_abs),
        'img_path_rel': str(img_path_rel),
        'title': mediatools.fname_to_title(img_path_abs.stem),
        'aspect': iif.meta.aspect_ratio(),
    }






if __name__ == "__main__":
    import uvicorn
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description='Start a video streaming server')
    parser.add_argument('root_path', type=Path, help='Root directory containing video files')
    parser.add_argument('template_path', type=Path, help='Path to the HTML template file.')
    parser.add_argument('thumb_path', type=Path, help='Directory for thumbnail images.')
    parser.add_argument('mongodb_url', help='MongoDB connection URL')
    parser.add_argument('-d', '--database-name', type=str, default='dwhost', help='MongoDB database name (default: dwhost)')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port to run the server on (default: 8000)')
    parser.add_argument('-s', '--sort-by-name', action='store_true', help='Rebuild the site index even if a cached version exists')
    parser.add_argument('-m', '--max-clip-duration', type=float, default=0, help='Maximum clip duration in seconds (default: 60)')
    parser.add_argument('-r', '--rescan-db', action='store_true', help='Rescan the database')
    args = parser.parse_args()

    config = ServerConfig.from_config_args(
        root_path=args.root_path,
        template_path=args.template_path,
        thumb_path=args.thumb_path,
        mongodb_url=args.mongodb_url,
        sort_by_name=args.sort_by_name,
        max_clip_duration=args.max_clip_duration,
        database_name=args.database_name,
    )

    app = create_app(config)
    
    print(f"\nStarting server: {config.root_path}")
    print(f"Server will be available at: http://0.0.0.0:{args.port}")
    print(f"Visit http://0.0.0.0:{args.port}/page to see available videos")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
    )
