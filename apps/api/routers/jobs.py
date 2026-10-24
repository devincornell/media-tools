from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from mediatools.application.media_jobs import to_job_view
from mediatools.contracts import ErrorResponse, JobPage, JobView
from mediatools.jobs import JobStatus

from ..dependencies import JobManagerDep

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


@router.get("")
async def list_jobs(
    manager: JobManagerDep,
    status: JobStatus | None = None,
    job_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    jobs, total = await manager.list(status=status, job_type=job_type, limit=limit, offset=offset)
    return JobPage(items=[to_job_view(j) for j in jobs], total=total, limit=limit, offset=offset)


@router.get("/{job_id}", responses=_NOT_FOUND)
async def get_job(job_id: str, manager: JobManagerDep) -> JobView:
    return to_job_view(await manager.get(job_id))


@router.post("/{job_id}/cancel", responses=_NOT_FOUND)
async def cancel_job(job_id: str, manager: JobManagerDep) -> JobView:
    '''Cancel a queued job now; a running job stops at its next checkpoint.'''
    return to_job_view(await manager.cancel(job_id))
