from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from mediatools.contracts import ErrorResponse
from mediatools.contracts.picker import PickerListing, PickerRoot, PickerScope

from ..dependencies import PickerDep

router = APIRouter(prefix="/api/fs", tags=["folder picker"])

_ERRORS: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("/roots")
async def picker_roots(picker: PickerDep) -> list[PickerRoot]:
    return picker.roots()


@router.get("/dirs", responses=_ERRORS)
async def picker_dirs(picker: PickerDep, scope: PickerScope = "gallery", path: str | None = None) -> PickerListing:
    '''Subfolders of `path` (absolute; default: the first root of `scope`), read live from disk.'''
    return await picker.list(scope, path)
