'''Blocking filesystem helpers used by media job handlers (run them via asyncio.to_thread).'''
from __future__ import annotations

import collections
import enum
import errno
import os
import pwd
import subprocess
import typing
import uuid
from collections.abc import Iterable
from pathlib import Path

from ...util import get_hash_hex


def run_command(argv: list[str], tolerate: str | None = None) -> None:
    '''Run a coreutils command without a shell, so file names are never parsed as syntax.

    A non-zero exit is an OSError unless stderr contains `tolerate`.
    '''
    result = subprocess.run(argv, capture_output=True, text=True, check=False, env={**os.environ, "LC_ALL": "C"})
    if result.returncode == 0:
        return
    message = result.stderr.strip() or f"exit status {result.returncode}"
    if tolerate and tolerate in message:
        return
    if "Permission denied" in message:
        raise PermissionError(errno.EACCES, message)
    if "No space left" in message:
        raise OSError(errno.ENOSPC, message)
    raise OSError(f"{argv[0]} failed: {message}")


def same_device(a: Path, b: Path) -> bool:
    return a.stat().st_dev == b.stat().st_dev


def user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def unwritable_dirs(root: Path) -> list[Path]:
    '''Directories under `root` (inclusive) in which this process can't delete or create entries.'''
    return [Path(d) for d, _, _ in os.walk(root, followlinks=False) if not os.access(d, os.W_OK | os.X_OK)]


def permission_message(source: Path, blocked: list[Path]) -> str:
    me = user_name(os.getuid())
    owners = sorted({user_name(p.stat().st_uid) for p in blocked})
    return (
        f"The server runs as '{me}' but can't delete files in {len(blocked)} source folder(s) "
        f"(owned by {', '.join(owners)}), e.g. {blocked[0]}. Nothing was moved. "
        f"Fix with: sudo chown -R {me} '{source}'"
    )


class MoveOutcome(enum.StrEnum):
    MOVED = "moved"
    DEDUPLICATED = "deduplicated"
    CONFLICT = "conflict"
    RENAMED = "renamed"


class Moved(typing.NamedTuple):
    outcome: MoveOutcome
    path: Path  # where the entry ended up; differs from the requested path when renamed


MAX_RENAMES = 10_000


def list_source_files(root: Path) -> tuple[list[Path], list[Path]]:
    '''Regular files under `root`, and every other non-directory entry (symlinks, sockets, fifos, ...).

    Symlinks are never followed; they are returned to be moved as links.
    '''
    files: list[Path] = []
    others: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        others.extend(base / d for d in dirnames if (base / d).is_symlink())
        for name in filenames:
            path = base / name
            (files if path.is_file() and not path.is_symlink() else others).append(path)
    return files, others


def _numbered(path: Path, n: int) -> Path:
    return path.with_name(f"{path.stem} ({n}){path.suffix}")


def _remove(path: Path) -> None:
    run_command(["rm", "-f", "--", str(path)])


def _place(src: Path, dst: Path, tmp_tag: str) -> bool:
    '''Put regular file `src` at `dst` (which must not exist) using mv/cp/rm.

    Returns False, changing nothing, if `dst` appeared in the meantime.
    '''
    if same_device(src, dst.parent):
        # A rename: no data is copied. `-n` makes mv skip rather than overwrite.
        run_command(["mv", "-n", "-T", "--", str(src), str(dst)], tolerate="not replacing")
        return not os.path.lexists(src)

    # Different filesystems: copy to a temporary name, verify, rename into place, then delete the source.
    tmp = dst.parent / f".{tmp_tag}-{uuid.uuid4().hex}.partial"
    try:
        run_command(["cp", "-p", "--reflink=auto", "--", str(src), str(tmp)])
        if tmp.stat().st_size != src.stat().st_size:
            raise OSError(f"Size mismatch after copying {src}")
        run_command(["mv", "-n", "-T", "--", str(tmp), str(dst)], tolerate="not replacing")
        if os.path.lexists(tmp):  # skipped: `dst` appeared meanwhile
            return False
        _remove(src)
        return True
    finally:
        if os.path.lexists(tmp):
            _remove(tmp)


