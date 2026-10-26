from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import logging
import os
import typing
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine, Iterable, Sequence
from pathlib import Path

import pydantic
import pymongo.errors

from ...contracts import (
    CleanupRequest,
    ConvertMp4Request,
    MontageRequest,
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
from ...video.ffmpeg import FFMPEGError, create_montage, ffinput, ffmpeg, ffoutput, make_animated_thumb
from ...video.ffmpeg.core.probe import probe
from ...video.video_file import VideoFile
from ..errors import PathOutsideRootError
from ..paths import resolve_allowed_source, resolve_under_root
from . import fileops
from .locks import PathLocks
from .types import CLEANUP, CONVERT_MP4, MONTAGE, MOVE, REINDEX, THUMBNAILS

logger = logging.getLogger(__name__)

MAX_LISTED = 500
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
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
    locks: PathLocks = dataclasses.field(default_factory=PathLocks)


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

    def _display(self, path: Path) -> str:
        return self._rel(path) if path.is_relative_to(self.deps.root_path) else str(path)

    @contextlib.asynccontextmanager
    async def _locked(self, ctx: JobContext, paths: Sequence[Path], *, exclusive: bool) -> AsyncIterator[None]:
        '''Serialize with other jobs in this process touching overlapping folders (unless both only read).'''
        announced = False

        async def waiting(blocker: Path) -> None:
            nonlocal announced
            if not announced:
                ctx.log(f"Waiting for another job working on {self._display(blocker)}")
                announced = True
            await ctx.checkpoint(None, f"Waiting for job on {self._display(blocker)}", force=True)

        async with self.deps.locks.hold(paths, exclusive=exclusive, on_wait=waiting):
            if announced:
                ctx.log("Resuming")
            yield

    async def _scan(self, path: Path, ctx: JobContext) -> MediaDir:
        if not path.is_dir():
            raise PermanentJobError(f"Directory not found: {self._rel(path)}", code="not_found")
        ctx.log(f"Listing files in {self._rel(path)} ...")
        await ctx.checkpoint(0, f"Listing files in {self._rel(path)}", force=True)
        mdir = await asyncio.to_thread(MediaDir.from_path, path)
        ctx.log(
            f"Found {len(mdir.all_dirs())} directories, {len(mdir.all_video_files())} videos, "
            f"{len(mdir.all_image_files())} images"
        )
        return mdir

    async def _reindex(self, path: Path, ctx: JobContext, lo: float = 0, hi: float = 100) -> Result:
        '''Rescan `path` into the index: upsert every directory, drop stale ones, probe new videos.'''
        mdir = await self._scan(path, ctx)
        dirs, videos_coll = self.deps.index.dirs, self.deps.index.videos
        scan_id = f"{ctx.job_id}:{ctx.job.attempt_count}"
        mid = lo + (hi - lo) * 0.4

        all_dirs = mdir.all_dirs()
        n = len(all_dirs)
        errors: list[str] = []
        ctx.log(f"Indexing {n} directories")
        for i, md in enumerate(all_dirs, 1):
            rel = self._rel(md.path)
            try:
                doc = await asyncio.to_thread(MediaDirIndexDoc.from_media_dir_scan, md)
                await dirs.upsert_directory(doc, scan_id=scan_id)
                ctx.log(f"[{i}/{n}] {rel}: {len(doc.video_files)} videos, {len(doc.image_files)} images")
            except Exception as e:
                logger.warning("Could not index %s; keeping previous entry", md.path, exc_info=True)
                errors.append(f"{rel}: {type(e).__name__}: {e}")
                ctx.log(f"[{i}/{n}] {rel}: ERROR {type(e).__name__}: {e} (kept previous entry)")
                await dirs.touch(md.path, scan_id)
            await ctx.checkpoint(_span(lo, mid, i, n), f"Indexing directories {i}/{n}: {rel}")
        removed = await dirs.delete_stale(path, scan_id)
        if removed:
            ctx.log(f"Removed {removed} directories that no longer exist")
        await self._link_into_parent(path)

        all_videos = mdir.all_video_files()
        m = len(all_videos)
        new_videos, probe_errors = 0, 0
        ctx.log(f"Checking {m} videos for new files")
        for i, vf in enumerate(all_videos, 1):
            rel = self._rel(vf.path)
            file_hash = await asyncio.to_thread(index_hash_func, vf.path)
            if not await videos_coll.check_exists(file_hash):
                try:
                    vdoc = await asyncio.to_thread(VideoIndexDoc.from_video_file_scan, vf, file_hash)
                    await videos_coll.insert(vdoc)
                    new_videos += 1
                    ctx.log(f"[{i}/{m}] new: {rel} ({vdoc.probe.duration_str()})")
                except (FFMPEGError, pydantic.ValidationError) as e:
                    probe_errors += 1
                    errors.append(f"{rel}: {type(e).__name__}")
                    ctx.log(f"[{i}/{m}] unreadable: {rel} ({type(e).__name__})")
                except pymongo.errors.DuplicateKeyError:
                    pass
            await ctx.checkpoint(_span(mid, hi, i, m), f"Probing videos {i}/{m}: {rel}")
        ctx.log(f"Videos: {new_videos} new, {m - new_videos - probe_errors} already indexed, {probe_errors} unreadable")

        return {
            "directories": n,
            "directories_removed": removed,
            "videos": m,
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


    async def _unlink_from_parent(self, path: Path) -> None:
        '''Drop `path` from an indexed parent's subdirectory list (after the folder was removed).'''
        try:
            parent = await self.deps.index.dirs.find_by_path(path.parent)
        except MediaDirIndexNotFoundError:
            return
        if parent is not None and parent.subpaths.pop(path.name, None) is not None:
            await self.deps.index.dirs.upsert_directory(parent)


class ReindexHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ReindexRequest)
        path = self._target(req.path)
        async with self._locked(ctx, [path], exclusive=True):
            result = await self._reindex(path, ctx)
        await self.deps.records.set_result(job_id, result)
        return None


class ThumbnailsHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ThumbnailsRequest)
        path = self._target(req.path)
        async with self._locked(ctx, [path], exclusive=False):
            result = await self._run(req, path, ctx)
        await self.deps.records.set_result(job_id, result)
        return None

    async def _run(self, req: ThumbnailsRequest, path: Path, ctx: JobContext) -> Result:
        mdir = await self._scan(path, ctx)
        videos = list(mdir.all_video_files())
        self.deps.thumb_path.mkdir(parents=True, exist_ok=True)
        created, skipped = 0, 0
        errors: list[str] = []
        claimed: set[str] = set()
        ctx.log(f"Generating thumbnails with {req.workers} parallel ffmpeg processes"
                + (" (regenerating existing)" if req.overwrite else ""))

        async def one(vf: VideoFile) -> None:
            nonlocal created, skipped
            file_hash = await asyncio.to_thread(index_hash_func, vf.path)
            out = self.deps.thumb_path / f"{file_hash}.gif"
            # Identical files share a hash (and thumbnail); only generate it once.
            if file_hash in claimed or (not req.overwrite and out.exists() and out.stat().st_size > 0):
                skipped += 1
                return
            claimed.add(file_hash)
            tmp = self.deps.thumb_path / f".{file_hash}.{uuid.uuid4().hex[:8]}.tmp.gif"
            try:
                await asyncio.to_thread(
                    make_animated_thumb, vf.path, str(tmp),
                    fps=THUMB_FPS, target_period=THUMB_PERIOD_SEC, width=THUMB_WIDTH, height=-1, overwrite=True,
                )
                os.replace(tmp, out)
                created += 1
                ctx.log(f"created: {self._rel(vf.path)}")
            except FFMPEGError as e:
                errors.append(f"{self._rel(vf.path)}: {type(e).__name__}")
                ctx.log(f"failed: {self._rel(vf.path)} ({type(e).__name__})")
            finally:
                tmp.unlink(missing_ok=True)

        await _bounded(videos, one, req.workers, ctx, lambda n: (_span(0, 100, n, len(videos)), f"Thumbnails {n}/{len(videos)}"))
        ctx.log(f"Thumbnails: {created} created, {skipped} already existed, {len(errors)} failed")
        return {
            "videos": len(videos), "created": created, "skipped_existing": skipped,
            "errors": _capped(errors), "error_count": len(errors),
        }


class CleanupHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, CleanupRequest)
        path = self._target(req.path)
        async with self._locked(ctx, [path], exclusive=not req.dry_run):
            result = await self._run(req, path, ctx)
        await self.deps.records.set_result(job_id, result)
        return None

    async def _run(self, req: CleanupRequest, path: Path, ctx: JobContext) -> Result:
        mdir = await self._scan(path, ctx)
        videos = [vf for vf in mdir.all_video_files() if vf.path.exists()]
        empty: list[Path] = []
        unprobable: list[Path] = []
        duplicates: list[tuple[Path, Path]] = []
        ctx.log("Dry run: nothing will be deleted" if req.dry_run else "Matching files WILL be deleted")

        if req.delete_empty:
            empty = [vf.path for vf in videos if vf.path.stat().st_size == 0]
            for p in empty:
                ctx.log(f"empty: {self._rel(p)}")
        flagged = set(empty)

        if req.delete_unprobable:
            candidates = [vf for vf in videos if vf.path not in flagged]
            for i, vf in enumerate(candidates, 1):
                try:
                    await asyncio.to_thread(vf.probe)
                except FFMPEGError as e:
                    unprobable.append(vf.path)
                    ctx.log(f"unprobable: {self._rel(vf.path)} ({type(e).__name__})")
                await ctx.checkpoint(_span(0, 50, i, len(candidates)), f"Probing {i}/{len(candidates)}")
            flagged |= set(unprobable)

        if req.delete_duplicates:
            all_dirs = mdir.all_dirs()
            for i, md in enumerate(all_dirs, 1):
                in_dir = [vf.path for vf in md.videos if vf.path.exists() and vf.path not in flagged]
                found = await asyncio.to_thread(fileops.find_duplicates, in_dir)
                for dup, kept in found:
                    ctx.log(f"duplicate: {self._rel(dup)} (same as {kept.name})")
                duplicates += found
                await ctx.checkpoint(_span(50, 80, i, len(all_dirs)), f"Comparing files {i}/{len(all_dirs)} dirs")

        to_delete = empty + unprobable + [dup for dup, _ in duplicates]
        if not req.dry_run:
            for i, p in enumerate(to_delete, 1):
                p.unlink(missing_ok=True)
                ctx.log(f"deleted: {self._rel(p)}")
                await ctx.checkpoint(_span(80, 85, i, len(to_delete)), f"Deleting {i}/{len(to_delete)}")
        ctx.log(f"{'Would delete' if req.dry_run else 'Deleted'} {len(to_delete)} files "
                f"({len(empty)} empty, {len(unprobable)} unprobable, {len(duplicates)} duplicates)")

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
        return result


