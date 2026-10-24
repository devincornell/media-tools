from __future__ import annotations

import dataclasses
import datetime
import typing

import bson
from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from .models import UtcDatetime


class JobLogLine(BaseModel):
    id: str
    attempt_no: int
    ts: UtcDatetime
    message: str


@dataclasses.dataclass(frozen=True)
class MongoJobLogStore:
    '''Append-only log lines per job, kept outside the job document so long jobs don't bloat it.'''

    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "job_logs") -> typing.Self:
        return cls(database[collection_name])

    async def create_indexes(self, retention_days: float = 30) -> None:
        await self._collection.create_index([("job_id", 1), ("_id", 1)])
        await self._collection.create_index("ts", expireAfterSeconds=int(retention_days * 86400))

    async def append(self, job_id: str, attempt_no: int, lines: list[tuple[datetime.datetime, str]]) -> None:
        if lines:
            await self._collection.insert_many(
                [{"job_id": job_id, "attempt_no": attempt_no, "ts": ts, "message": msg} for ts, msg in lines],
                ordered=True,
            )

    async def read(self, job_id: str, after: str | None = None, limit: int = 500) -> list[JobLogLine]:
        '''Lines after the line ID `after` (oldest first), or the last `limit` lines if `after` is None.'''
        if after is None:
            cursor = self._collection.find({"job_id": job_id}).sort("_id", -1).limit(limit)
            docs = [d async for d in cursor][::-1]
        else:
            query = {"job_id": job_id, "_id": {"$gt": bson.ObjectId(after)}}
            docs = [d async for d in self._collection.find(query).sort("_id", 1).limit(limit)]
        return [
            JobLogLine(id=str(d["_id"]), attempt_no=d["attempt_no"], ts=d["ts"], message=d["message"]) for d in docs
        ]
