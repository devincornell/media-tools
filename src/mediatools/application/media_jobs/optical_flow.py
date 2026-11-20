"""Optical flow job: estimate and cache dense flow for a video, then render the requested videos from it.

The flow code lives in `mediatools.vision` (an optional extra), so it is imported only when a job runs;
a worker without the extra fails these jobs with a clear message instead of failing to start.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import typing
from collections.abc import Generator, Iterator
from pathlib import Path

import pydantic

from ...contracts import OpticalFlowRequest
from ...jobs import JobContext, PermanentJobError
from ..errors import PathOutsideRootError
from ..paths import resolve_allowed_source
from .handlers import MAX_LISTED, Result, _Base, _span

if typing.TYPE_CHECKING:
    from ...vision import FlowVideo

# Share of the progress bar used by estimating flow, rendering, and rescanning the output folders.
RENDER_START, RENDER_END = 60, 95


async def _next(iterator: Generator[int, None, None]) -> int | None:
    '''Advance a blocking generator on a worker thread, so the event loop (leases, progress) keeps running.'''
    return await asyncio.to_thread(next, iterator, None)


def _close(iterator: Generator[int, None, None]) -> None:
    # A generator still executing on its thread (after a cancel) refuses to close; it is closed when collected.
    with contextlib.suppress(ValueError):
        iterator.close()


def _merge_rescans(rescans: list[Result]) -> Result:
    '''One rescan result in the shape of a single `_reindex`, for outputs that landed in different folders.'''
    merged: Result = {}
    for key in ("directories", "directories_removed", "videos", "videos_new", "error_count"):
        merged[key] = sum(int(typing.cast(int, r[key])) for r in rescans)
    merged["errors"] = [e for r in rescans for e in typing.cast(list[pydantic.JsonValue], r["errors"])][:MAX_LISTED]
    return merged


@contextlib.contextmanager
def _flow_errors() -> Iterator[None]:
    '''Out-of-memory is retried (another job may have been using the GPU); other flow errors would only repeat.'''
    from ...vision import DeviceMemoryError, OpticalFlowError

    try:
        yield
    except DeviceMemoryError:
        raise
    except OpticalFlowError as e:
        raise PermanentJobError(str(e), code="optical_flow_failed") from e


class OpticalFlowHandler(_Base):
    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        req = await self._load(job_id, OpticalFlowRequest)
        try:
            importlib.import_module("mediatools.vision")
        except ImportError as e:
            raise PermanentJobError(
                f"Optical flow needs the 'vision' extra on the worker (pip install 'mediatools[vision]'): {e}",
                code="missing_dependency",
            ) from e
        result = await self._run(job_id, req, ctx)
        await self.deps.records.set_result(job_id, result)
        return None

    async def _run(self, job_id: str, req: OpticalFlowRequest, ctx: JobContext) -> Result:
        from ...vision import FlowSettings, FlowVideo, OpticalFlowError

        source = self._source(req.video)
        overlay = self._output(req.overlay_output, req.overwrite)
        particles = self._output(req.particles_output, req.overwrite)
        outputs = [o for o in (overlay, particles) if o is not None]
        settings = FlowSettings(
            algorithm=req.algorithm,
            step=req.step,
            cache_height=req.cache_height,
            dis_preset=req.dis_preset,
            raft_max_height=req.raft_max_height,
            raft_variant=req.raft_variant,
            raft_flow_updates=req.raft_flow_updates,
        )
        try:
            flow = await asyncio.to_thread(FlowVideo, source, settings, self.deps.flow_cache_path, req.max_frames)
        except OpticalFlowError as e:
            raise PermanentJobError(str(e), code="invalid_video") from e
        total = len(flow.pairs)
        if total == 0:
            raise PermanentJobError("The video has no frame pairs to estimate flow between.", code="no_frames")

        missing = flow.missing(req.recompute)
        ctx.log(f"{self._display(source)}: {total} frame pairs, {total - len(missing)} cached, {len(missing)} to compute")
        ctx.log(f"Flow cache: {flow.cache.directory}")
        computed = 0
        if missing:
            # One estimation at a time per worker process: RAFT on a shared GPU would otherwise run out of memory.
            async with self._locked(ctx, [self.deps.flow_cache_path], exclusive=True):
                computed = await self._estimate(flow, missing, ctx, 0, RENDER_START if outputs else 100)

        result: Result = {
            "video": req.video,
            "algorithm": req.algorithm,
            "pairs": total,
            "flows_cached": total - len(missing),
            "flows_computed": computed,
            "frames_written": 0,
            "overlay_output": req.overlay_output,
            "particles_output": req.particles_output,
        }
        if not outputs:
            return result
        if not flow.cache.has(0):
            raise PermanentJobError("No optical flow could be computed for this video.", code="no_flow")

        parents = sorted({o.parent for o in outputs})
        async with self._locked(ctx, parents, exclusive=True):
            result["frames_written"] = await self._render(job_id, flow, req, overlay, particles, ctx)
            rescans: list[Result] = []
            for i, parent in enumerate(parents):
                rescans.append(await self._reindex(
                    parent, ctx, _span(RENDER_END, 100, i, len(parents)), _span(RENDER_END, 100, i + 1, len(parents))
                ))
            result["reindex"] = _merge_rescans(rescans)
        return result

    async def _estimate(self, flow: FlowVideo, missing: list[int], ctx: JobContext, lo: float, hi: float) -> int:
        '''Compute the missing pairs, one per thread call, reporting progress and honoring cancellation between pairs.'''
        note = " (RAFT weights download on first use)" if flow.settings.algorithm == "raft" else ""
        ctx.log(f"Estimating {len(missing)} flows with {flow.settings.algorithm}{note}")
        await ctx.checkpoint(lo, "Loading flow model", force=True)
        done = 0
        iterator = flow.compute(missing)
        try:
            with _flow_errors():
                while await _next(iterator) is not None:
                    done += 1
                    if done % 100 == 0:
                        ctx.log(f"Computed {done}/{len(missing)} flows")
                    await ctx.checkpoint(_span(lo, hi, done, len(missing)), f"Estimating flow {done}/{len(missing)}")
        finally:
            _close(iterator)
        if done < len(missing):
            ctx.log(f"The video ended early: {len(missing) - done} frame pairs could not be computed")
        return done

    async def _render(
        self,
        job_id: str,
        flow: FlowVideo,
        req: OpticalFlowRequest,
        overlay: Path | None,
        particles: Path | None,
        ctx: JobContext,
    ) -> int:
        '''Write the videos next to their final names, then move them into place once complete.'''
        from ...vision import OverlayOptions, ParticleOptions

        tmp: dict[Path, Path] = {}
        for out in (overlay, particles):
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                tmp[out] = out.with_name(f".{out.stem}.{job_id[:8]}.tmp.mp4")
        overlay_options = None if overlay is None else OverlayOptions(
            output=tmp[overlay],
            side_by_side=req.side_by_side,
            alpha=req.alpha,
            max_flow=req.max_flow,
            arrow_every=req.arrow_every,
            arrow_scale=req.arrow_scale,
        )
        particle_options = None if particles is None else ParticleOptions(
            output=tmp[particles],
            count=req.particle_count,
            lifetime=req.particle_lifetime,
            fade=req.particle_fade,
            substeps=req.particle_substeps,
            seed=req.particle_seed,
            white=req.particle_white,
            height=req.particle_height,
        )
        total = len(flow.pairs)
        written = 0
        ctx.log("Rendering " + " and ".join(
            label for label, out in (("overlay video", overlay), ("particle video", particles)) if out is not None
        ))
        await ctx.checkpoint(RENDER_START, "Rendering", force=True)
        iterator = flow.render(overlay_options, particle_options)
        try:
            with _flow_errors():
                while (n := await _next(iterator)) is not None:
                    written = n
                    await ctx.checkpoint(_span(RENDER_START, RENDER_END, n, total), f"Rendering frame {n}/{total}")
            for final, partial in tmp.items():
                os.replace(partial, final)
        finally:
            _close(iterator)
            for partial in tmp.values():
                partial.unlink(missing_ok=True)
        for out in tmp:
            ctx.log(f"Wrote {written} frames to {self._rel(out)}")
        return written

    def _source(self, video: str) -> Path:
        try:
            path = resolve_allowed_source(video, (self.deps.root_path, *self.deps.copy_source_roots))
        except PathOutsideRootError as e:
            raise PermanentJobError(str(e), code="invalid_source") from e
        if not path.is_file():
            raise PermanentJobError(f"Video not found: {video}", code="not_found")
        return path

    def _output(self, rel: str | None, overwrite: bool) -> Path | None:
        if rel is None:
            return None
        path = self._target(rel)
        if path.exists() and not overwrite:
            raise PermanentJobError(f"Output already exists: {rel}", code="output_exists")
        return path
