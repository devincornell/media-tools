from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import typing
from collections.abc import Callable, Coroutine, Iterable
from pathlib import Path

import pydantic
import pymongo.errors

from ...contracts import (
    CleanupRequest,
    ConvertMp4Request,
    MoveRequest,
    ReindexRequest,
    ThumbnailsRequest,
)
from ...index_db import (
    MediaDirIndexDoc,
    MediaDirIndexNotFoundError,
    MediaIndexDB,
    MediaJobCollection,
    MediaJobRecord,
    VideoIndexDoc,
    index_hash_func,
)
from ...jobs import JobContext, JobHandler, PermanentJobError
from ...mediadir import MediaDir
from ...video.ffmpeg import FFMPEGError, ffinput, ffmpeg, ffoutput, make_animated_thumb
from ...video.video_file import VideoFile
from ..errors import PathOutsideRootError
from ..paths import resolve_allowed_source, resolve_under_root
from . import fileops
from .types import CLEANUP, CONVERT_MP4, MOVE, REINDEX, THUMBNAILS

logger = logging.getLogger(__name__)

MAX_LISTED = 500
THUMB_FPS = 3
THUMB_PERIOD_SEC = 10
THUMB_WIDTH = 400

Result = dict[str, pydantic.JsonValue]
Req = typing.TypeVar("Req", bound=pydantic.BaseModel)
Item = typing.TypeVar("Item")


@dataclasses.dataclass(frozen=True)
class MediaJobDeps:
    root_path: Path
    thumb_path: Path
    copy_source_roots: tuple[Path, ...]
    index: MediaIndexDB
    records: MediaJobCollection


def _span(lo: float, hi: float, done: int, total: int) -> float:
    return lo + (hi - lo) * (done / total if total else 1.0)


def _capped(items: Iterable[str]) -> list[pydantic.JsonValue]:
    return [item for _, item in zip(range(MAX_LISTED), items)]


async def _bounded(
    items: list[Item],
    worker: Callable[[Item], Coroutine[typing.Any, typing.Any, None]],
    limit: int,
    ctx: JobContext,
    progress: Callable[[int], tuple[float, str]],
) -> None:
    '''Run `worker` over `items` with at most `limit` in flight, checkpointing after each completion.'''
    pending: set[asyncio.Task[None]] = set()
    queue = list(reversed(items))
    finished = 0
    try:
        while queue or pending:
            while queue and len(pending) < limit:
                pending.add(asyncio.create_task(worker(queue.pop())))
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            finished += len(done)
            await ctx.checkpoint(*progress(finished))
    finally:
        for task in pending:
            task.cancel()


class _Base:
    def __init__(self, deps: MediaJobDeps):
        self.deps = deps

    async def _load(self, job_id: str, model: type[Req]) -> Req:
        record: MediaJobRecord | None = await self.deps.records.get(job_id)
        if record is None:
            raise PermanentJobError(f"No media job record for {job_id}", code="missing_record")
        return model.model_validate(record.params)

    def _target(self, rel: str) -> Path:
        try:
            return resolve_under_root(self.deps.root_path, rel)
        except PathOutsideRootError as e:
            raise PermanentJobError(str(e), code="invalid_path") from e

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.deps.root_path))

    async def _scan(self, path: Path, ctx: JobContext) -> MediaDir:
        if not path.is_dir():
            raise PermanentJobError(f"Directory not found: {self._rel(path)}", code="not_found")
        await ctx.checkpoint(0, f"Listing files in {self._rel(path)}", force=True)
        return await asyncio.to_thread(MediaDir.from_path, path)

    async def _reindex(self, path: Path, ctx: JobContext, lo: float = 0, hi: float = 100) -> Result:
        '''Rescan `path` into the index: upsert every directory, drop stale ones, probe new videos.'''
        mdir = await self._scan(path, ctx)
        dirs, videos_coll = self.deps.index.dirs, self.deps.index.videos
        scan_id = f"{ctx.job_id}:{ctx.job.attempt_count}"
        mid = lo + (hi - lo) * 0.4

        all_dirs = mdir.all_dirs()
        errors: list[str] = []
        for i, md in enumerate(all_dirs, 1):
            try:
                doc = await asyncio.to_thread(MediaDirIndexDoc.from_media_dir_scan, md)
                await dirs.upsert_directory(doc, scan_id=scan_id)
            except Exception as e:
                logger.warning("Could not index %s; keeping previous entry", md.path, exc_info=True)
                errors.append(f"{self._rel(md.path)}: {type(e).__name__}: {e}")
                await dirs.touch(md.path, scan_id)
            await ctx.checkpoint(_span(lo, mid, i, len(all_dirs)), f"Indexing directories {i}/{len(all_dirs)}")
        removed = await dirs.delete_stale(path, scan_id)
        await self._link_into_parent(path)

        all_videos = mdir.all_video_files()
        new_videos = 0
        for i, vf in enumerate(all_videos, 1):
            file_hash = await asyncio.to_thread(index_hash_func, vf.path)
            if not await videos_coll.check_exists(file_hash):
                try:
                    vdoc = await asyncio.to_thread(VideoIndexDoc.from_video_file_scan, vf, file_hash)
                    await videos_coll.insert(vdoc)
                    new_videos += 1
                except (FFMPEGError, pydantic.ValidationError) as e:
                    errors.append(f"{self._rel(vf.path)}: {type(e).__name__}")
                except pymongo.errors.DuplicateKeyError:
                    pass
            await ctx.checkpoint(_span(mid, hi, i, len(all_videos)), f"Probing videos {i}/{len(all_videos)}")

        return {
            "directories": len(all_dirs),
            "directories_removed": removed,
            "videos": len(all_videos),
            "videos_new": new_videos,
            "errors": _capped(errors),
            "error_count": len(errors),
        }

    async def _link_into_parent(self, path: Path) -> None:
        '''Make sure an indexed parent lists `path` among its subdirectories (e.g. a folder created by a move).'''
        if path == self.deps.root_path:
            return
        try:
            parent = await self.deps.index.dirs.find_by_path(path.parent)
        except MediaDirIndexNotFoundError:
            return
        if parent is not None and path.name not in parent.subpaths:
            parent.subpaths[path.name] = str(path)
            await self.deps.index.dirs.upsert_directory(parent)


class ReindexHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ReindexRequest)
        await self.deps.records.set_result(job_id, await self._reindex(self._target(req.path), ctx))
        return None


class ThumbnailsHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ThumbnailsRequest)
        mdir = await self._scan(self._target(req.path), ctx)
        videos = list(mdir.all_video_files())
        self.deps.thumb_path.mkdir(parents=True, exist_ok=True)
        created, skipped = 0, 0
        errors: list[str] = []

        async def one(vf: VideoFile) -> None:
            nonlocal created, skipped
            file_hash = await asyncio.to_thread(index_hash_func, vf.path)
            out = self.deps.thumb_path / f"{file_hash}.gif"
            if not req.overwrite and out.exists() and out.stat().st_size > 0:
                skipped += 1
                return
            tmp = self.deps.thumb_path / f".{file_hash}.{job_id[:8]}.tmp.gif"
            try:
                await asyncio.to_thread(
                    make_animated_thumb, vf.path, str(tmp),
                    fps=THUMB_FPS, target_period=THUMB_PERIOD_SEC, width=THUMB_WIDTH, height=-1, overwrite=True,
                )
                os.replace(tmp, out)
                created += 1
            except FFMPEGError as e:
                errors.append(f"{self._rel(vf.path)}: {type(e).__name__}")
            finally:
                tmp.unlink(missing_ok=True)

        await _bounded(videos, one, req.workers, ctx, lambda n: (_span(0, 100, n, len(videos)), f"Thumbnails {n}/{len(videos)}"))
        await self.deps.records.set_result(job_id, {
            "videos": len(videos), "created": created, "skipped_existing": skipped,
            "errors": _capped(errors), "error_count": len(errors),
        })
        return None


class CleanupHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, CleanupRequest)
        path = self._target(req.path)
        mdir = await self._scan(path, ctx)
        videos = [vf for vf in mdir.all_video_files() if vf.path.exists()]
        empty: list[Path] = []
        unprobable: list[Path] = []
        duplicates: list[tuple[Path, Path]] = []

        if req.delete_empty:
            empty = [vf.path for vf in videos if vf.path.stat().st_size == 0]
        flagged = set(empty)

        if req.delete_unprobable:
            candidates = [vf for vf in videos if vf.path not in flagged]
            for i, vf in enumerate(candidates, 1):
                try:
                    await asyncio.to_thread(vf.probe)
                except FFMPEGError:
                    unprobable.append(vf.path)
                await ctx.checkpoint(_span(0, 50, i, len(candidates)), f"Probing {i}/{len(candidates)}")
            flagged |= set(unprobable)

        if req.delete_duplicates:
            all_dirs = mdir.all_dirs()
            for i, md in enumerate(all_dirs, 1):
                in_dir = [vf.path for vf in md.videos if vf.path.exists() and vf.path not in flagged]
                duplicates += await asyncio.to_thread(fileops.find_duplicates, in_dir)
                await ctx.checkpoint(_span(50, 80, i, len(all_dirs)), f"Comparing files {i}/{len(all_dirs)} dirs")

        to_delete = empty + unprobable + [dup for dup, _ in duplicates]
        if not req.dry_run:
            for i, p in enumerate(to_delete, 1):
                p.unlink(missing_ok=True)
                await ctx.checkpoint(_span(80, 85, i, len(to_delete)), f"Deleting {i}/{len(to_delete)}")

        result: Result = {
            "dry_run": req.dry_run,
            "deleted": 0 if req.dry_run else len(to_delete),
            "counts": {"empty": len(empty), "unprobable": len(unprobable), "duplicates": len(duplicates)},
            "empty": _capped(self._rel(p) for p in empty),
            "unprobable": _capped(self._rel(p) for p in unprobable),
            "duplicates": _capped(f"{self._rel(d)} (kept {k.name})" for d, k in duplicates),
        }
        if to_delete and not req.dry_run:
            result["reindex"] = await self._reindex(path, ctx, 85, 100)
        await self.deps.records.set_result(job_id, result)
        return None


