from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..dependencies import GalleryDep

router = APIRouter(tags=["media"])

VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}


@router.get("/file/{file_path:path}", response_class=FileResponse)
async def file_endpoint(file_path: str, gallery: GalleryDep) -> FileResponse:
    return FileResponse(gallery.media_file(file_path))


@router.get("/video/{video_path:path}", response_class=FileResponse)
async def video_endpoint(video_path: str, gallery: GalleryDep) -> FileResponse:
    # FileResponse handles Range requests (206 / 416) itself.
    path = gallery.media_file(video_path)
    return FileResponse(
        path,
        media_type=VIDEO_MEDIA_TYPES.get(path.suffix.lower(), "video/mp4"),
        headers={"Cache-Control": "public, max-age=31536000"},
    )


@router.get("/thumb/{file_hash}", response_class=FileResponse)
async def thumb_endpoint(file_hash: str, gallery: GalleryDep) -> FileResponse:
    return FileResponse(gallery.thumbnail_file(file_hash))
