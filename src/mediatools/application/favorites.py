from __future__ import annotations

import dataclasses
import re
from collections.abc import Collection
from pathlib import Path
from typing import Protocol

from ..contracts import FavoriteState, FolderFavoriteState
from ..index_db import MediaDirIndexNotFoundError, VideoFileNotFoundError
from .errors import DirectoryNotIndexedError, MediaFileNotFoundError
from .gallery import DirectoryIndexReader, VideoIndexReader
from .paths import resolve_under_root

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


@dataclasses.dataclass(frozen=True)
class FolderFavoriteService:
    '''Star or unstar folders by path relative to the gallery root (folders have no content hash).'''

    root_path: Path
    store: FavoriteStore
    dirs: DirectoryIndexReader

    async def add(self, rel_path: str) -> FolderFavoriteState:
        path = resolve_under_root(self.root_path, rel_path)
        try:
            doc = await self.dirs.find_by_path(path)
        except MediaDirIndexNotFoundError:
            doc = None
        if doc is None:
            raise DirectoryNotIndexedError(f"Folder not found: {rel_path}")
        key = str(path.relative_to(self.root_path))
        await self.store.add(key)
        return FolderFavoriteState(path=key, is_favorite=True)

    async def remove(self, rel_path: str) -> FolderFavoriteState:
        # No index check, so favorites of folders that were removed can still be cleared.
        key = str(resolve_under_root(self.root_path, rel_path).relative_to(self.root_path))
        await self.store.remove(key)
        return FolderFavoriteState(path=key, is_favorite=False)

    async def list_all(self) -> list[str]:
        return await self.store.list_all()
