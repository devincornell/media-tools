from __future__ import annotations

import asyncio
import dataclasses
import os
from pathlib import Path

from ..contracts.picker import PickerDir, PickerListing, PickerRoot, PickerScope
from .errors import InvalidJobRequestError, MediaFileNotFoundError, PathOutsideRootError
from .media_jobs.fileops import user_name

MAX_FILE_COUNT = 10_000


@dataclasses.dataclass(frozen=True)
class FolderPicker:
    '''Live folder listings for choosing job paths, confined to the gallery root and copy source roots.'''

    gallery_root: Path
    source_roots: tuple[Path, ...]

    def roots(self) -> list[PickerRoot]:
        return [PickerRoot(scope="gallery", path=str(self.gallery_root))] + [
            PickerRoot(scope="source", path=str(r)) for r in self.source_roots
        ]

    async def list(self, scope: PickerScope, path: str | None = None) -> PickerListing:
        return await asyncio.to_thread(self._list, scope, path)

    def _scope_roots(self, scope: PickerScope) -> tuple[Path, ...]:
        roots = (self.gallery_root,) if scope == "gallery" else self.source_roots
        if not roots:
            raise InvalidJobRequestError("Move jobs are disabled: no copy source roots are configured.")
        return tuple(r.resolve() for r in roots)

    def _list(self, scope: PickerScope, path: str | None) -> PickerListing:
        roots = self._scope_roots(scope)
        target = Path(path).resolve() if path else roots[0]
        # Outermost matching root, so you can always navigate back up to it.
        matching = [r for r in roots if target.is_relative_to(r)]
        if not matching:
            raise PathOutsideRootError(f"Not inside an allowed root: {path}")
        root = min(matching, key=lambda r: len(r.parts))
        if not target.is_dir():
            raise MediaFileNotFoundError(f"Folder not found: {path}")

        dirs: list[PickerDir] = []
        num_files = 0
        try:
            entries = list(os.scandir(target))
        except PermissionError as e:
            raise InvalidJobRequestError(f"The server can't read {target}") from e
        for entry in entries:
            if entry.is_dir():
                child = Path(entry.path).resolve()
                if any(child.is_relative_to(r) for r in roots):
                    dirs.append(self._describe(entry.name, child))
            elif entry.is_file():
                num_files += 1
        st = target.stat()
        return PickerListing(
            scope=scope,
            root=str(root),
            path=str(target),
            rel=self._rel(target),
            parent=None if target == root else str(target.parent),
            writable=os.access(target, os.W_OK | os.X_OK),
            owner=user_name(st.st_uid),
            num_files=num_files,
            dirs=sorted(dirs, key=lambda d: d.name.lower()),
        )

    def _describe(self, name: str, path: Path) -> PickerDir:
        num_files, has_subdirs, readable = 0, False, True
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir():
                        has_subdirs = True
                    elif entry.is_file():
                        num_files += 1
                        if num_files >= MAX_FILE_COUNT:
                            break
        except PermissionError:
            readable = False
        return PickerDir(
            name=name,
            path=str(path),
            rel=self._rel(path),
            readable=readable,
            writable=os.access(path, os.W_OK | os.X_OK),
            owner=user_name(path.stat().st_uid),
            num_files=num_files,
            more_files=num_files >= MAX_FILE_COUNT,
            has_subdirs=has_subdirs,
        )

    def _rel(self, path: Path) -> str | None:
        root = self.gallery_root.resolve()
        return str(path.relative_to(root)) if path.is_relative_to(root) else None
