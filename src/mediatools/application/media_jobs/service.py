from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from ...contracts import (
    CleanupRequest,
    ConvertMp4Request,
    DeleteItemRequest,
    JobAttemptView,
    JobView,
    MediaJobPage,
    MediaJobView,
    MontageRequest,
    MoveItemRequest,
    MoveRequest,
    ReindexRequest,
    ThumbnailsRequest,
)
from ...index_db import MediaJobCollection, MediaJobRecord
from ...jobs import Job, JobManager, JobStatus, new_job_id
from ..errors import InvalidJobRequestError, PathOutsideRootError
from ..paths import resolve_allowed_source, resolve_under_root
from . import fileops
from .types import (
    CLEANUP,
    CONVERT_MP4,
    DELETE_ITEM,
    KIND_BY_TYPE,
    MONTAGE,
    MOVE,
    MOVE_ITEM,
    REINDEX,
    THUMBNAILS,
    TYPE_BY_KIND,
)

MediaJobRequest = (
    ReindexRequest
    | ThumbnailsRequest
    | CleanupRequest
    | ConvertMp4Request
    | MoveRequest
    | MoveItemRequest
    | DeleteItemRequest
    | MontageRequest
)

_TYPE_BY_REQUEST: dict[type, str] = {
    ReindexRequest: REINDEX,
    ThumbnailsRequest: THUMBNAILS,
    CleanupRequest: CLEANUP,
    ConvertMp4Request: CONVERT_MP4,
    MoveRequest: MOVE,
    MoveItemRequest: MOVE_ITEM,
    DeleteItemRequest: DELETE_ITEM,
    MontageRequest: MONTAGE,
}


def to_job_view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        job_type=job.job_type,
        status=job.status.value,
        progress_percent=job.progress_percent,
        progress_stage=job.progress_stage,
        request_ref=job.request_ref,
        result_ref=job.result_ref,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested_at is not None,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_code=job.error_code,
        error_message=job.error_message,
    )


