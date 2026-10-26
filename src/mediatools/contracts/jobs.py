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


class MontageRequest(_Contract):
    '''Build one montage video from random clips of the videos found in the sources, optionally limited to a creation date range.'''

    sources: Annotated[list[str], Field(min_length=1, description="Absolute directories to search recursively; each must be inside the gallery root or a configured copy source root.")]
    start: Annotated[datetime.datetime | None, Field(description="Earliest `creation_time` tag to include (naive values are UTC). Omit for no lower bound.")] = None
    end: Annotated[datetime.datetime | None, Field(description="Latest `creation_time` tag to include (naive values are UTC). Omit for no upper bound.")] = None
    output: Annotated[str, Field(description="Output `.mp4` path relative to the gallery root.")]
    name_contains: Annotated[str | None, Field(description="Only consider files whose name contains this text (e.g. `GX` for GoPro).")] = None
    width: Annotated[int, Field(ge=16, le=7680, description="Output width in pixels.")] = 1920
    height: Annotated[int, Field(ge=16, le=4320, description="Output height in pixels.")] = 1080
    fps: Annotated[int, Field(ge=1, le=240, description="Output frames per second.")] = 30
    clip_ratio: Annotated[float | None, Field(gt=0, description="Alternative to `target_duration`: seconds of source video per clip (90 with 2 s clips is about 45x shorter).")] = None
    target_duration: Annotated[float | None, Field(gt=0, description="Desired montage length in seconds; clips are shared across videos in proportion to their length. Defaults to 600 unless `clip_ratio` is given.")] = 600
    clip_duration: Annotated[float, Field(gt=0, le=600, description="Length of each clip in seconds.")] = 2.0
    random_seed: Annotated[int, Field(description="Seed for clip selection.")] = 0
    max_clips_per_video: Annotated[int | None, Field(ge=1, description="Cap on clips taken from one video.")] = None
    max_total_clips: Annotated[int | None, Field(ge=1, description="Cap on clips in the montage.")] = None
    shuffle_clips: Annotated[bool, Field(description="Shuffle clip order instead of keeping chronological order.")] = False
    use_cuda: Annotated[bool, Field(description="Use CUDA acceleration.")] = False
    workers: Annotated[int, Field(ge=1, le=16, description="Concurrent clip encodes; each is multithreaded and uses substantial memory at high resolutions.")] = 2
    overwrite: Annotated[bool, Field(description="Replace the output file if it exists.")] = False

    @model_validator(mode="before")
    @classmethod
    def _default_sampling(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("clip_ratio") is not None and "target_duration" not in data:
            return {**data, "target_duration": None}
        return data

    @model_validator(mode="after")
    def _valid_range(self) -> MontageRequest:
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not be after end.")
        if (self.clip_ratio is None) == (self.target_duration is None):
            raise ValueError("Give exactly one of target_duration or clip_ratio.")
        if not self.output.lower().endswith(".mp4"):
            raise ValueError("output must end in .mp4.")
        return self


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
