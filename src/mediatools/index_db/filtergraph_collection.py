from __future__ import annotations

import dataclasses
import datetime
import typing
from typing import Annotated

import pydantic
import pymongo.errors
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    return value.replace(tzinfo=datetime.UTC) if value.tzinfo is None else value


class FilterGraphRecord(pydantic.BaseModel):
    '''A saved studio filtergraph. `graph` is the editor document; `uses` lists embedded saved graphs.'''

    model_config = pydantic.ConfigDict(populate_by_name=True, extra="ignore")

    id: Annotated[str, pydantic.Field(alias="_id")]
    name: str
    name_key: str
    description: str = ""
    tags: list[str] = []
    graph: dict[str, pydantic.JsonValue]
    uses: list[str] = []
    revision: int = 1
    created_at: Annotated[datetime.datetime, pydantic.AfterValidator(_as_utc)]
    updated_at: Annotated[datetime.datetime, pydantic.AfterValidator(_as_utc)]


class GraphNameTakenError(Exception):
    '''Another saved graph already has this name.'''


@dataclasses.dataclass(frozen=True)
class FilterGraphCollection:
    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "studio_graphs") -> typing.Self:
        return cls(database[collection_name])

    async def create_indexes(self) -> None:
        await self._collection.create_index("name_key", unique=True)
        await self._collection.create_index("uses")

    async def list_all(self) -> list[FilterGraphRecord]:
        cursor = self._collection.find({}).sort([("updated_at", -1), ("_id", 1)])
        return [FilterGraphRecord.model_validate(doc) async for doc in cursor]

    async def get(self, graph_id: str) -> FilterGraphRecord | None:
        doc = await self._collection.find_one({"_id": graph_id})
        return FilterGraphRecord.model_validate(doc) if doc else None

    async def get_many(self, graph_ids: typing.Iterable[str]) -> dict[str, FilterGraphRecord]:
        cursor = self._collection.find({"_id": {"$in": list(graph_ids)}})
        return {doc["_id"]: FilterGraphRecord.model_validate(doc) async for doc in cursor}

    async def find_by_name(self, name_key: str) -> FilterGraphRecord | None:
        doc = await self._collection.find_one({"name_key": name_key})
        return FilterGraphRecord.model_validate(doc) if doc else None

    async def insert(self, record: FilterGraphRecord) -> None:
        try:
            await self._collection.insert_one(record.model_dump(by_alias=True))
        except pymongo.errors.DuplicateKeyError as e:
            raise GraphNameTakenError(record.name) from e

    async def replace(self, record: FilterGraphRecord, expected_revision: int) -> bool:
        '''Store `record` if the stored revision is still `expected_revision`; False if it changed meanwhile.'''
        try:
            result = await self._collection.replace_one(
                {"_id": record.id, "revision": expected_revision}, record.model_dump(by_alias=True),
            )
        except pymongo.errors.DuplicateKeyError as e:
            raise GraphNameTakenError(record.name) from e
        return result.matched_count == 1

    async def delete(self, graph_id: str) -> bool:
        result = await self._collection.delete_one({"_id": graph_id})
        return result.deleted_count == 1

    async def used_by(self, graph_id: str) -> list[FilterGraphRecord]:
        cursor = self._collection.find({"uses": graph_id})
        return [FilterGraphRecord.model_validate(doc) async for doc in cursor]
