from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from mediatools.contracts import ErrorResponse
from mediatools.contracts.uploads import UploadCheckRequest, UploadCheckResponse, UploadResult

from ..dependencies import UploadDep
from ..settings import TEMPLATES_DIR

router = APIRouter(tags=["uploads"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    507: {"model": ErrorResponse},
}


@router.post("/api/uploads/check")
async def check_uploads(body: UploadCheckRequest, uploads: UploadDep) -> UploadCheckResponse:
    '''Report which of the files already exist under `dest`, so a client can skip or resume.'''
    return UploadCheckResponse(items=await uploads.check(body.dest, body.files))


@router.put("/api/uploads/file", responses=_ERRORS)
async def upload_file(
    request: Request,
    uploads: UploadDep,
    path: Annotated[str, Query(description="File path relative to `dest`, with `/` separators.")],
    dest: Annotated[str, Query(description="Destination folder relative to the gallery root.")] = ".",
    overwrite: Annotated[bool, Query(description="Replace an existing file instead of answering 409.")] = False,
    mtime: Annotated[float | None, Query(description="Modification time to apply, in milliseconds since the epoch.")] = None,
) -> UploadResult:
    '''Store the raw request body at `dest/path`, creating folders as needed.'''
    declared = request.headers.get("content-length")
    return await uploads.store(
        dest,
        path,
        request.stream(),
        expected_size=int(declared) if declared and declared.isdigit() else None,
        overwrite=overwrite,
        mtime_ms=mtime,
    )


@router.get("/upload", include_in_schema=False)
async def upload_page() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "upload.html", media_type="text/html")
