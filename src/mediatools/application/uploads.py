from __future__ import annotations

import asyncio
import dataclasses
import errno
import os
import uuid
from collections.abc import AsyncIterable
from pathlib import Path

from ..contracts.uploads import UploadCheckItem, UploadFileSpec, UploadResult
from .errors import (
    InvalidUploadError,
    PathOutsideRootError,
    UploadConflictError,
    UploadError,
    UploadIncompleteError,
    UploadPermissionError,
    UploadStorageFullError,
)
from .paths import resolve_under_root

MAX_COMPONENT_BYTES = 255
MAX_PATH_BYTES = 4096
WRITE_BUFFER = 1024 * 1024


def clean_relative_path(rel: str) -> tuple[str, ...]:
    '''Validate an uploaded relative path and split it into components.

    Rejects absolute paths, empty/`.`/`..` components, control characters, and over-long names.
    '''
    if not rel or len(rel.encode(errors="replace")) > MAX_PATH_BYTES:
        raise InvalidUploadError("Empty or over-long path.")
    if rel.startswith("/"):
        raise InvalidUploadError(f"Absolute paths are not allowed: {rel}")
    parts = tuple(rel.split("/"))
    for part in parts:
        if part in ("", ".", ".."):
            raise InvalidUploadError(f"Invalid path component in: {rel}")
        if any(ord(c) < 32 or c == "\x7f" for c in part):
            raise InvalidUploadError(f"Control characters are not allowed in: {rel}")
        if len(part.encode(errors="replace")) > MAX_COMPONENT_BYTES:
            raise InvalidUploadError(f"File or folder name is too long in: {rel}")
    return parts


def _translate(error: OSError, path: Path) -> UploadError:
    if isinstance(error, PermissionError):
        return UploadPermissionError(f"The server isn't allowed to write to {path.parent}.")
    if error.errno == errno.ENOSPC:
        return UploadStorageFullError("The server's disk is full.")
    if error.errno in (errno.ENAMETOOLONG, errno.EILSEQ):
        return InvalidUploadError(f"The file name can't be stored: {path.name}")
    if isinstance(error, (NotADirectoryError, IsADirectoryError, FileExistsError)):
        return UploadConflictError(f"A file and a folder have the same name along {path}.")
    return UploadError(f"Could not write {path.name}: {error.strerror or error}")


def _no_clobber_move(tmp: Path, target: Path) -> None:
    '''Atomically give `tmp` the name `target`, refusing to overwrite.'''
    try:
        os.link(tmp, target)  # fails if `target` exists
    except FileExistsError as e:
        raise UploadConflictError(f"File already exists: {target.name}") from e
    except OSError:
        # Filesystem without hard links.
        if target.exists():
            raise UploadConflictError(f"File already exists: {target.name}") from None
        os.replace(tmp, target)
        return
    tmp.unlink()


@dataclasses.dataclass(frozen=True)
class UploadService:
    '''Stores uploaded files under the gallery root, preserving relative folder structure.'''

    root_path: Path

    def _dest_dir(self, dest: str) -> Path:
        try:
            return resolve_under_root(self.root_path, dest)
        except PathOutsideRootError as e:
            raise InvalidUploadError(str(e)) from e

    def target_for(self, dest: str, rel: str) -> Path:
        dest_dir = self._dest_dir(dest)
        return dest_dir.joinpath(*clean_relative_path(rel))

    async def check(self, dest: str, files: list[UploadFileSpec]) -> list[UploadCheckItem]:
        dest_dir = self._dest_dir(dest)
        return await asyncio.to_thread(self._check, dest_dir, files)

    def _check(self, dest_dir: Path, files: list[UploadFileSpec]) -> list[UploadCheckItem]:
        items: list[UploadCheckItem] = []
        for spec in files:
            try:
                target = dest_dir.joinpath(*clean_relative_path(spec.path))
            except InvalidUploadError as e:
                items.append(UploadCheckItem(path=spec.path, state="invalid", existing_size=None, detail=str(e)))
                continue
            try:
                st = target.stat()
            except FileNotFoundError:
                items.append(UploadCheckItem(path=spec.path, state="new", existing_size=None, detail=None))
                continue
            except OSError as e:  # e.g. a parent component is a file
                items.append(UploadCheckItem(path=spec.path, state="conflict", existing_size=None, detail=e.strerror))
                continue
            if target.is_dir():
                items.append(UploadCheckItem(path=spec.path, state="conflict", existing_size=None, detail="A folder has this name."))
            elif st.st_size == spec.size:
                items.append(UploadCheckItem(path=spec.path, state="same", existing_size=st.st_size, detail=None))
            else:
                items.append(UploadCheckItem(
                    path=spec.path, state="conflict", existing_size=st.st_size,
                    detail=f"A file with a different size exists ({st.st_size} bytes).",
                ))
        return items

    async def store(
        self,
        dest: str,
        rel: str,
        chunks: AsyncIterable[bytes],
        *,
        expected_size: int | None = None,
        overwrite: bool = False,
        mtime_ms: float | None = None,
    ) -> UploadResult:
        '''Stream `chunks` to disk. The file appears at its final name only once fully received.'''
        target = self.target_for(dest, rel)
        tmp = target.parent / f".upload-{uuid.uuid4().hex}"
        try:
            existed = await asyncio.to_thread(self._prepare, target, overwrite)
            written = await self._write(tmp, chunks)
            if expected_size is not None and written != expected_size:
                raise UploadIncompleteError(f"Received {written} of {expected_size} bytes.")
            await asyncio.to_thread(self._finish, tmp, target, overwrite, mtime_ms)
        except OSError as e:
            raise _translate(e, target) from e
        finally:
            tmp.unlink(missing_ok=True)
        return UploadResult(path=self._rel(target), size=written, replaced=existed and overwrite)

    def _prepare(self, target: Path, overwrite: bool) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            raise InvalidUploadError(f"A folder already has this name: {target.name}")
        existed = target.exists()
        if existed and not overwrite:
            raise UploadConflictError(f"File already exists: {target.name}")
        return existed

    @staticmethod
    async def _write(tmp: Path, chunks: AsyncIterable[bytes]) -> int:
        written = 0
        buffer = bytearray()
        with tmp.open("xb") as f:
            async for chunk in chunks:
                buffer += chunk
                if len(buffer) >= WRITE_BUFFER:
                    data, buffer = bytes(buffer), bytearray()
                    await asyncio.to_thread(f.write, data)
                    written += len(data)
            if buffer:
                await asyncio.to_thread(f.write, bytes(buffer))
                written += len(buffer)
        return written

    @staticmethod
    def _finish(tmp: Path, target: Path, overwrite: bool, mtime_ms: float | None) -> None:
        if mtime_ms is not None and 0 <= mtime_ms < 32_503_680_000_000:  # before year 3000
            os.utime(tmp, (mtime_ms / 1000, mtime_ms / 1000))
        if overwrite:
            os.replace(tmp, target)
        else:
            _no_clobber_move(tmp, target)

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root_path))