@dataclasses.dataclass(frozen=True)
class MediaJobService:
    '''Validates and submits media jobs, and presents them together with their parameters and results.'''

    root_path: Path
    copy_source_roots: tuple[Path, ...]
    jobs: JobManager
    records: MediaJobCollection
    max_attempts: int = 3

    async def submit(self, request: MediaJobRequest) -> Job:
        job_type = _TYPE_BY_REQUEST[type(request)]
        target = self._validate(request)
        job_id = new_job_id()
        # Record first: the job only becomes claimable once its parameters exist.
        await self.records.insert(MediaJobRecord(
            job_id=job_id,
            job_type=job_type,
            target_path=str(target.relative_to(self.root_path)),
            params=request.model_dump(mode="json"),
        ))
        return await self.jobs.submit(job_type, job_id=job_id, max_attempts=self.max_attempts)

    async def get(self, job_id: str) -> MediaJobView:
        job = await self.jobs.get(job_id)
        return self._view(job, await self.records.get(job_id))

    async def cancel(self, job_id: str) -> MediaJobView:
        job = await self.jobs.cancel(job_id)
        return self._view(job, await self.records.get(job_id))

    async def list(
        self, *, status: JobStatus | None = None, kind: str | None = None, limit: int = 50, offset: int = 0
    ) -> MediaJobPage:
        job_type = TYPE_BY_KIND.get(kind) if kind else None
        if kind and job_type is None:
            raise InvalidJobRequestError(f"Unknown job kind: {kind}")
        jobs, total = await self.jobs.list(status=status, job_type=job_type, limit=limit, offset=offset)
        records = await self.records.get_many(j.id for j in jobs)
        return MediaJobPage(
            items=[self._view(j, records.get(j.id)) for j in jobs], total=total, limit=limit, offset=offset
        )

    def _validate(self, request: MediaJobRequest) -> Path:
        '''Check paths up front so bad requests fail fast; returns the target directory.'''
        if isinstance(request, MoveRequest):
            return self._validate_move(request)
        if isinstance(request, MoveItemRequest):
            return self._validate_move_item(request)
        if isinstance(request, DeleteItemRequest):
            return self._validate_delete_item(request)
        if isinstance(request, MontageRequest):
            return self._validate_montage(request)
        target = self._under_root(request.path)
        if not target.is_dir():
            raise InvalidJobRequestError(f"Directory not found: {request.path}")
        return target

    def _validate_montage(self, request: MontageRequest) -> Path:
        for source in request.sources:
            try:
                path = resolve_allowed_source(source, (self.root_path, *self.copy_source_roots))
            except PathOutsideRootError as e:
                raise InvalidJobRequestError(str(e)) from e
            if not path.is_dir():
                raise InvalidJobRequestError(f"Source directory not found: {source}")
        output = self._under_root(request.output)
        if output.exists() and not request.overwrite:
            raise InvalidJobRequestError(f"Output already exists: {request.output}")
        return output

    def _validate_move(self, request: MoveRequest) -> Path:
        if not self.copy_source_roots:
            raise InvalidJobRequestError("Move jobs are disabled: no copy source roots are configured.")
        try:
            source = resolve_allowed_source(request.source, self.copy_source_roots)
        except PathOutsideRootError as e:
            raise InvalidJobRequestError(str(e)) from e
        if not source.is_dir():
            raise InvalidJobRequestError(f"Source directory not found: {request.source}")
        if fileops.is_protected_root(source, self.copy_source_roots):
            raise InvalidJobRequestError(
                "Choose a folder inside the copy source root, not the root itself: the source folder is removed after the move."
            )
        if not os.access(source, os.W_OK | os.X_OK):
            raise InvalidJobRequestError(fileops.permission_message(source, [source]))
        dest = self._under_root(request.dest)
        dest_real, source_real = dest.resolve(), source.resolve()
        if dest_real.is_relative_to(source_real) or source_real.is_relative_to(dest_real):
            raise InvalidJobRequestError("Source and destination must not contain each other.")
        existing = next(p for p in (dest, *dest.parents) if p.exists())
        if not os.access(existing, os.W_OK | os.X_OK):
            raise InvalidJobRequestError(
                f"The server can't write to {existing} (owned by {fileops.user_name(existing.stat().st_uid)})."
            )
        return dest

    def _validate_move_item(self, request: MoveItemRequest) -> Path:
        source = self._under_root(request.path)
        if source == self.root_path:
            raise InvalidJobRequestError("The gallery root can't be moved.")
        if not os.path.lexists(source):
            raise InvalidJobRequestError(f"Not found: {request.path}")
        dest = self._under_root(request.dest)
        if not dest.is_dir():
            raise InvalidJobRequestError(f"Destination folder not found: {request.dest}")
        if dest.resolve() == source.parent.resolve():
            raise InvalidJobRequestError("The item is already in that folder.")
        if source.is_dir() and (dest.resolve() == source.resolve() or dest.resolve().is_relative_to(source.resolve())):
            raise InvalidJobRequestError("A folder can't be moved into itself.")
        clash = dest / source.name
        if source.is_dir() and os.path.lexists(clash) and not clash.is_dir():
            raise InvalidJobRequestError(f"A file named {source.name} already exists in the destination folder.")
        for folder in (source.parent, dest):
            if not os.access(folder, os.W_OK | os.X_OK):
                raise InvalidJobRequestError(
                    f"The server can't write to {folder} (owned by {fileops.user_name(folder.stat().st_uid)})."
                )
        return dest

    def _validate_delete_item(self, request: DeleteItemRequest) -> Path:
        source = self._under_root(request.path)
        if source == self.root_path:
            raise InvalidJobRequestError("The gallery root can't be deleted.")
        if not os.path.lexists(source):
            raise InvalidJobRequestError(f"Not found: {request.path}")
        if not os.access(source.parent, os.W_OK | os.X_OK):
            raise InvalidJobRequestError(
                f"The server can't delete from {source.parent} (owned by {fileops.user_name(source.parent.stat().st_uid)})."
            )
        return source

    def _under_root(self, rel: str) -> Path:
        try:
            return resolve_under_root(self.root_path, rel)
        except PathOutsideRootError as e:
            raise InvalidJobRequestError(str(e)) from e

    @staticmethod
    def _view(job: Job, record: MediaJobRecord | None) -> MediaJobView:
        return MediaJobView(
            job=to_job_view(job),
            kind=KIND_BY_TYPE.get(job.job_type, job.job_type),
            target=record.target_path if record else None,
            params=record.params if record else {},
            result=record.result if record else None,
            attempts=[
                JobAttemptView(
                    attempt_no=a.attempt_no,
                    status=a.status.value,
                    started_at=a.started_at,
                    finished_at=a.finished_at,
                    error_code=a.error_code,
                    error_message=a.error_message,
                )
                for a in job.attempts
            ],
        )
