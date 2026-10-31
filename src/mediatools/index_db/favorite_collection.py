from __future__ import annotations

import dataclasses
import datetime
import typing
from collections.abc import Collection

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase


@dataclasses.dataclass(frozen=True)
class FavoriteCollection:
    '''Starred media files, one document per path relative to the gallery root (`_id`).'''

    _collection: AsyncCollection

    @classmethod
    def from_database(cls, database: AsyncDatabase, collection_name: str = "favorites") -> typing.Self:
        return cls(database[collection_name])

    async def add(self, rel_path: str) -> None:
        '''Idempotent: re-adding keeps the original `created_at`.'''
        await self._collection.update_one(
            {"_id": rel_path},
            {"$setOnInsert": {"created_at": datetime.datetime.now(datetime.UTC)}},
            upsert=True,
        )

    async def remove(self, rel_path: str) -> None:
        await self._collection.delete_one({"_id": rel_path})

    async def among(self, rel_paths: Collection[str]) -> set[str]:
        '''The subset of `rel_paths` that are favorites.'''
        if not rel_paths:
            return set()
        cursor = self._collection.find({"_id": {"$in": list(rel_paths)}}, {"_id": 1})
        return {doc["_id"] async for doc in cursor}

    async def list_all(self) -> list[str]:
        cursor = self._collection.find({}, {"_id": 1}).sort("created_at", -1)
        return [doc["_id"] async for doc in cursor]
