from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import jinja2

from mediatools.contracts import DirectoryPage

from .settings import TEMPLATES_DIR

GALLERY_TEMPLATE = TEMPLATES_DIR / "gallery.html"
REELS_TEMPLATE = TEMPLATES_DIR / "reels.html"


def _load_template(path: Path) -> jinja2.Template:
    # One environment per file so same-named templates in different dirs can't shadow each other.
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(path.parent), autoescape=True)
    return env.get_template(path.name)


@dataclasses.dataclass(frozen=True)
class PageRenderer:
    '''Renders directory pages to HTML. Templates are re-read on each render so edits apply without a restart.'''

    def render_gallery(self, page: DirectoryPage) -> str:
        return self._render(GALLERY_TEMPLATE, page)

    def render_reels(self, page: DirectoryPage) -> str:
        return self._render(REELS_TEMPLATE, page)

    @staticmethod
    def _render(path: Path, page: DirectoryPage) -> str:
        context: dict[str, typing.Any] = page.model_dump()
        return _load_template(path).render(**context)
