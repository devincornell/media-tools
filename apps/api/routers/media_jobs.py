from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from mediatools.application.media_jobs import MediaJobRequest, MediaJobService
from mediatools.contracts import (
    CleanupRequest,
    ConvertMp4Request,
    ErrorResponse,
    JobAccepted,
    JobConfigView,
    MediaJobPage,
    MediaJobView,
    MontageRequest,
    MoveItemRequest,
    MoveRequest,
    ReindexRequest,
    ThumbnailsRequest,
)
from mediatools.jobs import JobStatus

from ..dependencies import JobConfigDep, MediaJobsDep
from ..settings import TEMPLATES_DIR

router = APIRouter(tags=["media jobs"])

_INVALID: dict[int | str, dict[str, Any]] = {422: {"model": ErrorResponse}}


async def _submit(svc: MediaJobService, request: MediaJobRequest) -> JobAccepted:
    job = await svc.submit(request)
    return JobAccepted(job_id=job.id, status=job.status.value, status_url=f"/v1/jobs/{job.id}")


@router.post("/api/jobs/reindex", status_code=202, responses=_INVALID)
async def submit_reindex(request: ReindexRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Rescan a directory tree into the index.'''
    return await _submit(svc, request)


@router.post("/api/jobs/thumbnails", status_code=202, responses=_INVALID)
async def submit_thumbnails(request: ThumbnailsRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Generate missing animated thumbnails under a directory.'''
    return await _submit(svc, request)


@router.post("/api/jobs/cleanup", status_code=202, responses=_INVALID)
async def submit_cleanup(request: CleanupRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Find (dry run) or delete empty, unprobable, or duplicate videos.'''
    return await _submit(svc, request)


@router.post("/api/jobs/convert-mp4", status_code=202, responses=_INVALID)
async def submit_convert_mp4(request: ConvertMp4Request, svc: MediaJobsDep) -> JobAccepted:
    '''Convert non-MP4 videos to MP4 next to the originals.'''
    return await _submit(svc, request)


@router.post("/api/jobs/move", status_code=202, responses=_INVALID)
async def submit_move(request: MoveRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Move a directory's contents into the gallery, then rescan the destination.'''
    return await _submit(svc, request)


@router.post("/api/jobs/move-item", status_code=202, responses=_INVALID)
async def submit_move_item(request: MoveItemRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Move a gallery file or folder into another gallery folder, then rescan both.'''
    return await _submit(svc, request)


@router.post("/api/jobs/montage", status_code=202, responses=_INVALID)
async def submit_montage(request: MontageRequest, svc: MediaJobsDep) -> JobAccepted:
    '''Build a montage from random clips of videos whose creation_time falls in a date range.'''
    return await _submit(svc, request)


@router.get("/api/media-jobs")
async def list_media_jobs(
    svc: MediaJobsDep,
    status: JobStatus | None = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MediaJobPage:
    return await svc.list(status=status, kind=kind, limit=limit, offset=offset)


@router.get("/api/media-jobs/{job_id}", responses={404: {"model": ErrorResponse}})
async def get_media_job(job_id: str, svc: MediaJobsDep) -> MediaJobView:
    return await svc.get(job_id)


@router.get("/api/job-config")
async def job_config(config: JobConfigDep) -> JobConfigView:
    return config


@router.get("/jobs", include_in_schema=False)
async def jobs_page() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "jobs.html", media_type="text/html")
