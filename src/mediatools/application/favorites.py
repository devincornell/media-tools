from __future__ import annotations

import dataclasses
import re
from collections.abc import Collection
from typing import Protocol

from ..contracts import FavoriteState
from ..index_db import VideoFileNotFoundError
from .errors import MediaFileNotFoundError
from .gallery import VideoIndexReader

_HASH = re.compile(r"[A-Za-z0-9_-]+")


class FavoriteStore(Protocol):
    async def add(self, file_hash: str) -> None: ...
    async def remove(self, file_hash: str) -> None: ...
    async def among(self, file_hashes: Collection[str]) -> set[str]: ...
    async def list_all(self) -> list[str]: ...


@dataclasses.dataclass(frozen=True)
class FavoriteService:
    '''Star or unstar videos by index hash, so favorites survive moves, renames and re-indexing.'''

    store: FavoriteStore
    videos: VideoIndexReader

    async def add(self, file_hash: str) -> FavoriteState:
        if not _HASH.fullmatch(file_hash):
            raise MediaFileNotFoundError(f"Video not found: {file_hash}")
        try:
            await self.videos.find_by_hash(file_hash)
        except VideoFileNotFoundError:
            raise MediaFileNotFoundError(f"Video not found: {file_hash}") from None
        await self.store.add(file_hash)
        return FavoriteState(file_hash=file_hash, is_favorite=True)

    async def remove(self, file_hash: str) -> FavoriteState:
        # No index check, so favorites whose video left the index can still be cleared.
        await self.store.remove(file_hash)
        return FavoriteState(file_hash=file_hash, is_favorite=False)

    async def list_all(self) -> list[str]:
        return await self.store.list_all()
