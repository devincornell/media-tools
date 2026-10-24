"""Integration tests for the generic job subsystem. Needs a disposable MongoDB at TEST_MONGODB_URL."""
from __future__ import annotations

import asyncio
import datetime
import os
import uuid
from collections.abc import Awaitable, Callable

import pymongo
import pytest

from mediatools.jobs import (
    AttemptStatus,
    JobCanceled,
    JobContext,
    JobManager,
    JobNotFoundError,
    JobStatus,
    JobWorker,
    LeaseLostError,
    MongoJobRepository,
    PermanentJobError,
)

MONGO_URL = os.environ.get("TEST_MONGODB_URL")
pytestmark = pytest.mark.skipif(not MONGO_URL, reason="TEST_MONGODB_URL not set")


def run_with_repo(body: Callable[[MongoJobRepository], Awaitable[None]]) -> None:
    async def main() -> None:
        db_name = f"test_jobs_{uuid.uuid4().hex[:8]}"
        client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(MONGO_URL)
        try:
            repo = MongoJobRepository.from_database(client[db_name])
            await repo.create_indexes()
            await body(repo)
        finally:
            await client.drop_database(db_name)
            await client.aclose()

    asyncio.run(main())


class FnHandler:
    def __init__(self, fn: Callable[[str, JobContext], Awaitable[str | None]]):
        self.fn = fn
        self.calls = 0

    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        self.calls += 1
        return await self.fn(job_id, ctx)


def worker(repo: MongoJobRepository, **handlers: FnHandler) -> JobWorker:
    return JobWorker(repo, handlers, lease_seconds=30, poll_interval=0.05, backoff=lambda n: 0.0)


def test_submit_get_list_and_scope():
    async def body(repo: MongoJobRepository) -> None:
        a, b = JobManager(repo, "scope-a"), JobManager(repo, "scope-b")
        job = await a.submit("t.v1", request_ref="req-1")
        assert (await a.get(job.id)).request_ref == "req-1"
        with pytest.raises(JobNotFoundError):
            await b.get(job.id)
        with pytest.raises(JobNotFoundError):
            await b.cancel(job.id)
        jobs, total = await a.list()
        assert total == 1 and jobs[0].id == job.id and jobs[0].status is JobStatus.QUEUED
        assert (await b.list())[1] == 0

    run_with_repo(body)


def test_concurrent_claims_are_exclusive():
    async def body(repo: MongoJobRepository) -> None:
        job = await JobManager(repo, "s").submit("t.v1")
        claims = await asyncio.gather(*(repo.claim(f"w{i}", 30, ["t.v1"]) for i in range(20)))
        won = [c for c in claims if c is not None]
        assert len(won) == 1
        claimed = won[0]
        assert claimed.id == job.id and claimed.status is JobStatus.RUNNING and claimed.attempt_count == 1
        assert [(a.attempt_no, a.status) for a in claimed.attempts] == [(1, AttemptStatus.RUNNING)]
        assert claimed.lease_token and claimed.started_at
        assert await repo.claim("w", 30, ["other.v1"]) is None

    run_with_repo(body)


def test_success_records_result_and_progress():
    async def body(repo: MongoJobRepository) -> None:
        async def fn(job_id: str, ctx: JobContext) -> str:
            await ctx.checkpoint(50, "halfway", force=True)
            assert (await repo.get(job_id)).progress_stage == "halfway"
            return "result-1"

        job = await JobManager(repo, "s").submit("t.v1")
        await worker(repo, **{"t.v1": FnHandler(fn)}).run_once()
        done = await repo.get(job.id)
        assert done.status is JobStatus.SUCCEEDED and done.result_ref == "result-1"
        assert done.progress_percent == 100 and done.finished_at and done.lease_token is None
        assert done.attempts[0].status is AttemptStatus.SUCCEEDED

    run_with_repo(body)


def test_transient_failure_retries_and_keeps_attempt_errors():
    async def body(repo: MongoJobRepository) -> None:
        async def fn(job_id: str, ctx: JobContext) -> None:
            if ctx.job.attempt_count == 1:
                raise RuntimeError("flaky")

        job = await JobManager(repo, "s").submit("t.v1")
        w = worker(repo, **{"t.v1": FnHandler(fn)})
        await w.run_once()
        mid = await repo.get(job.id)
        assert mid.status is JobStatus.QUEUED and mid.error_message == "flaky"
        await w.run_once()
        done = await repo.get(job.id)
        assert done.status is JobStatus.SUCCEEDED and done.attempt_count == 2
        assert [a.status for a in done.attempts] == [AttemptStatus.FAILED, AttemptStatus.SUCCEEDED]
        assert done.attempts[0].error_code == "RuntimeError"

    run_with_repo(body)


