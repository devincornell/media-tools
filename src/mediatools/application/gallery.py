from __future__ import annotations

import dataclasses
import datetime
import logging
import os
import re
from pathlib import Path
from typing import Protocol

from ..contracts import DirectoryPage, ImageSummary, SubdirectorySummary, VideoSummary
from ..index_db import MediaDirIndexDoc, MediaDirIndexNotFoundError, VideoIndexDoc
from ..index_db.mediadir_index_collection import IndexImageFile, IndexVideoFile
from ..util import fname_to_id, fname_to_title, format_memory
from ..video.ffmpeg import NoResolutionError, NoVideoStreamError
from .errors import (
    DirectoryNotIndexedError,
    MediaFileNotFoundError,
    PathOutsideRootError,
)

logger = logging.getLogger(__name__)

_THUMB_ID = re.compile(r"[A-Za-z0-9_-]+(?:\.gif)?")


class DirectoryIndexReader(Protocol):
    async def find_by_path(self, path: Path) -> MediaDirIndexDoc | None: ...
    async def find_direct_subdirs(self, path: Path) -> list[MediaDirIndexDoc]: ...
    async def find_by_path_prefix(self, prefix: Path) -> list[MediaDirIndexDoc]: ...


class VideoIndexReader(Protocol):
    async def find_by_hash(self, file_hash: str) -> VideoIndexDoc: ...


