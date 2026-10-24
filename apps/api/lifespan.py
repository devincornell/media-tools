from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pymongo
from fastapi import FastAPI

from mediatools.application import GalleryService
from mediatools.index_db import MediaIndexDB

from .rendering import PageRenderer
from .settings import ServerConfig, Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings or Settings()  # type: ignore[call-arg]
    config = ServerConfig.from_settings(settings)

    mongo_client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(config.mongodb_url)
    try:
        db = await MediaIndexDB.from_client(mongo_client[config.database_name])  # type: ignore[arg-type]
        app.state.gallery = GalleryService(
            root_path=config.root_path,
            thumb_path=config.thumb_path,
            max_clip_duration=config.max_clip_duration,
            dirs=db.dirs,
            videos=db.videos,
        )
        app.state.renderer = PageRenderer(
            template_path=config.template_path,
            reels_template_path=config.reels_template_path,
        )
        logger.info("Serving %s (database %r)", config.root_path, config.database_name)
        yield
    finally:
        await mongo_client.aclose()