class ConvertMp4Handler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ConvertMp4Request)
        path = self._target(req.path)
        mdir = await self._scan(path, ctx)
        sources = [vf.path for vf in mdir.all_video_files() if vf.path.suffix.lower() != ".mp4"]
        converted, skipped = 0, 0
        errors: list[str] = []
        for i, src in enumerate(sources, 1):
            dst = src.with_suffix(".mp4")
            if dst.exists():
                skipped += 1
            else:
                tmp = dst.with_name(f".{dst.stem}.{job_id[:8]}.tmp.mp4")
                try:
                    await asyncio.to_thread(ffmpeg(input=ffinput(src), output=ffoutput(tmp, y=True)).run)
                    os.replace(tmp, dst)
                    converted += 1
                except FFMPEGError as e:
                    errors.append(f"{self._rel(src)}: {type(e).__name__}")
                finally:
                    tmp.unlink(missing_ok=True)
            await ctx.checkpoint(_span(0, 85, i, len(sources)), f"Converting {i}/{len(sources)}")

        result: Result = {
            "candidates": len(sources), "converted": converted, "skipped_existing": skipped,
            "errors": _capped(errors), "error_count": len(errors),
        }
        if converted:
            result["reindex"] = await self._reindex(path, ctx, 85, 100)
        await self.deps.records.set_result(job_id, result)
        return None


class MoveHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, MoveRequest)
        try:
            source = resolve_allowed_source(req.source, self.deps.copy_source_roots)
        except PathOutsideRootError as e:
            raise PermanentJobError(str(e), code="invalid_source") from e
        if not source.is_dir():
            raise PermanentJobError(f"Source directory not found: {source}", code="not_found")
        dest = self._target(req.dest)

        await ctx.checkpoint(0, "Listing source files", force=True)
        files, links = await asyncio.to_thread(fileops.list_source_files, source)
        total_bytes = sum(f.stat().st_size for f in files) or 1
        dest.mkdir(parents=True, exist_ok=True)
        tally = dict.fromkeys(fileops.MoveOutcome, 0)
        conflicts: list[str] = []
        processed_bytes = 0

        async def one(src: Path) -> None:
            nonlocal processed_bytes
            size = src.stat().st_size
            rel = src.relative_to(source)
            outcome = await asyncio.to_thread(fileops.move_file, src, dest / rel, job_id[:8])
            tally[outcome] += 1
            processed_bytes += size
            if outcome is fileops.MoveOutcome.CONFLICT:
                conflicts.append(str(rel))

        await _bounded(files, one, req.workers, ctx, lambda n: (80 * processed_bytes / total_bytes, f"Moving files {n}/{len(files)}"))
        source_empty = await asyncio.to_thread(fileops.remove_empty_dirs, source)

        warnings: list[pydantic.JsonValue] = []
        if conflicts:
            warnings.append(f"{len(conflicts)} file(s) already exist at the destination with a different size; left in source.")
        if links:
            warnings.append(f"{len(links)} symlink(s) in source were skipped.")
        result: Result = {
            "source": str(source),
            "dest": self._rel(dest),
            "files": len(files),
            "moved": tally[fileops.MoveOutcome.MOVED],
            "deduplicated": tally[fileops.MoveOutcome.DEDUPLICATED],
            "conflicts": _capped(conflicts),
            "skipped_symlinks": _capped(str(p.relative_to(source)) for p in links),
            "source_empty": source_empty,
            "warnings": warnings,
        }
        await self.deps.records.set_result(job_id, result)
        result["reindex"] = await self._reindex(dest, ctx, 80, 100)
        await self.deps.records.set_result(job_id, result)
        return None


def build_handlers(deps: MediaJobDeps) -> dict[str, JobHandler]:
    return {
        REINDEX: ReindexHandler(deps),
        THUMBNAILS: ThumbnailsHandler(deps),
        CLEANUP: CleanupHandler(deps),
        CONVERT_MP4: ConvertMp4Handler(deps),
        MOVE: MoveHandler(deps),
    }
