from __future__ import annotations

import dataclasses
from collections.abc import Collection
from pathlib import Path
from typing import Protocol

from ..contracts import FavoriteState
from .errors import MediaFileNotFoundError
from .paths import resolve_under_root


class FavoriteStore(Protocol):
    async def add(self, rel_path: str) -> None: ...
    async def remove(self, rel_path: str) -> None: ...
    async def among(self, rel_paths: Collection[str]) -> set[str]: ...
    async def list_all(self) -> list[str]: ...


@dataclasses.dataclass(frozen=True)
class FavoriteService:
    '''Star or unstar media files, identified by their path relative to the gallery root.'''

    root_path: Path
    store: FavoriteStore

    async def add(self, rel_path: str) -> FavoriteState:
        path = resolve_under_root(self.root_path, rel_path)
        if not path.is_file():
            raise MediaFileNotFoundError(f"File not found: {rel_path}")
        key = str(path.relative_to(self.root_path))
        await self.store.add(key)
        return FavoriteState(path=key, is_favorite=True)

    async def remove(self, rel_path: str) -> FavoriteState:
        # No existence check, so favorites of deleted files can still be cleared.
        key = str(resolve_under_root(self.root_path, rel_path).relative_to(self.root_path))
        await self.store.remove(key)
        return FavoriteState(path=key, is_favorite=False)

    async def list_all(self) -> list[str]:
        return await self.store.list_all()
