from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from mediatools.application.media_jobs import to_job_view
from mediatools.contracts import (
    ErrorResponse,
    JobLogLineView,
    JobLogPage,
    JobPage,
    JobView,
)
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


@router.get("/{job_id}/logs", responses=_NOT_FOUND)
async def job_logs(
    job_id: str,
    manager: JobManagerDep,
    after: Annotated[str | None, Query(pattern="^[0-9a-f]{24}$", description="Return lines after this line ID.")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> JobLogPage:
    '''Without `after`, returns the most recent `limit` lines; with it, the next lines in order.'''
    lines = await manager.logs(job_id, after=after, limit=limit)
    return JobLogPage(
        lines=[JobLogLineView(id=ln.id, attempt_no=ln.attempt_no, ts=ln.ts, message=ln.message) for ln in lines],
        last_id=lines[-1].id if lines else after,
    )