class ConvertMp4Handler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, ConvertMp4Request)
        path = self._target(req.path)
        async with self._locked(ctx, [path], exclusive=True):
            result = await self._run(job_id, path, ctx)
        await self.deps.records.set_result(job_id, result)
        return None

    async def _run(self, job_id: str, path: Path, ctx: JobContext) -> Result:
        mdir = await self._scan(path, ctx)
        sources = [vf.path for vf in mdir.all_video_files() if vf.path.suffix.lower() != ".mp4"]
        total = len(sources)
        converted, skipped = 0, 0
        errors: list[str] = []
        ctx.log(f"{total} non-MP4 videos")
        for i, src in enumerate(sources, 1):
            dst = src.with_suffix(".mp4")
            if dst.exists():
                skipped += 1
                ctx.log(f"[{i}/{total}] skipped (MP4 exists): {self._rel(src)}")
            else:
                ctx.log(f"[{i}/{total}] converting: {self._rel(src)}")
                await ctx.checkpoint(_span(0, 85, i - 1, total), f"Converting {i}/{total}: {self._rel(src)}", force=True)
                tmp = dst.with_name(f".{dst.stem}.{job_id[:8]}.tmp.mp4")
                try:
                    await asyncio.to_thread(ffmpeg(input=ffinput(src), output=ffoutput(tmp, y=True)).run)
                    os.replace(tmp, dst)
                    converted += 1
                except FFMPEGError as e:
                    errors.append(f"{self._rel(src)}: {type(e).__name__}")
                    ctx.log(f"[{i}/{total}] failed: {self._rel(src)} ({type(e).__name__})")
                finally:
                    tmp.unlink(missing_ok=True)
            await ctx.checkpoint(_span(0, 85, i, total), f"Converting {i}/{total}")

        result: Result = {
            "candidates": total, "converted": converted, "skipped_existing": skipped,
            "errors": _capped(errors), "error_count": len(errors),
        }
        if converted:
            result["reindex"] = await self._reindex(path, ctx, 85, 100)
        return result


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    return value.replace(tzinfo=datetime.timezone.utc) if value.tzinfo is None else value.astimezone(datetime.timezone.utc)


class MontageHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, MontageRequest)
        sources = []
        for source in req.sources:
            try:
                sources.append(resolve_allowed_source(source, (self.deps.root_path, *self.deps.copy_source_roots)))
            except PathOutsideRootError as e:
                raise PermanentJobError(str(e), code="invalid_source") from e
        output = self._target(req.output)
        if output.exists() and not req.overwrite:
            raise PermanentJobError(f"Output already exists: {req.output}", code="output_exists")
        async with self._locked(ctx, [output.parent], exclusive=True):
            result = await self._run(job_id, req, sources, output, ctx)
        await self.deps.records.set_result(job_id, result)
        return None

    async def _run(self, job_id: str, req: MontageRequest, sources: list[Path], output: Path, ctx: JobContext) -> Result:
        start, end = _as_utc(req.start), _as_utc(req.end)
        candidates: list[Path] = []
        for source in sources:
            if not source.is_dir():
                raise PermanentJobError(f"Source directory not found: {source}", code="not_found")
            ctx.log(f"Listing files in {source} ...")
            found = await asyncio.to_thread(
                lambda s=source: [
                    p for p in s.rglob("*")
                    if p.suffix.lower() in VIDEO_SUFFIXES and p.is_file()
                    and (req.name_contains is None or req.name_contains in p.name)
                ]
            )
            candidates.extend(found)
        candidates = sorted(set(candidates))
        total = len(candidates)
        ctx.log(f"Probing {total} videos for creation_time between {start.isoformat()} and {end.isoformat()}")

        selected: list[Path] = []
        undated, errors = 0, []
        for i, path in enumerate(candidates, 1):
            try:
                info = await asyncio.to_thread(probe, path)
                raw = (info.tags or {}).get("creation_time")
                if raw is None:
                    undated += 1
                elif start <= _as_utc(datetime.datetime.fromisoformat(str(raw))) <= end:
                    selected.append(path)
            except (FFMPEGError, ValueError, OverflowError) as e:
                errors.append(f"{self._display(path)}: {type(e).__name__}")
                ctx.log(f"unreadable: {self._display(path)} ({type(e).__name__})")
            await ctx.checkpoint(_span(0, 30, i, total), f"Probing videos {i}/{total}")
        ctx.log(f"{len(selected)} of {total} videos are in the date range ({undated} without creation_time)")

        result: Result = {
            "output": req.output,
            "videos_found": total,
            "videos_selected": len(selected),
            "videos_without_creation_time": undated,
            "errors": _capped(errors),
            "error_count": len(errors),
        }
        if not selected:
            raise PermanentJobError("No videos matched the date range.", code="no_videos")

        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_name(f".{output.stem}.{job_id[:8]}.tmp.mp4")
        ctx.log(f"Creating montage {req.output} from {len(selected)} videos (this step cannot be canceled midway)")
        await ctx.checkpoint(30, "Rendering montage", force=True)
        try:
            await asyncio.to_thread(
                create_montage,
                video_files=selected,
                output_filename=str(tmp),
                clip_ratio=req.clip_ratio,
                clip_duration=req.clip_duration,
                random_seed=req.random_seed,
                width=req.width,
                height=req.height,
                fps=req.fps,
                use_cuda=req.use_cuda,
                num_cores=req.workers,
                tmp_dir=output.parent,  # clips can be many GB; /tmp may be RAM-backed
                max_clips_per_video=req.max_clips_per_video,
                max_total_clips=req.max_total_clips,
                shuffle_clips=req.shuffle_clips,
                overwrite=True,
            )
            os.replace(tmp, output)
        except FFMPEGError as e:
            raise PermanentJobError(f"ffmpeg failed: {e}", code="ffmpeg_failed") from e
        finally:
            tmp.unlink(missing_ok=True)
        ctx.log("Montage created")
        result["reindex"] = await self._reindex(output.parent, ctx, 90, 100)
        return result


