from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mediatools.application import (
    DirectoryNotIndexedError,
    MediaFileNotFoundError,
    PathOutsideRootError,
)
from mediatools.contracts import ErrorResponse


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorResponse(detail=detail).model_dump())


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return _error(404, str(exc))


async def _outside_root(request: Request, exc: Exception) -> JSONResponse:
    # Same response as a missing file so probing can't distinguish the two.
    return _error(404, "Not found")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DirectoryNotIndexedError, _not_found)
    app.add_exception_handler(MediaFileNotFoundError, _not_found)
    app.add_exception_handler(PathOutsideRootError, _outside_root)
