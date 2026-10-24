from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from mediatools.application import GalleryService

from .rendering import PageRenderer


def get_gallery(request: Request) -> GalleryService:
    return request.app.state.gallery


def get_renderer(request: Request) -> PageRenderer:
    return request.app.state.renderer


GalleryDep = Annotated[GalleryService, Depends(get_gallery)]
RendererDep = Annotated[PageRenderer, Depends(get_renderer)]
