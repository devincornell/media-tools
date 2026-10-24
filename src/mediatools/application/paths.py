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
    '''Require `source` to be inside one of `allowed_roots`, lexically, so symlinks inside a root are followed.

    The allow-list is therefore only as strict as the symlinks you create inside the roots.
    '''
    if not os.path.isabs(source):
        raise PathOutsideRootError(f"Source must be an absolute path: {source}")
    path = Path(os.path.normpath(source))
    if not any(path.is_relative_to(os.path.normpath(root)) for root in allowed_roots):
        raise PathOutsideRootError(f"Source is not inside an allowed copy source root: {source}")
    return path