@dataclasses.dataclass(frozen=True)
class GalleryService:
    '''Read-only browsing use cases over an indexed media directory tree.'''

    root_path: Path
    thumb_path: Path
    max_clip_duration: float
    dirs: DirectoryIndexReader
    videos: VideoIndexReader

    def resolve_under_root(self, rel_path: str) -> Path:
        '''Join `rel_path` to the root, rejecting paths that escape it (lexically, so symlinks inside the root still work).'''
        candidate = Path(os.path.normpath(self.root_path / (rel_path or ".")))
        if not candidate.is_relative_to(self.root_path):
            raise PathOutsideRootError(f"Path is outside the gallery root: {rel_path}")
        return candidate

    async def directory_page(self, rel_path: str = ".") -> DirectoryPage:
        path = self.resolve_under_root(rel_path)
        try:
            dir_doc = await self.dirs.find_by_path(path)
        except MediaDirIndexNotFoundError:
            dir_doc = None
        if dir_doc is None:
            raise DirectoryNotIndexedError(f"Page not found: {rel_path}")
        subdirs = await self.dirs.find_direct_subdirs(path)
        return await self._build_page(dir_doc, subdirs)

    async def list_directories(self) -> list[str]:
        docs = await self.dirs.find_by_path_prefix(self.root_path)
        return [str(doc.path.relative_to(self.root_path)) for doc in docs]

    async def list_videos(self) -> list[str]:
        docs = await self.dirs.find_by_path_prefix(self.root_path)
        return [
            str(ivf.path.relative_to(self.root_path))
            for doc in docs
            for ivf in doc.video_files.values()
        ]

    def media_file(self, rel_path: str) -> Path:
        path = self.resolve_under_root(rel_path)
        if not path.is_file():
            raise MediaFileNotFoundError(f"File not found: {rel_path}")
        return path

    def thumbnail_file(self, file_hash: str) -> Path:
        if not _THUMB_ID.fullmatch(file_hash):
            raise MediaFileNotFoundError(f"Thumbnail not found: {file_hash}")
        path = self.thumb_path / f"{file_hash.removesuffix('.gif')}.gif"
        if not path.is_file():
            raise MediaFileNotFoundError(f"Thumbnail not found: {file_hash}")
        return path

    def _has_thumb(self, file_hash: str) -> bool:
        return (self.thumb_path / f"{file_hash}.gif").exists()

    async def _build_page(self, dir_doc: MediaDirIndexDoc, subdirs: list[MediaDirIndexDoc]) -> DirectoryPage:
        video_items: list[VideoSummary] = []
        for ivf in sorted(dir_doc.video_files.values(), key=lambda v: v.name.lower()):
            try:
                vid_doc = await self.videos.find_by_hash(ivf.file_hash)
                video_items.append(self._video_summary(ivf, vid_doc))
            except Exception:
                logger.warning("Skipping video %s", ivf.path_str, exc_info=True)

        images = [
            self._image_summary(iif)
            for iif in sorted(dir_doc.image_files.values(), key=lambda i: i.name.lower())
        ]
        subpages = [
            await self._subdir_summary(sd)
            for sd in sorted(subdirs, key=lambda d: d.path.name.lower())
        ]
        total_size = sum(f.stat.size for f in dir_doc.video_files.values()) + sum(
            f.stat.size for f in dir_doc.image_files.values()
        )

        return DirectoryPage(
            page_path_rel=str(dir_doc.path.relative_to(self.root_path)),
            idx=fname_to_id(dir_doc.path.name),
            name=fname_to_title(dir_doc.path.name),
            files_size_str=format_memory(total_size),
            vids=[v for v in video_items if not v.is_clip],
            clips=[v for v in video_items if v.is_clip],
            images=images,
            subpages=subpages,
            num_vids=len(dir_doc.video_files),
            num_imgs=len(dir_doc.image_files),
            num_subpages=len(subdirs),
        )

    def _video_summary(self, ivf: IndexVideoFile, vid_doc: VideoIndexDoc) -> VideoSummary:
        vid_path = ivf.path
        tags = vid_doc.probe.tags or {}
        created_ts: datetime.datetime | None = None
        if "creation_time" in tags:
            try:
                created_ts = datetime.datetime.fromisoformat(str(tags["creation_time"]))
            except (ValueError, TypeError):
                pass

        try:
            aspect = vid_doc.probe.video.aspect_ratio
            res_str = vid_doc.probe.resolution_str()
        except (NoVideoStreamError, NoResolutionError):
            aspect = 1.0
            res_str = ""

        return VideoSummary(
            vid_path_rel=str(vid_path.relative_to(self.root_path)),
            thumb_exists=self._has_thumb(vid_doc.file_hash),
            idx=fname_to_id(vid_path.stem),
            vid_title=fname_to_title(vid_path.stem),
            vid_size=vid_doc.stat.size,
            vid_size_str=format_memory(vid_doc.stat.size),
            duration=vid_doc.probe.duration,
            duration_str=vid_doc.probe.duration_str(),
            res_str=res_str,
            aspect=aspect,
            hash=vid_doc.file_hash,
            is_clip=vid_doc.probe.duration < self.max_clip_duration,
            created_ts=created_ts.timestamp() if created_ts is not None else None,
            created=created_ts.strftime("%Y-%m-%d %H:%M:%S") if created_ts is not None else None,
        )

    def _image_summary(self, iif: IndexImageFile) -> ImageSummary:
        width, height = iif.res
        return ImageSummary(
            img_path_rel=str(iif.path.relative_to(self.root_path)),
            title=fname_to_title(iif.path.stem),
            aspect=width / height if height else 1.0,
        )

    async def _subdir_summary(self, sd: MediaDirIndexDoc) -> SubdirectorySummary:
        all_docs = await self.dirs.find_by_path_prefix(sd.path)
        thumbs = [
            ivf.file_hash
            for doc in all_docs
            for ivf in doc.video_files.values()
            if self._has_thumb(ivf.file_hash)
        ]
        return SubdirectorySummary(
            page_path_rel=str(sd.path.relative_to(self.root_path)),
            idx=fname_to_id(sd.path.name),
            name=fname_to_title(sd.path.name),
            num_vids=len(sd.video_files),
            num_imgs=len(sd.image_files),
            num_subpages=len(sd.subpaths),
            subfolder_thumbs_all=thumbs,
        )
