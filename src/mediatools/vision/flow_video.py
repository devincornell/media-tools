"""Optical flow over a whole video: estimate and cache flow per frame pair, then render it.

The work is exposed as generators that yield after each frame pair, so a caller can report
progress or stop early between pairs (the CLI script prints; the job handler checkpoints and
checks for cancellation). Closing a generator releases the video and finishes any open writers.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Generator, Sequence
from pathlib import Path

import cv2
import numpy as np

from ..video.h264_writer import H264Writer
from .flow_cache import FlowCache, FlowSettings
from .flow_render import (
    ParticleSystem,
    compose_overlay,
    draw_particles,
    particle_output_size,
)
from .optical_flow_domain import BgrFrame, OpticalFlowError


@dataclasses.dataclass(frozen=True)
class OverlayOptions:
    """The source video with the flow color wheel and motion arrows drawn over it."""

    output: Path
    side_by_side: bool = False
    alpha: float = 0.5
    max_flow: float | None = None  # pixels that map to full brightness; default 2% of the width per step
    arrow_every: int = 48  # grid spacing in pixels; 0 disables arrows
    arrow_scale: float = 3.0


@dataclasses.dataclass(frozen=True)
class ParticleOptions:
    """Particles on a black background that drift with the flow."""

    output: Path
    count: int = 4000
    lifetime: int = 90  # frames before a particle respawns elsewhere
    fade: float = 0.85  # fraction of the previous frame kept each frame; higher = longer trails
    substeps: int = 4  # integration steps per frame of flow
    seed: int = 0
    white: bool = False  # draw white instead of coloring by direction
    height: int = 720  # output height, keeping aspect (0 = source size)


class FlowVideo:
    """One video's flow: which frame pairs exist in the cache, and the steps to fill and render them.

    Pair `k` is the flow between frames `k * step` and `(k + 1) * step`. With `max_frames`, only the
    first that many pairs are considered.
    """

    def __init__(
        self, video: Path, settings: FlowSettings, cache_dir: Path, max_frames: int | None = None
    ) -> None:
        if max_frames is not None and max_frames < 1:
            raise ValueError(f"max_frames must be at least 1, got {max_frames}.")
        self.video = video
        self.settings = settings
        cap = cv2.VideoCapture(str(video))
        try:
            if not cap.isOpened():
                raise OpticalFlowError(f"Could not open video: {video}")
            self.fps = float(cap.get(cv2.CAP_PROP_FPS))
            self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        finally:
            cap.release()
        if self.width < 2 or self.height < 2:
            raise OpticalFlowError(f"Video is too small: {self.width}x{self.height}.")
        total = max(0, (frame_count - 1) // settings.step)
        self.pairs = range(total if max_frames is None else min(total, max_frames))
        self.cache = FlowCache(cache_dir, video, settings, self.width, self.height)

    def missing(self, recompute: bool = False) -> list[int]:
        """The pairs that still need to be computed (all of them with `recompute`)."""
        return [k for k in self.pairs if recompute or not self.cache.has(k)]

    def compute(self, pairs: Sequence[int]) -> Generator[int, None, None]:
        """Estimate and cache the flow for each pair in `pairs`, in one pass over the video.

        Yields each pair index once it is cached. Frames that no listed pair needs are skipped
        without being decoded. The estimator (which may download model weights) loads on first use.
        """
        step = self.settings.step
        todo = set(pairs)
        wanted = sorted({k * step for k in pairs} | {(k + 1) * step for k in pairs})
        cap = cv2.VideoCapture(str(self.video))
        if not cap.isOpened():
            raise OpticalFlowError(f"Could not open video: {self.video}")
        try:
            estimator = self.settings.build_estimator()
            position = 0
            previous: tuple[int, BgrFrame] | None = None
            for index in wanted:
                while position < index:
                    cap.grab()
                    position += 1
                success, frame = cap.read()
                position += 1
                if not success:
                    return  # the video ended early; later pairs stay uncached
                pair = index // step - 1
                if previous is not None and previous[0] == index - step and pair in todo:
                    self.cache.save(pair, estimator.estimate(previous[1], frame))  # type: ignore[arg-type]
                    yield pair
                previous = (index, frame)  # type: ignore[assignment]
        finally:
            cap.release()

    def render(
        self, overlay: OverlayOptions | None = None, particles: ParticleOptions | None = None
    ) -> Generator[int, None, None]:
        """Write the requested videos from the cached flow, yielding the number of frames written so far.

        Stops at the first pair that is not cached. Output plays at the source frame rate divided by
        `step`, since flow exists only every `step` frames.
        """
        step = self.settings.step
        out_fps = self.fps / step
        cap = overlay_writer = particle_writer = None
        system = canvas = None
        try:
            if overlay is not None:
                cap = cv2.VideoCapture(str(self.video))
                if not cap.isOpened():
                    raise OpticalFlowError(f"Could not open video: {self.video}")
                size = (self.width * 2 if overlay.side_by_side else self.width, self.height)
                overlay_writer = H264Writer(overlay.output, out_fps, size)
                max_flow = overlay.max_flow or 0.02 * self.width * step
            if particles is not None:
                size = particle_output_size(self.width, self.height, particles.height)
                scale = size[0] / self.width  # simulate in source pixels, draw at output size
                thickness = max(1, size[0] // 1280)
                system = ParticleSystem(
                    particles.count, self.width, self.height, particles.lifetime, np.random.default_rng(particles.seed)
                )
                canvas = np.zeros((size[1], size[0], 3), dtype=np.uint8)
                particle_writer = H264Writer(particles.output, out_fps, size)

            for k in self.pairs:
                if not self.cache.has(k):
                    break  # the video ended before this pair
                flow = self.cache.load(k)
                if overlay is not None and cap is not None and overlay_writer is not None:
                    success, frame = cap.read()
                    if not success:
                        raise OpticalFlowError(f"Video ended after {k} frames.")
                    for _ in range(step - 1):
                        cap.grab()
                    overlay_writer.write(compose_overlay(
                        frame, flow, max_flow, overlay.alpha, overlay.arrow_every, overlay.arrow_scale,  # type: ignore[arg-type]
                        overlay.side_by_side,
                    ))
                if particles is not None and system is not None and canvas is not None and particle_writer is not None:
                    previous, alive = system.advance(flow.vectors, particles.substeps)
                    canvas = (canvas * np.float32(particles.fade)).astype(np.uint8)
                    draw_particles(canvas, previous[alive], system.positions[alive], scale, particles.white, thickness)
                    particle_writer.write(canvas)
                yield k + 1  # frames written so far
        finally:
            if cap is not None:
                cap.release()
            for writer in (overlay_writer, particle_writer):
                if writer is not None:
                    writer.close()
