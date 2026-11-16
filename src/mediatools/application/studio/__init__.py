from ..media_jobs.handlers import MediaJobDeps
from ..media_jobs.types import STUDIO_RENDER
from .examples import EXAMPLES, Example
from .handler import StudioRenderHandler
from .service import GraphStore, StudioService


def build_studio_handlers(deps: MediaJobDeps) -> dict[str, StudioRenderHandler]:
    return {STUDIO_RENDER: StudioRenderHandler(deps)}


__all__ = ["EXAMPLES", "Example", "GraphStore", "StudioRenderHandler", "StudioService", "build_studio_handlers"]
