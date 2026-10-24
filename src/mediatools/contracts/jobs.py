from __future__ import annotations

import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- generic jobs

class JobView(_Contract):
    '''Public representation of a job's lifecycle state (no lease or worker internals).'''

    id: Annotated[str, Field(description="Job ID; also the key for application records about this job.")]
    job_type: Annotated[str, Field(description="Versioned job type, e.g. `media.reindex.v1`.")]
    status: Annotated[str, Field(description="One of queued, running, succeeded, failed, canceled.")]
    progress_percent: Annotated[int | None, Field(description="0-100 progress reported by the handler, if any.")]
    progress_stage: Annotated[str | None, Field(description="Human-readable description of the current step.")]
    request_ref: Annotated[str | None, Field(description="Optional reference to request data stored elsewhere.")]
    result_ref: Annotated[str | None, Field(description="Optional reference to result data stored elsewhere.")]
    attempt_count: Annotated[int, Field(description="Number of execution attempts started so far.")]
    max_attempts: Annotated[int, Field(description="Attempts allowed before the job fails permanently.")]
    cancel_requested: Annotated[bool, Field(description="True once cancellation was requested; a running job stops at its next checkpoint.")]
    created_at: Annotated[datetime.datetime, Field(description="When the job was submitted (UTC).")]
    started_at: Annotated[datetime.datetime | None, Field(description="When the first attempt started (UTC).")]
    finished_at: Annotated[datetime.datetime | None, Field(description="When the job reached a terminal state (UTC).")]
    error_code: Annotated[str | None, Field(description="Error code of the most recent failure.")]
    error_message: Annotated[str | None, Field(description="Error message of the most recent failure.")]


class JobAttemptView(_Contract):
    '''One execution attempt of a job.'''

    attempt_no: Annotated[int, Field(description="1-based attempt number.")]
    status: Annotated[str, Field(description="One of running, succeeded, failed, interrupted, canceled.")]
    started_at: Annotated[datetime.datetime, Field(description="Attempt start (UTC).")]
    finished_at: Annotated[datetime.datetime | None, Field(description="Attempt end (UTC).")]
    error_code: Annotated[str | None, Field(description="Error code, if the attempt failed or was interrupted.")]
    error_message: Annotated[str | None, Field(description="Error message, if the attempt failed.")]


class JobPage(_Contract):
    items: Annotated[list[JobView], Field(description="Jobs, newest first.")]
    total: Annotated[int, Field(description="Total jobs matching the filters.")]
    limit: Annotated[int, Field(description="Page size used.")]
    offset: Annotated[int, Field(description="Offset used.")]


class JobLogLineView(_Contract):
    id: Annotated[str, Field(description="Opaque, increasing line ID; pass as `after` to fetch newer lines.")]
    attempt_no: Annotated[int, Field(description="Attempt that wrote the line.")]
    ts: Annotated[datetime.datetime, Field(description="When the line was logged (UTC).")]
    message: Annotated[str, Field(description="Log text.")]


class JobLogPage(_Contract):
    lines: Annotated[list[JobLogLineView], Field(description="Log lines, oldest first.")]
    last_id: Annotated[str | None, Field(description="ID of the last line returned (or the `after` given if none).")]


class JobAccepted(_Contract):
    '''Returned with HTTP 202 when a job is queued.'''

    job_id: Annotated[str, Field(description="ID of the queued job.")]
    status: Annotated[str, Field(description="Initial status (normally `queued`).")]
    status_url: Annotated[str, Field(description="URL to poll for this job's status.")]


# --------------------------------------------------------------------------- media job requests

_PATH_DESC = "Directory relative to the gallery root (`.` for the root)."


class ReindexRequest(_Contract):
    '''Rescan a directory tree into the media index.'''

    path: Annotated[str, Field(description=_PATH_DESC)] = "."


class ThumbnailsRequest(_Contract):
    '''Generate animated GIF thumbnails for every video under a directory.'''

    path: Annotated[str, Field(description=_PATH_DESC)] = "."
    overwrite: Annotated[bool, Field(description="Regenerate thumbnails that already exist.")] = False
    workers: Annotated[int, Field(ge=1, le=16, description="Concurrent ffmpeg processes.")] = 2


class CleanupRequest(_Contract):
    '''Find (and optionally delete) empty, unprobable, or duplicate videos under a directory.'''

    path: Annotated[str, Field(description=_PATH_DESC)] = "."
    delete_empty: Annotated[bool, Field(description="Include zero-byte video files.")] = False
    delete_unprobable: Annotated[bool, Field(description="Include videos ffprobe cannot read.")] = False
    delete_duplicates: Annotated[bool, Field(description="Include byte-identical videos in the same directory (keeps the longest path).")] = False
    dry_run: Annotated[bool, Field(description="Only report what would be deleted. Set false to actually delete.")] = True

    @model_validator(mode="after")
    def _something_selected(self) -> CleanupRequest:
        if not (self.delete_empty or self.delete_unprobable or self.delete_duplicates):
            raise ValueError("Select at least one of delete_empty, delete_unprobable, delete_duplicates.")
        return self


class ConvertMp4Request(_Contract):
    '''Convert non-MP4 videos under a directory to MP4 alongside the originals.'''

    path: Annotated[str, Field(description=_PATH_DESC)] = "."


class MoveRequest(_Contract):
    '''Move a directory's contents into the gallery, then rescan the destination.'''

    source: Annotated[str, Field(description="Absolute source directory; must be inside a configured copy source root.")]
    dest: Annotated[str, Field(description="Destination directory relative to the gallery root; created if missing.")]
    workers: Annotated[int, Field(ge=1, le=32, description="Files transferred concurrently.")] = 4


# --------------------------------------------------------------------------- media job views

class MediaJobView(_Contract):
    '''A job together with its media-specific parameters and results.'''

    job: Annotated[JobView, Field(description="Generic lifecycle state.")]
    kind: Annotated[str, Field(description="Short task name: reindex, thumbnails, cleanup, convert_mp4, move.")]
    target: Annotated[str | None, Field(description="Target directory relative to the gallery root.")]
    params: Annotated[dict[str, JsonValue], Field(description="Parameters the job was submitted with.")]
    result: Annotated[dict[str, JsonValue] | None, Field(description="Handler-written result summary, once available.")]
    attempts: Annotated[list[JobAttemptView], Field(description="Execution attempts, oldest first.")]


class MediaJobPage(_Contract):
    items: Annotated[list[MediaJobView], Field(description="Media jobs, newest first.")]
    total: Annotated[int, Field(description="Total jobs matching the filters.")]
    limit: Annotated[int, Field(description="Page size used.")]
    offset: Annotated[int, Field(description="Offset used.")]


class JobConfigView(_Contract):
    '''Server capabilities the jobs UI needs.'''

    copy_source_roots: Annotated[list[str], Field(description="Directories that move jobs may read from. Empty disables move jobs.")]
    worker_enabled: Annotated[bool, Field(description="Whether this server process runs a job worker.")]
