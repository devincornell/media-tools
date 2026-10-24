from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from ..dependencies import GalleryDep, RendererDep

router = APIRouter(tags=["pages"])


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/page/")


@router.get("/page", include_in_schema=False)
async def page_redirect() -> RedirectResponse:
    return RedirectResponse(url="/page/")


@router.get("/page/{page_path:path}", response_class=HTMLResponse)
async def gallery_page(page_path: str, gallery: GalleryDep, renderer: RendererDep) -> str:
    return renderer.render_gallery(await gallery.directory_page(page_path))


@router.get("/reel", include_in_schema=False)
async def reel_redirect() -> RedirectResponse:
    return RedirectResponse(url="/reel/")


@router.get("/reel/{page_path:path}", response_class=HTMLResponse)
async def reels_page(page_path: str, gallery: GalleryDep, renderer: RendererDep) -> str:
    return renderer.render_reels(await gallery.directory_page(page_path))