def move_file(src: Path, dst: Path, tmp_tag: str, rename_on_conflict: bool = False) -> Moved:
    '''Move regular file `src` to `dst` without clobbering, using mv/cp/rm.

    A same-size file already at `dst` counts as the same file, so `src` is just deleted. Otherwise a clash is
    reported, or with `rename_on_conflict` the file is stored next to `dst` as `name (1).ext`, `name (2).ext`, ...
    '''
    size = src.stat().st_size
    if os.path.lexists(dst):
        if dst.is_file() and dst.stat().st_size == size:
            _remove(src)
            return Moved(MoveOutcome.DEDUPLICATED, dst)
        if not rename_on_conflict:
            return Moved(MoveOutcome.CONFLICT, dst)
        return _move_renamed(src, dst, tmp_tag, size)

    dst.parent.mkdir(parents=True, exist_ok=True)
    if _place(src, dst, tmp_tag):
        return Moved(MoveOutcome.MOVED, dst)
    return move_file(src, dst, tmp_tag, rename_on_conflict)  # `dst` appeared; re-evaluate


def _move_renamed(src: Path, dst: Path, tmp_tag: str, size: int) -> Moved:
    for n in range(1, MAX_RENAMES + 1):
        candidate = _numbered(dst, n)
        if os.path.lexists(candidate):
            if candidate.is_file() and candidate.stat().st_size == size:  # left by an earlier attempt
                _remove(src)
                return Moved(MoveOutcome.DEDUPLICATED, candidate)
            continue
        if _place(src, candidate, tmp_tag):
            return Moved(MoveOutcome.RENAMED, candidate)
    raise OSError(f"No free name found for {dst.name}")


def move_entry(src: Path, dst: Path) -> Moved:
    '''Move a symlink or special file as itself (never following it) with `mv`, renaming on a name clash.'''
    if os.path.islink(src) and os.path.islink(dst) and os.readlink(src) == os.readlink(dst):
        _remove(src)  # an earlier attempt already moved it
        return Moved(MoveOutcome.DEDUPLICATED, dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    for n in range(MAX_RENAMES + 1):
        target = dst if n == 0 else _numbered(dst, n)
        if os.path.lexists(target):
            continue
        run_command(["mv", "-n", "-T", "--", str(src), str(target)], tolerate="not replacing")
        if not os.path.lexists(src):
            return Moved(MoveOutcome.MOVED if n == 0 else MoveOutcome.RENAMED, target)
    raise OSError(f"No free name found for {dst.name}")


def is_protected_root(source: Path, roots: Iterable[Path]) -> bool:
    '''Whether `source` is (or links to) one of the configured copy source roots.'''
    candidates = {Path(os.path.normpath(source)), Path(os.path.realpath(source))}
    protected = {p for r in roots for p in (Path(os.path.normpath(r)), Path(os.path.realpath(r)))}
    return bool(candidates & protected)


def remove_source_tree(source: Path) -> list[Path]:
    '''Remove `source` and every empty folder in it; if `source` is a symlink, remove the link as well.

    Returns the entries still inside (so the folder remains) when something could not be moved out.
    '''
    real = Path(os.path.realpath(source))
    for dirpath, _, _ in os.walk(real, topdown=False):
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    if real.exists():
        return [
            Path(d) / name
            for d, dirnames, filenames in os.walk(real)
            for name in [*filenames, *(n for n in dirnames if (Path(d) / n).is_symlink())]
        ]
    if os.path.islink(source):
        _remove(source)
    return []


def find_duplicates(paths: Iterable[Path]) -> list[tuple[Path, Path]]:
    '''Group byte-identical files; return (duplicate, kept) pairs, keeping the longest path of each group.'''
    by_hash: dict[str, list[Path]] = collections.defaultdict(list)
    by_size: dict[int, list[Path]] = collections.defaultdict(list)
    for path in paths:
        by_size[path.stat().st_size].append(path)
    for same_size in by_size.values():
        if len(same_size) > 1:
            for path in same_size:
                by_hash[get_hash_hex(path, chunk_size=1024 * 1024)].append(path)
    pairs: list[tuple[Path, Path]] = []
    for group in by_hash.values():
        if len(group) > 1:
            kept = max(group, key=lambda p: (len(str(p)), str(p)))
            pairs.extend((p, kept) for p in group if p != kept)
    return pairs
