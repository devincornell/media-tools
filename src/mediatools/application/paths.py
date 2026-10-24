from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .errors import PathOutsideRootError


def resolve_under_root(root: Path, rel_path: str) -> Path:
    '''Join `rel_path` to `root`, rejecting paths that escape it (lexically, so symlinks inside the root still work).'''
    candidate = Path(os.path.normpath(root / (rel_path or ".")))
    if not candidate.is_relative_to(root):
        raise PathOutsideRootError(f"Path is outside the gallery root: {rel_path}")
    return candidate


def resolve_allowed_source(source: str, allowed_roots: Iterable[Path]) -> Path:
    '''Resolve `source` (following symlinks) and require it to be inside one of `allowed_roots`.'''
    path = Path(source)
    if not path.is_absolute():
        raise PathOutsideRootError(f"Source must be an absolute path: {source}")
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise PathOutsideRootError(f"Source is not inside an allowed copy source root: {source}")
    return resolved
