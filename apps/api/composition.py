from __future__ import annotations

import dataclasses

from pymongo.asynchronous.database import AsyncDatabase

from mediatools.application import BrowserService, GalleryService
from mediatools.application.folder_picker import FolderPicker
from mediatools.application.uploads import UploadService
from mediatools.application.media_jobs import (
    MediaJobDeps,
    MediaJobService,
    build_handlers,
)
from mediatools.index_db import MediaIndexDB, MediaJobCollection
from mediatools.jobs import JobManager, JobWorker, MongoJobLogStore, MongoJobRepository

from .settings import ServerConfig


@dataclasses.dataclass(frozen=True)
class Services:
    gallery: GalleryService
    browser: BrowserService
    picker: FolderPicker
    uploads: UploadService
    job_manager: JobManager
    media_jobs: MediaJobService
    worker: JobWorker


async def build_services(config: ServerConfig, database: AsyncDatabase) -> Services:
    '''Composition root shared by the API server and the standalone worker.'''
    index = await MediaIndexDB.from_client(database)  # type: ignore[arg-type]
    repo = MongoJobRepository.from_database(database)
    await repo.create_indexes()
    log_store = MongoJobLogStore.from_database(database)
    await log_store.create_indexes()
    records = MediaJobCollection.from_database(database)
    # Jobs are scoped to the gallery root they operate on.
    manager = JobManager(repo, scope_id=str(config.root_path), log_store=log_store)
    deps = MediaJobDeps(
        root_path=config.root_path,
        thumb_path=config.thumb_path,
        copy_source_roots=config.copy_source_roots,
        index=index,
        records=records,
    )
    return Services(
        gallery=GalleryService(
            root_path=config.root_path,
            thumb_path=config.thumb_path,
            max_clip_duration=config.max_clip_duration,
            dirs=index.dirs,
            videos=index.videos,
        ),
        browser=BrowserService(root_path=config.root_path, dirs=index.dirs),
        picker=FolderPicker(gallery_root=config.root_path, source_roots=config.copy_source_roots),
        uploads=UploadService(root_path=config.root_path),
        job_manager=manager,
        media_jobs=MediaJobService(
            root_path=config.root_path,
            copy_source_roots=config.copy_source_roots,
            jobs=manager,
            records=records,
        ),
        worker=JobWorker(
            repo,
            build_handlers(deps),
            scope_id=manager.scope_id,
            logs=log_store,
            lease_seconds=config.job_lease_seconds,
            concurrency=config.worker_concurrency,
        ),
    )
