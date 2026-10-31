from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pymongo
from fastapi import FastAPI

from mediatools.contracts import JobConfigView

from .composition import build_services
from .rendering import PageRenderer
from .settings import ServerConfig, Settings

logger = logging.getLogger(__name__)

WORKER_SHUTDOWN_TIMEOUT = 15.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings or Settings()  # type: ignore[call-arg]
    config = ServerConfig.from_settings(settings)

    mongo_client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(config.mongodb_url)
    stop = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None
    try:
        services = await build_services(config, mongo_client[config.database_name])
        app.state.gallery = services.gallery
        app.state.favorites = services.favorites
        app.state.folder_favorites = services.folder_favorites
        app.state.browser = services.browser
        app.state.picker = services.picker
        app.state.uploads = services.uploads
        app.state.job_manager = services.job_manager
        app.state.media_jobs = services.media_jobs
        app.state.job_config = JobConfigView(
            copy_source_roots=[str(p) for p in config.copy_source_roots],
            worker_enabled=config.run_worker,
        )
        app.state.renderer = PageRenderer()
        if config.run_worker:
            worker_task = asyncio.create_task(services.worker.run(stop))
        logger.info("Serving %s (database %r, job worker %s)", config.root_path, config.database_name,
                    "on" if config.run_worker else "off")
        yield
    finally:
        stop.set()
        if worker_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(worker_task), WORKER_SHUTDOWN_TIMEOUT)
            except TimeoutError:
                logger.warning("Job worker did not stop in time; its jobs will be recovered when their leases expire")
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task
        await mongo_client.aclose()
