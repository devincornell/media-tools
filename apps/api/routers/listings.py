from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from mediatools.contracts import DirectoryPage, ErrorResponse, PathList

from ..dependencies import GalleryDep

router = APIRouter(tags=["listings"])


@router.get("/list_directories", response_class=PlainTextResponse)
async def list_directories_text(gallery: GalleryDep) -> str:
    return "\n".join(await gallery.list_directories())


@router.get("/list_videos", response_class=PlainTextResponse)
async def list_videos_text(gallery: GalleryDep) -> str:
    return "\n".join(await gallery.list_videos())


api_router = APIRouter(prefix="/api", tags=["api"])


@api_router.get("/directories")
async def list_directories(gallery: GalleryDep) -> PathList:
    return PathList(paths=await gallery.list_directories())


@api_router.get("/videos")
async def list_videos(gallery: GalleryDep) -> PathList:
    return PathList(paths=await gallery.list_videos())


@api_router.get("/directory/{dir_path:path}", responses={404: {"model": ErrorResponse}})
async def get_directory(dir_path: str, gallery: GalleryDep) -> DirectoryPage:
    return await gallery.directory_page(dir_path)
