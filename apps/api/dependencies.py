from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from mediatools.application import BrowserService, GalleryService
from mediatools.application.folder_picker import FolderPicker
from mediatools.application.media_jobs import MediaJobService
from mediatools.contracts import JobConfigView
from mediatools.jobs import JobManager

from .rendering import PageRenderer


def get_gallery(request: Request) -> GalleryService:
    return request.app.state.gallery


def get_browser(request: Request) -> BrowserService:
    return request.app.state.browser


def get_picker(request: Request) -> FolderPicker:
    return request.app.state.picker


def get_renderer(request: Request) -> PageRenderer:
    return request.app.state.renderer


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_media_jobs(request: Request) -> MediaJobService:
    return request.app.state.media_jobs


def get_job_config(request: Request) -> JobConfigView:
    return request.app.state.job_config


GalleryDep = Annotated[GalleryService, Depends(get_gallery)]
BrowserDep = Annotated[BrowserService, Depends(get_browser)]
PickerDep = Annotated[FolderPicker, Depends(get_picker)]
RendererDep = Annotated[PageRenderer, Depends(get_renderer)]
JobManagerDep = Annotated[JobManager, Depends(get_job_manager)]
MediaJobsDep = Annotated[MediaJobService, Depends(get_media_jobs)]
JobConfigDep = Annotated[JobConfigView, Depends(get_job_config)]
