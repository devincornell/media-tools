from __future__ import annotations

import builtins
import dataclasses

from .logs import JobLogLine, MongoJobLogStore
from .models import Job, JobStatus, new_job_id, utcnow
from .repository import MongoJobRepository


class JobNotFoundError(Exception):
    '''No job with this ID exists in the caller's scope.'''


@dataclasses.dataclass(frozen=True)
class JobManager:
    '''Application-facing operations on jobs within one authorization scope.'''

    repo: MongoJobRepository
    scope_id: str
    log_store: MongoJobLogStore | None = None

    async def submit(
        self,
        job_type: str,
        *,
        job_id: str | None = None,
        request_ref: str | None = None,
        max_attempts: int = 3,
    ) -> Job:
        '''Create a queued job. Persist any application records keyed by `job_id` *before* calling this.'''
        now = utcnow()
        job = Job(
            id=job_id or new_job_id(),
            job_type=job_type,
            scope_id=self.scope_id,
            request_ref=request_ref,
            max_attempts=max_attempts,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        await self.repo.insert(job)
        return job

    async def get(self, job_id: str) -> Job:
        job = await self.repo.get(job_id, self.scope_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        return job

    async def list(
        self,
        *,
        status: JobStatus | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        return await self.repo.list(self.scope_id, status=status, job_type=job_type, limit=limit, offset=offset)

    async def cancel(self, job_id: str) -> Job:
        job = await self.repo.request_cancel(job_id, self.scope_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        return job

    async def logs(self, job_id: str, *, after: str | None = None, limit: int = 500) -> builtins.list[JobLogLine]:
        '''Log lines after line ID `after`, or the most recent `limit` lines.'''
        await self.get(job_id)
        if self.log_store is None:
            return []
        return await self.log_store.read(job_id, after=after, limit=limit)
