from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .lifespan import lifespan
from .routers import favorites, fs, jobs, listings, media, media_jobs, pages, uploads
from .settings import STATIC_DIR, Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    '''Build the app. Settings are read from the environment at startup when not given.'''
    app = FastAPI(title="mediatools gallery", lifespan=lifespan)
    app.state.settings = settings
    register_exception_handlers(app)
    app.include_router(pages.router)
    app.include_router(media.router)
    app.include_router(listings.router)
    app.include_router(listings.api_router)
    app.include_router(favorites.router)
    app.include_router(jobs.router)
    app.include_router(media_jobs.router)
    app.include_router(fs.router)
    app.include_router(uploads.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
