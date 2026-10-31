from __future__ import annotations

import dataclasses
import datetime
import re
import typing
from collections.abc import Collection

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase


@dataclasses.dataclass(frozen=True)
class FavoriteCollection:
    '''Starred videos, one document per video index hash (`_id`). Independent of the video index, so favorites outlive it.'''

    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "favorites") -> typing.Self:
        return cls(database[collection_name])

    async def add(self, file_hash: str) -> None:
        '''Idempotent: re-adding keeps the original `created_at`.'''
        await self._collection.update_one(
            {"_id": file_hash},
            {"$setOnInsert": {"created_at": datetime.datetime.now(datetime.UTC)}},
            upsert=True,
        )

    async def remove(self, file_hash: str) -> None:
        await self._collection.delete_one({"_id": file_hash})

    async def among(self, file_hashes: Collection[str]) -> set[str]:
        '''The subset of `file_hashes` that are favorites.'''
        if not file_hashes:
            return set()
        cursor = self._collection.find({"_id": {"$in": list(file_hashes)}}, {"_id": 1})
        return {doc["_id"] async for doc in cursor}

    async def list_all(self) -> list[str]:
        cursor = self._collection.find({}, {"_id": 1}).sort("created_at", -1)
        return [doc["_id"] async for doc in cursor]

    @staticmethod
    def _at_or_under(key: str) -> dict[str, typing.Any]:
        return {"_id": {"$regex": f"^{re.escape(key)}(/|$)"}}

    async def move_prefix(self, old: str, new: str) -> int:
        '''Re-key path-keyed favorites at or beneath `old` to the same place beneath `new`, keeping `created_at`.'''
        docs = [doc async for doc in self._collection.find(self._at_or_under(old))]
        for doc in docs:
            await self._collection.update_one(
                {"_id": new + doc["_id"][len(old):]},
                {"$setOnInsert": {"created_at": doc.get("created_at") or datetime.datetime.now(datetime.UTC)}},
                upsert=True,
            )
        if docs:
            await self._collection.delete_many({"_id": {"$in": [doc["_id"] for doc in docs]}})
        return len(docs)

    async def remove_prefix(self, key: str) -> int:
        '''Remove path-keyed favorites at or beneath `key`.'''
        result = await self._collection.delete_many(self._at_or_under(key))
        return result.deleted_count
