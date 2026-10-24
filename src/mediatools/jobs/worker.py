from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import logging
import os
import socket
import time
import typing
import uuid
from collections.abc import Callable, Mapping

from .logs import MongoJobLogStore
from .models import Job, utcnow
from .repository import LeaseLostError, MongoJobRepository

logger = logging.getLogger(__name__)

_T = typing.TypeVar("_T")


class JobCanceled(Exception):
    '''Raised by a handler (via JobContext) to stop cooperatively after a cancel request.'''


class PermanentJobError(Exception):
    '''A failure that retrying will not fix (bad input, missing directory, ...).'''

    def __init__(self, message: str, code: str = "permanent_error"):
        super().__init__(message)
        self.code = code


class JobContext:
    '''Handed to handlers for progress reporting, logging, and cancellation checks.'''

    def __init__(
        self,
        job: Job,
        repo: MongoJobRepository,
        logs: MongoJobLogStore | None = None,
        progress_interval: float = 1.0,
    ):
        self.job = job
        self.lease_lost = False
        self._repo = repo
        self._logs = logs
        self._log_buffer: list[tuple[datetime.datetime, str]] = []
        self._progress_interval = progress_interval
        self._last_write = 0.0

    @property
    def job_id(self) -> str:
        return self.job.id

    @property
    def cancel_requested(self) -> bool:
        return self.job.cancel_requested_at is not None

    def log(self, message: str) -> None:
        '''Queue a log line; lines are written in batches at checkpoints.'''
        self._log_buffer.append((utcnow(), message))

    async def flush_logs(self) -> None:
        if self._logs is not None and self._log_buffer:
            lines, self._log_buffer = self._log_buffer, []
            await self._logs.append(self.job_id, self.job.attempt_count, lines)

    async def checkpoint(self, percent: float | None = None, stage: str | None = None, *, force: bool = False) -> None:
        '''Report progress and flush logs (throttled); raise JobCanceled if cancellation was requested.'''
        now = time.monotonic()
        if force or now - self._last_write >= self._progress_interval:
            pct = None if percent is None else max(0, min(100, int(percent)))
            self.job = await self._repo.update_progress(self.job, pct, stage)
            await self.flush_logs()
            self._last_write = now
        if self.cancel_requested:
            raise JobCanceled()


class JobHandler(typing.Protocol):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        '''Load application data for `job_id`, do the work, persist results; optionally return a result_ref.'''
        ...


def default_backoff(attempt_no: int) -> float:
    return float(min(300, 10 * 2 ** (attempt_no - 1)))


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


@dataclasses.dataclass
class JobWorker:
    '''Claims queued jobs, runs their handlers, and manages leases, retries, and cancellation.'''

    repo: MongoJobRepository
    handlers: Mapping[str, JobHandler]
    scope_id: str | None = None
    logs: MongoJobLogStore | None = None
    worker_id: str = dataclasses.field(default_factory=default_worker_id)
    lease_seconds: float = 60.0
    poll_interval: float = 2.0
    concurrency: int = 1
    backoff: Callable[[int], float] = default_backoff

    async def run(self, stop: asyncio.Event) -> None:
        '''Process jobs until `stop` is set; running jobs are then released back to the queue.'''
        running: set[asyncio.Task[None]] = set()
        last_recovery = 0.0
        stop_wait = asyncio.create_task(stop.wait())
        try:
            while not stop.is_set():
                if time.monotonic() - last_recovery >= self.lease_seconds / 2:
                    await self._safe(self.repo.recover_expired())
                    last_recovery = time.monotonic()
                while len(running) < self.concurrency:
                    job = await self._safe(self._claim())
                    if job is None:
                        break
                    task = asyncio.create_task(self._execute(job))
                    running.add(task)
                    task.add_done_callback(running.discard)
                await asyncio.wait({stop_wait, *running}, timeout=self.poll_interval, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop_wait.cancel()
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    async def run_once(self) -> Job | None:
        '''Recover expired leases, then claim and fully execute at most one job. Returns the claimed job.'''
        await self.repo.recover_expired()
        job = await self._claim()
        if job is not None:
            await self._execute(job)
        return job

    async def _claim(self) -> Job | None:
        return await self.repo.claim(self.worker_id, self.lease_seconds, self.handlers.keys(), self.scope_id)

    async def _execute(self, job: Job) -> None:
        ctx = JobContext(job, self.repo, self.logs)
        ctx.log(f"Attempt {job.attempt_count}/{job.max_attempts} started on {self.worker_id}")
        handler_task = asyncio.create_task(self.handlers[job.job_type].execute(job.id, ctx))
        lease_task = asyncio.create_task(self._keep_lease(ctx, handler_task))
        try:
            result_ref = await handler_task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                ctx.log("Worker shutting down; job returned to the queue")
                if not ctx.lease_lost:
                    await self._safe(self.repo.release(ctx.job))
                raise
            ctx.log("Lease lost; another worker will resume this job")
            logger.warning("Lease lost for job %s; abandoning attempt %s", job.id, job.attempt_count)
        except LeaseLostError:
            ctx.log("Lease lost; another worker will resume this job")
            logger.warning("Lease lost for job %s; abandoning attempt %s", job.id, job.attempt_count)
        except JobCanceled:
            ctx.log("Canceled")
            await self._safe(self.repo.confirm_cancel(ctx.job))
        except PermanentJobError as e:
            ctx.log(f"Failed: {e}")
            await self._safe(self.repo.fail(ctx.job, e.code, str(e), retry_at=None))
        except Exception as e:
            logger.exception("Job %s (%s) attempt %s failed", job.id, job.job_type, job.attempt_count)
            retry_at = self._retry_at(ctx.job)
            ctx.log(f"Error: {type(e).__name__}: {e}" + (
                f"; retrying at {retry_at:%H:%M:%S} UTC" if retry_at else "; no attempts left"))
            await self._safe(self.repo.fail(ctx.job, type(e).__name__, str(e), retry_at=retry_at))
        else:
            ctx.log("Finished")
            await self._safe(self.repo.complete(ctx.job, result_ref))
        finally:
            lease_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease_task
            await self._safe(ctx.flush_logs())

    def _retry_at(self, job: Job) -> datetime.datetime | None:
        if job.attempt_count >= job.max_attempts:
            return None
        return utcnow() + datetime.timedelta(seconds=self.backoff(job.attempt_count))

    async def _keep_lease(self, ctx: JobContext, handler_task: asyncio.Task[typing.Any]) -> None:
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            try:
                ctx.job = await self.repo.renew_lease(ctx.job, self.lease_seconds)
            except LeaseLostError:
                ctx.lease_lost = True
                handler_task.cancel()
                return
            except Exception:
                logger.exception("Lease renewal failed for job %s; will retry", ctx.job_id)

    @staticmethod
    async def _safe(coro: typing.Awaitable[_T]) -> _T | None:
        '''Await a bookkeeping call, logging instead of crashing the worker loop.'''
        try:
            return await coro
        except LeaseLostError:
            logger.warning("Lease lost while finalizing job")
        except Exception:
            logger.exception("Job bookkeeping failed")
        return None
