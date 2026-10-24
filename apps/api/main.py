from __future__ import annotations

from fastapi import FastAPI

from .errors import register_exception_handlers
from .lifespan import lifespan
from .routers import listings, media, pages
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    '''Build the app. Settings are read from the environment at startup when not given.'''
    app = FastAPI(title="mediatools gallery", lifespan=lifespan)
    app.state.settings = settings
    register_exception_handlers(app)
    app.include_router(pages.router)
    app.include_router(media.router)
    app.include_router(listings.router)
    app.include_router(listings.api_router)
    return app


app = create_app()
