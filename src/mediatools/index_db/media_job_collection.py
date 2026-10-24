from __future__ import annotations

import dataclasses
import typing
from typing import Annotated

import pydantic
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase


class MediaJobRecord(pydantic.BaseModel):
    '''Media-specific data for one job; `_id` is the generic job ID (one-to-one).'''

    model_config = pydantic.ConfigDict(populate_by_name=True, extra="ignore")

    job_id: Annotated[str, pydantic.Field(alias="_id")]
    job_type: str
    target_path: str | None
    params: dict[str, pydantic.JsonValue]
    result: dict[str, pydantic.JsonValue] | None = None


@dataclasses.dataclass(frozen=True)
class MediaJobCollection:
    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "media_jobs") -> typing.Self:
        return cls(database[collection_name])

    async def insert(self, record: MediaJobRecord) -> None:
        await self._collection.insert_one(record.model_dump(by_alias=True))

    async def get(self, job_id: str) -> MediaJobRecord | None:
        doc = await self._collection.find_one({"_id": job_id})
        return MediaJobRecord.model_validate(doc) if doc else None

    async def get_many(self, job_ids: typing.Iterable[str]) -> dict[str, MediaJobRecord]:
        cursor = self._collection.find({"_id": {"$in": list(job_ids)}})
        return {doc["_id"]: MediaJobRecord.model_validate(doc) async for doc in cursor}

    async def set_result(self, job_id: str, result: dict[str, pydantic.JsonValue]) -> None:
        '''Idempotent: a retried attempt simply overwrites the previous result.'''
        await self._collection.update_one({"_id": job_id}, {"$set": {"result": result}})
