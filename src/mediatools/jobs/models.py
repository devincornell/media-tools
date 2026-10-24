from __future__ import annotations

import datetime
import enum
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    # pymongo returns naive UTC datetimes unless the client is tz_aware.
    return value.replace(tzinfo=datetime.UTC) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime.datetime, AfterValidator(_as_utc)]


def new_job_id() -> str:
    return str(uuid.uuid4())


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED)


class AttemptStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELED = "canceled"


class JobAttempt(BaseModel):
    '''One execution attempt; stored inside its job document so claim + attempt creation is a single atomic write.'''

    model_config = ConfigDict(extra="ignore")

    attempt_no: int = Field(ge=1)
    worker_id: str | None = None
    status: AttemptStatus
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class Job(BaseModel):
    '''Generic job lifecycle state. Application data lives elsewhere, keyed by `id`.'''

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: Annotated[str, Field(alias="_id")]
    job_type: str
    scope_id: str
    status: JobStatus = JobStatus.QUEUED
    request_ref: str | None = None
    result_ref: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    progress_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    available_at: UtcDatetime
    lease_token: str | None = None
    lease_expires_at: UtcDatetime | None = None
    cancel_requested_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    attempts: list[JobAttempt] = Field(default_factory=list)