def test_permanent_and_exhausted_failures():
    async def body(repo: MongoJobRepository) -> None:
        async def permanent(job_id: str, ctx: JobContext) -> None:
            raise PermanentJobError("bad input", code="bad_input")

        async def always(job_id: str, ctx: JobContext) -> None:
            raise RuntimeError("boom")

        m = JobManager(repo, "s")
        p = await m.submit("perm.v1")
        e = await m.submit("always.v1", max_attempts=2)
        w = worker(repo, **{"perm.v1": FnHandler(permanent), "always.v1": FnHandler(always)})
        for _ in range(4):
            await w.run_once()
        p_done, e_done = await repo.get(p.id), await repo.get(e.id)
        assert p_done.status is JobStatus.FAILED and p_done.attempt_count == 1 and p_done.error_code == "bad_input"
        assert e_done.status is JobStatus.FAILED and e_done.attempt_count == 2

    run_with_repo(body)


def test_expired_lease_recovered_and_stale_worker_cannot_finalize():
    async def body(repo: MongoJobRepository) -> None:
        job = await JobManager(repo, "s").submit("t.v1")
        stale = await repo.claim("old", 30, ["t.v1"])
        await repo._collection.update_one(
            {"_id": job.id}, {"$set": {"lease_expires_at": datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)}}
        )
        assert await repo.recover_expired() == 1
        requeued = await repo.get(job.id)
        assert requeued.status is JobStatus.QUEUED and requeued.attempts[0].status is AttemptStatus.INTERRUPTED

        fresh = await repo.claim("new", 30, ["t.v1"])
        assert fresh.attempt_count == 2
        with pytest.raises(LeaseLostError):
            await repo.complete(stale, "stale-result")
        with pytest.raises(LeaseLostError):
            await repo.update_progress(stale, 10, "x")
        await repo.complete(fresh, "fresh-result")
        done = await repo.get(job.id)
        assert done.result_ref == "fresh-result"
        assert [a.status for a in done.attempts] == [AttemptStatus.INTERRUPTED, AttemptStatus.SUCCEEDED]

    run_with_repo(body)


def test_cancel_queued_and_running():
    async def body(repo: MongoJobRepository) -> None:
        m = JobManager(repo, "s")
        queued = await m.submit("t.v1")
        assert (await m.cancel(queued.id)).status is JobStatus.CANCELED
        assert await repo.claim("w", 30, ["t.v1"]) is None

        started = asyncio.Event()

        async def loop_forever(job_id: str, ctx: JobContext) -> None:
            started.set()
            while True:
                await ctx.checkpoint(1, "looping", force=True)
                await asyncio.sleep(0.01)

        running = await m.submit("t.v1")
        run = asyncio.create_task(worker(repo, **{"t.v1": FnHandler(loop_forever)}).run_once())
        await started.wait()
        assert (await m.cancel(running.id)).status is JobStatus.RUNNING
        await asyncio.wait_for(run, 5)
        done = await repo.get(running.id)
        assert done.status is JobStatus.CANCELED and done.attempts[0].status is AttemptStatus.CANCELED

    run_with_repo(body)


def test_worker_shutdown_releases_running_job():
    async def body(repo: MongoJobRepository) -> None:
        started = asyncio.Event()

        async def block(job_id: str, ctx: JobContext) -> None:
            started.set()
            await asyncio.sleep(3600)

        job = await JobManager(repo, "s").submit("t.v1")
        stop = asyncio.Event()
        run = asyncio.create_task(worker(repo, **{"t.v1": FnHandler(block)}).run(stop))
        await asyncio.wait_for(started.wait(), 5)
        stop.set()
        await asyncio.wait_for(run, 5)
        released = await repo.get(job.id)
        assert released.status is JobStatus.QUEUED and released.lease_token is None
        assert released.attempts[0].status is AttemptStatus.INTERRUPTED

    run_with_repo(body)


def test_handler_cancel_exception_is_cooperative():
    async def body(repo: MongoJobRepository) -> None:
        async def fn(job_id: str, ctx: JobContext) -> None:
            raise JobCanceled()

        job = await JobManager(repo, "s").submit("t.v1")
        await worker(repo, **{"t.v1": FnHandler(fn)}).run_once()
        assert (await repo.get(job.id)).status is JobStatus.CANCELED

    run_with_repo(body)
