from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid
from collections.abc import Collection

from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from .models import AttemptStatus, Job, JobStatus, utcnow


class LeaseLostError(Exception):
    '''The worker no longer holds the lease for this job (expired and reclaimed, or job finalized elsewhere).'''


def _clear_lease(now: datetime.datetime) -> dict[str, typing.Any]:
    return {"lease_token": None, "lease_expires_at": None, "updated_at": now}


@dataclasses.dataclass(frozen=True)
class MongoJobRepository:
    '''Persistence for generic jobs. Every state change is a single-document atomic update; no transactions needed.'''

    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "jobs") -> typing.Self:
        return cls(database[collection_name])

    async def create_indexes(self) -> None:
        await self._collection.create_index([("scope_id", 1), ("created_at", -1)])
        await self._collection.create_index([("status", 1), ("available_at", 1), ("created_at", 1)])
        await self._collection.create_index([("status", 1), ("lease_expires_at", 1)])

    async def insert(self, job: Job) -> None:
        doc = job.model_dump(by_alias=True, exclude={"attempts"})
        doc |= {"status": job.status.value, "attempts": []}
        await self._collection.insert_one(doc)

    async def get(self, job_id: str, scope_id: str | None = None) -> Job | None:
        query: dict[str, typing.Any] = {"_id": job_id}
        if scope_id is not None:
            query["scope_id"] = scope_id
        doc = await self._collection.find_one(query)
        return Job.model_validate(doc) if doc else None

    async def list(
        self,
        scope_id: str,
        *,
        status: JobStatus | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        query: dict[str, typing.Any] = {"scope_id": scope_id}
        if status is not None:
            query["status"] = status.value
        if job_type is not None:
            query["job_type"] = job_type
        total = await self._collection.count_documents(query)
        cursor = self._collection.find(query).sort([("created_at", -1), ("_id", 1)]).skip(offset).limit(limit)
        return [Job.model_validate(doc) async for doc in cursor], total

    async def claim(
        self, worker_id: str, lease_seconds: float, job_types: Collection[str], scope_id: str | None = None
    ) -> Job | None:
        '''Atomically claim the oldest eligible queued job, start a new attempt, and return it.'''
        now = utcnow()
        next_attempt = {"$add": ["$attempt_count", 1]}
        query: dict[str, typing.Any] = {
            "status": JobStatus.QUEUED.value,
            "available_at": {"$lte": now},
            "cancel_requested_at": None,
            "job_type": {"$in": list(job_types)},
        }
        if scope_id is not None:
            query["scope_id"] = scope_id
        doc = await self._collection.find_one_and_update(
            query,
            [
                {
                    "$set": {
                        "status": JobStatus.RUNNING.value,
                        "lease_token": str(uuid.uuid4()),
                        "lease_expires_at": now + datetime.timedelta(seconds=lease_seconds),
                        "attempt_count": next_attempt,
                        "started_at": {"$ifNull": ["$started_at", now]},
                        "updated_at": now,
                        "attempts": {
                            "$concatArrays": [
                                {"$ifNull": ["$attempts", []]},
                                [
                                    {
                                        "attempt_no": next_attempt,
                                        "worker_id": {"$literal": worker_id},
                                        "status": AttemptStatus.RUNNING.value,
                                        "started_at": now,
                                        "finished_at": None,
                                        "error_code": None,
                                        "error_message": None,
                                    }
                                ],
                            ]
                        },
                    }
                }
            ],
            sort=[("available_at", 1), ("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return Job.model_validate(doc) if doc else None

    async def _update_leased(
        self,
        job: Job,
        update: dict[str, typing.Any],
        attempt_update: dict[str, typing.Any] | None = None,
    ) -> Job:
        '''Apply `update` only if `job`'s lease is still current; raise LeaseLostError otherwise.'''
        set_fields = dict(update)
        for key, value in (attempt_update or {}).items():
            set_fields[f"attempts.$[a].{key}"] = value
        doc = await self._collection.find_one_and_update(
            {"_id": job.id, "lease_token": job.lease_token, "status": JobStatus.RUNNING.value},
            {"$set": set_fields},
            array_filters=[{"a.attempt_no": job.attempt_count}] if attempt_update else None,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise LeaseLostError(f"Lease lost for job {job.id}")
        return Job.model_validate(doc)

    async def renew_lease(self, job: Job, lease_seconds: float) -> Job:
        now = utcnow()
        return await self._update_leased(
            job, {"lease_expires_at": now + datetime.timedelta(seconds=lease_seconds), "updated_at": now}
        )

    async def update_progress(self, job: Job, percent: int | None, stage: str | None) -> Job:
        return await self._update_leased(
            job, {"progress_percent": percent, "progress_stage": stage, "updated_at": utcnow()}
        )

    async def complete(self, job: Job, result_ref: str | None = None) -> Job:
        now = utcnow()
        return await self._update_leased(
            job,
            {
                **_clear_lease(now),
                "status": JobStatus.SUCCEEDED.value,
                "result_ref": result_ref,
                "progress_percent": 100,
                "finished_at": now,
                "error_code": None,
                "error_message": None,
            },
            {"status": AttemptStatus.SUCCEEDED.value, "finished_at": now},
        )

    async def fail(
        self, job: Job, error_code: str, error_message: str, retry_at: datetime.datetime | None
    ) -> Job:
        '''Record a failed attempt; requeue at `retry_at`, or fail the job permanently if it is None.'''
        now = utcnow()
        update: dict[str, typing.Any] = {**_clear_lease(now), "error_code": error_code, "error_message": error_message}
        if retry_at is None:
            update |= {"status": JobStatus.FAILED.value, "finished_at": now}
        else:
            update |= {"status": JobStatus.QUEUED.value, "available_at": retry_at}
        return await self._update_leased(
            job,
            update,
            {"status": AttemptStatus.FAILED.value, "finished_at": now, "error_code": error_code, "error_message": error_message},
        )

    async def confirm_cancel(self, job: Job) -> Job:
        now = utcnow()
        return await self._update_leased(
            job,
            {**_clear_lease(now), "status": JobStatus.CANCELED.value, "finished_at": now},
            {"status": AttemptStatus.CANCELED.value, "finished_at": now},
        )

    async def release(self, job: Job) -> Job:
        '''Give a running job back to the queue immediately (e.g. on worker shutdown).'''
        now = utcnow()
        return await self._update_leased(
            job,
            {**_clear_lease(now), "status": JobStatus.QUEUED.value, "available_at": now},
            {"status": AttemptStatus.INTERRUPTED.value, "finished_at": now},
        )

    async def request_cancel(self, job_id: str, scope_id: str) -> Job | None:
        '''Cancel a queued job immediately, or flag a running job for cooperative cancellation.'''
        now = utcnow()
        doc = await self._collection.find_one_and_update(
            {"_id": job_id, "scope_id": scope_id, "status": JobStatus.QUEUED.value},
            {"$set": {"status": JobStatus.CANCELED.value, "cancel_requested_at": now, "finished_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            doc = await self._collection.find_one_and_update(
                {"_id": job_id, "scope_id": scope_id, "status": JobStatus.RUNNING.value, "cancel_requested_at": None},
                {"$set": {"cancel_requested_at": now, "updated_at": now}},
                return_document=ReturnDocument.AFTER,
            )
        if doc is None:
            return await self.get(job_id, scope_id)
        return Job.model_validate(doc)

    async def recover_expired(self) -> int:
        '''Mark attempts with expired leases as interrupted, then requeue, cancel, or fail their jobs.'''
        now = utcnow()
        recovered = 0
        cursor = self._collection.find({"status": JobStatus.RUNNING.value, "lease_expires_at": {"$lt": now}})
        async for doc in cursor:
            job = Job.model_validate(doc)
            update: dict[str, typing.Any] = _clear_lease(now)
            if job.cancel_requested_at is not None:
                update |= {"status": JobStatus.CANCELED.value, "finished_at": now}
            elif job.attempt_count >= job.max_attempts:
                update |= {
                    "status": JobStatus.FAILED.value,
                    "finished_at": now,
                    "error_code": "lease_expired",
                    "error_message": "Worker stopped responding and no attempts remain.",
                }
            else:
                update |= {"status": JobStatus.QUEUED.value, "available_at": now}
            update |= {
                "attempts.$[a].status": AttemptStatus.INTERRUPTED.value,
                "attempts.$[a].finished_at": now,
                "attempts.$[a].error_code": "lease_expired",
            }
            result = await self._collection.update_one(
                {"_id": job.id, "lease_token": job.lease_token, "status": JobStatus.RUNNING.value},
                {"$set": update},
                array_filters=[{"a.attempt_no": job.attempt_count}],
            )
            recovered += result.modified_count
        return recovered


__all__ = ["LeaseLostError", "MongoJobRepository"]
