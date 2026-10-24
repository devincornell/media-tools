from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Literal, Protocol

from ..contracts import FileEntry, FolderFiles, FolderNode, FolderTree
from ..index_db import DirectorySizeRow, MediaDirIndexDoc, MediaDirIndexNotFoundError
from .errors import DirectoryNotIndexedError
from .paths import resolve_under_root


class FolderIndexReader(Protocol):
    async def directory_sizes(self, prefix: Path) -> list[DirectorySizeRow]: ...
    async def find_by_path(self, path: Path) -> MediaDirIndexDoc | None: ...


@dataclasses.dataclass(frozen=True)
class BrowserService:
    '''Folder tree with recursive sizes and per-folder file listings, read from the index only.'''

    root_path: Path
    dirs: FolderIndexReader

    async def tree(self) -> FolderTree:
        rows = {Path(r.path_str): r for r in await self.dirs.directory_sizes(self.root_path)}
        parent = {p: self._indexed_ancestor(p, rows) for p in rows}
        size = {p: r.bytes for p, r in rows.items()}
        files = {p: r.num_videos + r.num_images + r.num_other for p, r in rows.items()}
        for p in sorted(rows, key=lambda p: len(p.parts), reverse=True):
            if (up := parent[p]) is not None:
                size[up] += size[p]
                files[up] += files[p]

        total = sum(r.bytes for r in rows.values())
        return FolderTree(
            total_size=total,
            folders=[
                FolderNode(
                    path=self._rel(p),
                    name=p.name,
                    parent=self._rel_or_none(parent[p]),
                    size=size[p],
                    direct_size=r.bytes,
                    percent=100 * size[p] / total if total else 0.0,
                    files=files[p],
                    num_videos=r.num_videos,
                    num_images=r.num_images,
                    num_other=r.num_other,
                    num_subdirs=r.num_subdirs,
                )
                for p, r in sorted(rows.items())
            ],
        )

    async def files(self, rel_path: str) -> FolderFiles:
        path = resolve_under_root(self.root_path, rel_path)
        try:
            doc = await self.dirs.find_by_path(path)
        except MediaDirIndexNotFoundError:
            doc = None
        if doc is None:
            raise DirectoryNotIndexedError(f"Folder not indexed: {rel_path}")

        groups: list[tuple[Literal["video", "image", "other"], dict]] = [
            ("video", doc.video_files), ("image", doc.image_files), ("other", doc.other_files),
        ]
        entries = [
            FileEntry(
                name=f.name,
                path=self._rel(f.path),
                kind=kind,
                size=f.stat.st_size,
                modified=datetime.datetime.fromtimestamp(f.stat.st_mtime, datetime.UTC),
            )
            for kind, group in groups
            for f in group.values()
            if f.path.is_relative_to(self.root_path)
        ]
        return FolderFiles(path=self._rel(path), files=sorted(entries, key=lambda e: e.name.lower()))

    def _indexed_ancestor(self, path: Path, indexed: dict[Path, DirectorySizeRow]) -> Path | None:
        '''Nearest ancestor that is in the index (skipping unindexed gaps), staying within the root.'''
        for ancestor in path.parents:
            if not ancestor.is_relative_to(self.root_path):
                return None
            if ancestor in indexed:
                return ancestor
        return None

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root_path))

    def _rel_or_none(self, path: Path | None) -> str | None:
        return None if path is None else self._rel(path)