class MoveIncompleteError(Exception):
    '''Some entries could not be moved, so the source folder still exists. Retried, as the cause may be transient.'''


class MoveHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, MoveRequest)
        try:
            source = resolve_allowed_source(req.source, self.deps.copy_source_roots)
        except PathOutsideRootError as e:
            raise PermanentJobError(str(e), code="invalid_source") from e
        if fileops.is_protected_root(source, self.deps.copy_source_roots):
            raise PermanentJobError(
                "A copy source root itself can't be moved, because the source folder is removed afterwards.",
                code="protected_source",
            )
        if not source.is_dir():
            if ctx.job.attempt_count <= 1:
                raise PermanentJobError(f"Source directory not found: {source}", code="not_found")
            ctx.log("The source folder is already gone (emptied by an earlier attempt)")
        dest = self._target(req.dest)
        # Lock the real locations too, so a symlink alias can't dodge another job's lock.
        async with self._locked(ctx, [source, source.resolve(), dest, dest.resolve()], exclusive=True):
            await self._run(job_id, req, source, dest, ctx)
        return None

    async def _run(self, job_id: str, req: MoveRequest, source: Path, dest: Path, ctx: JobContext) -> None:
        root = self.deps.root_path
        # Index entries live under the source's path as the gallery sees it, which may be a link or its target.
        in_gallery = [p for p in dict.fromkeys((source, Path(os.path.realpath(source)))) if p.is_relative_to(root)]
        files: list[Path] = []
        others: list[Path] = []
        if source.is_dir():
            ctx.log(f"Listing files in {source} ...")
            await ctx.checkpoint(0, "Listing source files", force=True)
            if blocked := await asyncio.to_thread(fileops.unwritable_dirs, source):
                raise PermanentJobError(fileops.permission_message(source, blocked), code="permission_denied")
            files, others = await asyncio.to_thread(fileops.list_source_files, source)
        total_bytes = sum(f.stat().st_size for f in files) or 1
        ctx.log(f"Moving {len(files)} files ({total_bytes / 1e9:.2f} GB) and {len(others)} link(s) to {self._rel(dest)} "
                f"with {req.workers} parallel transfers")
        dest.mkdir(parents=True, exist_ok=True)
        tally = dict.fromkeys(fileops.MoveOutcome, 0)
        renamed: list[str] = []
        failed: list[str] = []
        processed_bytes = 0
        messages = {
            fileops.MoveOutcome.MOVED: "moved",
            fileops.MoveOutcome.DEDUPLICATED: "already present (same size), removed from source",
        }

        def note(rel: Path, moved: fileops.Moved, is_link: bool = False) -> None:
            if not is_link:
                tally[moved.outcome] += 1  # links are counted separately
            if moved.outcome is fileops.MoveOutcome.RENAMED:
                new = moved.path.relative_to(dest)
                renamed.append(f"{rel} -> {new}")
                ctx.log(f"RENAMED, something else is already at the destination: {rel} -> {new}")
            else:
                ctx.log(f"{'link ' if is_link else ''}{messages[moved.outcome]}: {rel}")

        async def one(src: Path) -> None:
            nonlocal processed_bytes
            size = src.stat().st_size
            rel = src.relative_to(source)
            try:
                moved = await asyncio.to_thread(fileops.move_file, src, dest / rel, job_id[:8], True)
            except OSError as e:
                failed.append(f"{rel}: {e.strerror or e}")
                ctx.log(f"ERROR, left in source: {rel} ({e.strerror or e})")
                return
            finally:
                processed_bytes += size
            note(rel, moved)

        await _bounded(files, one, req.workers, ctx, lambda n: (80 * processed_bytes / total_bytes, f"Moving files {n}/{len(files)}"))
        links_moved = 0
        for link in others:
            rel = link.relative_to(source)
            try:
                moved = await asyncio.to_thread(fileops.move_entry, link, dest / rel)
            except OSError as e:
                failed.append(f"{rel}: {e.strerror or e}")
                ctx.log(f"ERROR, left in source: {rel} ({e.strerror or e})")
                continue
            links_moved += 1
            note(rel, moved, is_link=True)

        await ctx.checkpoint(80, "Removing the source folder", force=True)
        remaining = await asyncio.to_thread(fileops.remove_source_tree, source)
        source_removed = not os.path.lexists(source)
        ctx.log("Source folder removed" if source_removed else f"Source folder NOT removed: {len(remaining)} item(s) left")
        ctx.log(f"Moved {tally[fileops.MoveOutcome.MOVED]}, {tally[fileops.MoveOutcome.DEDUPLICATED]} already present, "
                f"{len(renamed)} renamed, {len(failed)} errors")

        warnings: list[pydantic.JsonValue] = []
        if renamed:
            warnings.append(f"{len(renamed)} file(s) clashed with a different file at the destination and were kept under a numbered name.")
        if links_moved:
            warnings.append(f"{links_moved} symlink(s)/special file(s) were moved as they are; a relative link may now point elsewhere.")
        if failed:
            warnings.append(f"{len(failed)} entr(ies) could not be moved (see log).")
        result: Result = {
            "source": str(source),
            "dest": self._rel(dest),
            "files": len(files),
            "moved": tally[fileops.MoveOutcome.MOVED],
            "deduplicated": tally[fileops.MoveOutcome.DEDUPLICATED],
            "renamed": _capped(renamed),
            "links_moved": links_moved,
            "failed": _capped(failed),
            "source_removed": source_removed,
            "warnings": warnings,
        }
        await self.deps.records.set_result(job_id, result)

        dest_lo = 90 if in_gallery else 82
        if in_gallery:
            ctx.log(f"Source is inside the gallery; updating the index for {self._rel(in_gallery[0])}")
            source_results = [await self._rescan_source(p, ctx, 82, dest_lo) for p in in_gallery]
            result["source_reindex"] = source_results[0]
            await self.deps.records.set_result(job_id, result)
        ctx.log(f"Rescanning {self._rel(dest)}")
        result["reindex"] = await self._reindex(dest, ctx, dest_lo, 100)
        await self.deps.records.set_result(job_id, result)

        if not source_removed:
            first = "; ".join(failed[:3]) or ", ".join(str(p.relative_to(source)) for p in remaining[:3])
            raise MoveIncompleteError(
                f"The source folder still exists: {len(remaining)} item(s) could not be moved. {first}"
            )

    async def _rescan_source(self, source: Path, ctx: JobContext, lo: float, hi: float) -> Result:
        if source.is_dir():
            return await self._reindex(source, ctx, lo, hi)
        removed = await self.deps.index.dirs.delete_by_path_prefix(source)
        await self._unlink_from_parent(source)
        ctx.log(f"Source no longer exists; removed {removed} directories from the index")
        return {"directories": 0, "directories_removed": removed, "videos": 0, "videos_new": 0, "errors": [], "error_count": 0}


def build_handlers(deps: MediaJobDeps) -> dict[str, JobHandler]:
    return {
        REINDEX: ReindexHandler(deps),
        THUMBNAILS: ThumbnailsHandler(deps),
        CLEANUP: CleanupHandler(deps),
        CONVERT_MP4: ConvertMp4Handler(deps),
        MOVE: MoveHandler(deps),
        MONTAGE: MontageHandler(deps),
    }
