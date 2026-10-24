'''Blocking filesystem helpers used by media job handlers (run them via asyncio.to_thread).'''
from __future__ import annotations

import collections
import enum
import os
import pwd
import shutil
from collections.abc import Iterable
from pathlib import Path

from ...util import get_hash_hex


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


def list_source_files(root: Path) -> tuple[list[Path], list[Path]]:
    '''Regular files under `root`, and symlinks (files or dirs) which are skipped rather than followed.'''
    files: list[Path] = []
    links: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        links.extend(base / d for d in dirnames if (base / d).is_symlink())
        for name in filenames:
            path = base / name
            if path.is_symlink():
                links.append(path)
            elif path.is_file():
                files.append(path)
    return files, links


def move_file(src: Path, dst: Path, tmp_tag: str) -> MoveOutcome:
    '''Move `src` to `dst` without clobbering. If `dst` already has the same size, just delete `src`.'''
    size = src.stat().st_size
    if dst.exists() or dst.is_symlink():
        if dst.is_file() and dst.stat().st_size == size:
            src.unlink()
            return MoveOutcome.DEDUPLICATED
        return MoveOutcome.CONFLICT

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Same filesystem: instant, and link() refuses to overwrite an existing file.
        os.link(src, dst)
    except FileExistsError:
        return move_file(src, dst, tmp_tag)
    except OSError:
        tmp = dst.with_name(f".{dst.name}.{tmp_tag}.partial")
        try:
            shutil.copyfile(src, tmp)
            shutil.copystat(src, tmp)
            if tmp.stat().st_size != size:
                raise OSError(f"Size mismatch after copying {src}")
            if dst.exists():
                return MoveOutcome.CONFLICT
            os.replace(tmp, dst)
        finally:
            tmp.unlink(missing_ok=True)
    src.unlink()
    return MoveOutcome.MOVED


def remove_empty_dirs(root: Path) -> bool:
    '''Remove empty directories beneath `root` (not `root` itself). Returns True if `root` ends up empty.'''
    for dirpath, _, _ in os.walk(root, topdown=False):
        if Path(dirpath) != root:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    return not any(root.iterdir())


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
