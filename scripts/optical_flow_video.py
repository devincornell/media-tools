"""Estimate dense optical flow for a video, cache it, and optionally render it two ways.

By default this only fills the flow cache. Each output is enabled by giving it a filename:

  --overlay-output FILE    the source frame with the flow drawn on top: a color-wheel
                           layer (hue = direction, brightness = speed) blended in, plus a
                           sparse grid of motion arrows.
  --particles-output FILE  particles on a black background that drift with the flow. A
                           particle's velocity is the flow at its exact sub-pixel position
                           (bilinear interpolation). Each frame's flow is integrated in
                           --particle-substeps smaller steps, re-sampling the velocity each
                           time so paths curve with the field. Particles that leave the
                           frame or reach --particle-lifetime frames respawn at random.
                           Trails come from fading the previous frame by --particle-fade.

Computed flow is cached on disk, one file per frame pair, keyed by the video (path, size,
modification time), the algorithm and its parameters, `--step`, and `--cache-height`. Any
run, whatever its `--max-frames`, only computes the frame pairs that are not cached yet, so
extending 500 frames to 1000 computes just the new 500 and shrinking back to 500 computes
nothing. Flow is stored downscaled to `--cache-height` rows (float16) to keep the cache
small, and upscaled when rendering; both fresh and cached runs go through that same
round trip, so their output is identical. With no `--max-frames`, the whole video is
processed.

Usage:
    python scripts/optical_flow_video.py VIDEO [--algorithm raft|dis|farneback] [--step N]
        [--max-frames M] [--cache-dir DIR] [--recompute]
        [--overlay-output FILE [--side-by-side] [--alpha A] [--arrow-every PX]]
        [--particles-output FILE [--particle-count N] [--particle-fade F]]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from mediatools.vision import (
    DisFlow,
    FarnebackFlow,
    FlowField,
    OpticalFlowEstimator,
    RaftFlow,
)
from video_writer import H264Writer

BgrFrame = np.ndarray
Positions = npt.NDArray[np.float32]  # (N, 2) x, y in source-video pixels

DEFAULT_CACHE_DIR = Path("~/.cache/mediatools/optical_flow").expanduser()


def estimator_params(args: argparse.Namespace) -> dict[str, object]:
    """The settings that change the computed flow; the device is deliberately excluded."""
    if args.algorithm == "raft":
        params: dict[str, object] = {"max_height": args.raft_max_height, "variant": args.raft_variant}
        if args.raft_flow_updates is not None:
            params["num_flow_updates"] = args.raft_flow_updates
        return params
    if args.algorithm == "dis":
        return {"preset": args.dis_preset}
    return {}


class FlowCache:
    """Per-frame-pair flow files for one (video, algorithm, parameters, step) combination."""

    def __init__(self, root: Path, video: Path, args: argparse.Namespace, width: int, height: int) -> None:
        stat = video.stat()
        self._key = {
            "video": str(video.resolve()),
            "video_size": stat.st_size,
            "video_mtime_ns": stat.st_mtime_ns,
            "algorithm": args.algorithm,
            "params": estimator_params(args),
            "step": args.step,
            "cache_height": args.cache_height,
            "format": 1,
        }
        digest = hashlib.sha256(json.dumps(self._key, sort_keys=True).encode()).hexdigest()[:12]
        self.directory = root / f"{video.stem}-{digest}"
        self._width, self._height = width, height
        if args.cache_height and height > args.cache_height:
            self._size = (max(1, round(width * args.cache_height / height)), args.cache_height)
        else:
            self._size = (width, height)

    def _path(self, index: int) -> Path:
        return self.directory / f"{index:07d}.npy"

    def has(self, index: int) -> bool:
        return self._path(index).is_file()

    def save(self, index: int, flow: FlowField) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        meta = self.directory / "key.json"
        if not meta.exists():
            meta.write_text(json.dumps(self._key, indent=2))
        small_w, small_h = self._size
        hwc = np.moveaxis(flow.vectors, 0, 2)
        if (small_w, small_h) != (self._width, self._height):
            hwc = cv2.resize(hwc, (small_w, small_h), interpolation=cv2.INTER_AREA)
            hwc = hwc * np.array([small_w / self._width, small_h / self._height], dtype=np.float32)
        # Write to a temporary name first so an interrupted run never leaves a truncated file.
        path = self._path(index)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            np.save(f, np.moveaxis(hwc, 2, 0).astype(np.float16))
        os.replace(tmp, path)

    def load(self, index: int) -> FlowField:
        vectors = np.load(self._path(index)).astype(np.float32)
        small_w, small_h = self._size
        if (small_w, small_h) == (self._width, self._height):
            return FlowField.from_array(vectors)
        hwc = cv2.resize(np.moveaxis(vectors, 0, 2), (self._width, self._height), interpolation=cv2.INTER_LINEAR)
        hwc = hwc * np.array([self._width / small_w, self._height / small_h], dtype=np.float32)
        return FlowField.from_hwc(hwc)


def add_flow_args(parser: argparse.ArgumentParser) -> None:
    """The flags that select a flow cache; shared with scripts that read the cache."""
    parser.add_argument("--algorithm", choices=["raft", "dis", "farneback"], default="dis",
                        help="flow estimator; raft is the most accurate, dis the fastest on CPU")  # fmt: skip
    parser.add_argument("--step", type=int, default=1, help="estimate flow between frames N apart")
    parser.add_argument("--dis-preset", choices=["ultrafast", "fast", "medium"], default="medium")
    parser.add_argument("--raft-max-height", type=int, default=360, help="downscale frames to this height for RAFT")
    parser.add_argument("--raft-variant", choices=["small", "large"], default="small")
    parser.add_argument("--raft-flow-updates", type=int, default=None,
                        help="RAFT refinement iterations (model default if unset); more is slower, not larger in memory")  # fmt: skip
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="where computed flow is stored")
    parser.add_argument("--cache-height", type=int, default=360,
                        help="store flow downscaled to this many rows (0 = full resolution, much larger files)")  # fmt: skip


def validate_flow_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.step < 1:
        parser.error("--step must be >= 1")
    if args.cache_height < 0:
        parser.error("--cache-height must be >= 0")


def build_estimator(args: argparse.Namespace) -> OpticalFlowEstimator:
    if args.algorithm == "raft":
        return RaftFlow(
            device=args.device,
            max_height=args.raft_max_height,
            variant=args.raft_variant,
            num_flow_updates=args.raft_flow_updates,
        )
    if args.algorithm == "dis":
        return DisFlow(preset=args.dis_preset)
    return FarnebackFlow()


def compute_missing(video: Path, missing: list[int], cache: FlowCache, args: argparse.Namespace) -> None:
    """Estimate and cache the flow for each pair index in `missing`, in one pass over the video.

    Pair `k` is the flow between frames `k * step` and `(k + 1) * step`. Frames that no
    missing pair needs are skipped without being decoded.
    """
    estimator = build_estimator(args)
    todo = set(missing)
    wanted = sorted({k * args.step for k in missing} | {(k + 1) * args.step for k in missing})
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    position = 0
    previous: tuple[int, BgrFrame] | None = None
    done = 0
    try:
        for index in wanted:
            while position < index:
                cap.grab()
                position += 1
            success, frame = cap.read()
            position += 1
            if not success:
                print(f"video ended at frame {index}; {len(missing) - done} pairs not computed")
                break
            pair = index // args.step - 1
            if previous is not None and previous[0] == index - args.step and pair in todo:
                cache.save(pair, estimator.estimate(previous[1], frame))
                done += 1
                if done % 50 == 0:
                    print(f"computed {done}/{len(missing)} flows")
            previous = (index, frame)
    finally:
        cap.release()


def draw_arrows(image: BgrFrame, flow: FlowField, spacing: int, scale: float) -> None:
    """Draw one arrow per `spacing`-pixel grid cell, pointing along the local mean flow."""
    dx, dy = flow.vectors
    half = spacing // 2
    thickness = max(1, image.shape[1] // 960)
    for y in range(half, flow.height - half, spacing):
        for x in range(half, flow.width - half, spacing):
            vx = float(dx[y - half : y + half, x - half : x + half].mean())
            vy = float(dy[y - half : y + half, x - half : x + half].mean())
            if abs(vx) + abs(vy) < 0.5:
                continue
            tip = (int(round(x + vx * scale)), int(round(y + vy * scale)))
            cv2.arrowedLine(image, (x, y), tip, (255, 255, 255), thickness + 1, cv2.LINE_AA, tipLength=0.3)
            cv2.arrowedLine(image, (x, y), tip, (0, 0, 0), thickness, cv2.LINE_AA, tipLength=0.3)


def compose(
    frame: BgrFrame,
    flow: FlowField,
    max_flow: float,
    alpha: float,
    arrow_spacing: int,
    arrow_scale: float,
    side_by_side: bool,
) -> BgrFrame:
    color = flow.to_bgr(max_magnitude=max_flow)
    out = cv2.addWeighted(frame, 1.0 - alpha, color, alpha, 0.0)
    if arrow_spacing > 0:
        draw_arrows(out, flow, arrow_spacing, arrow_scale)
    mean_speed = float(flow.magnitude().mean())
    cv2.putText(out, f"mean flow {mean_speed:.2f}px", (20, 50), cv2.FONT_HERSHEY_SIMPLEX,
                max(0.6, frame.shape[1] / 1600), (255, 255, 255), 2, cv2.LINE_AA)  # fmt: skip
    return np.hstack([frame, out]) if side_by_side else out  # type: ignore[no-any-return]


def sample_bilinear(vectors: npt.NDArray[np.float32], positions: Positions) -> Positions:
    """Flow at arbitrary sub-pixel positions, bilinearly interpolated from the (2, H, W) field."""
    _, height, width = vectors.shape
    x = np.clip(positions[:, 0], 0, width - 1)
    y = np.clip(positions[:, 1], 0, height - 1)
    x0 = np.minimum(x.astype(np.int64), width - 2)
    y0 = np.minimum(y.astype(np.int64), height - 2)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    hwc = np.moveaxis(vectors, 0, 2)  # view, (H, W, 2)
    top = hwc[y0, x0] * (1 - fx) + hwc[y0, x0 + 1] * fx
    bottom = hwc[y0 + 1, x0] * (1 - fx) + hwc[y0 + 1, x0 + 1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32)


class ParticleSystem:
    def __init__(self, count: int, width: int, height: int, lifetime: int, rng: np.random.Generator) -> None:
        self._size = np.array([width, height], dtype=np.float32)
        self._lifetime = lifetime
        self._rng = rng
        self.positions = self._random_positions(count)
        # Stagger ages so particles do not all respawn on the same frame.
        self._age = rng.integers(0, lifetime, count)

    def _random_positions(self, count: int) -> Positions:
        return (self._rng.random((count, 2), dtype=np.float32) * self._size).astype(np.float32)

    def advance(self, vectors: npt.NDArray[np.float32], substeps: int) -> tuple[Positions, npt.NDArray[np.bool_]]:
        """Move every particle through one frame of flow.

        Returns the positions before the move and a mask of particles that survived it
        (respawned particles should not be drawn with a trail from their old spot).
        """
        previous = self.positions.copy()
        for _ in range(substeps):
            self.positions += sample_bilinear(vectors, self.positions) / substeps
        self._age += 1
        inside = np.all((self.positions >= 0) & (self.positions < self._size), axis=1)
        alive = inside & (self._age < self._lifetime)
        dead = ~alive
        self.positions[dead] = self._random_positions(int(dead.sum()))
        self._age[dead] = 0
        return previous, alive


def direction_colors(delta: Positions) -> npt.NDArray[np.uint8]:
    """BGR color per displacement, matching FlowField.to_bgr's hue convention at full brightness."""
    hue = ((np.arctan2(delta[:, 1], delta[:, 0]) + np.pi) * (180.0 / (2 * np.pi))).astype(np.uint8)
    hsv = np.stack([hue, np.full_like(hue, 255), np.full_like(hue, 255)], axis=-1)
    return cv2.cvtColor(hsv[np.newaxis], cv2.COLOR_HSV2BGR)[0]  # type: ignore[return-value]


def draw_particles(
    canvas: npt.NDArray[np.uint8],
    start: Positions,
    end: Positions,
    scale: float,
    white: bool,
    thickness: int,
) -> None:
    colors = np.full((len(start), 3), 255, dtype=np.uint8) if white else direction_colors(end - start)
    a = np.rint(start * scale).astype(np.int32)
    b = np.rint(end * scale).astype(np.int32)
    for (x0, y0), (x1, y1), color in zip(a, b, colors):
        cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), tuple(int(c) for c in color), thickness, cv2.LINE_AA)


def particle_output_size(width: int, height: int, max_height: int) -> tuple[int, int]:
    if max_height and height > max_height:
        # Keep the aspect ratio; codecs want even dimensions.
        return round(width * max_height / height / 2) * 2, max_height // 2 * 2
    return width, height


def render(video: Path, args: argparse.Namespace) -> None:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if args.overlay_output is None:
        cap.release()  # only the overlay needs the source frames after this

    cache = FlowCache(args.cache_dir, video, args, width, height)
    total = (frame_count - 1) // args.step
    wanted = range(total if args.max_frames is None else min(total, args.max_frames))
    missing = [k for k in wanted if args.recompute or not cache.has(k)]
    print(f"{len(wanted) - len(missing)}/{len(wanted)} flows cached in {cache.directory}")
    if missing:
        compute_missing(video, missing, cache, args)
    if args.overlay_output is None and args.particles_output is None:
        print("no outputs requested; pass --overlay-output and/or --particles-output to render")
        return

    # Flow is only computed every `step` frames, so outputs play at a proportionally lower rate.
    out_fps = fps / args.step
    overlay_writer = particle_writer = None
    particles = None
    canvas = None
    try:
        if args.overlay_output is not None:
            overlay_writer = H264Writer(
                args.overlay_output, out_fps, (width * 2 if args.side_by_side else width, height)
            )
            max_flow = args.max_flow or 0.02 * width * args.step
        if args.particles_output is not None:
            particle_size = particle_output_size(width, height, args.particle_height)
            particle_scale = particle_size[0] / width  # simulate in source pixels, draw at output size
            particle_thickness = max(1, particle_size[0] // 1280)
            particles = ParticleSystem(
                args.particle_count, width, height, args.particle_lifetime, np.random.default_rng(args.particle_seed)
            )
            canvas = np.zeros((particle_size[1], particle_size[0], 3), dtype=np.uint8)
            particle_writer = H264Writer(args.particles_output, out_fps, particle_size)

        written = 0
        for k in wanted:
            if not cache.has(k):
                break  # the video ended before this pair
            flow = cache.load(k)
            if overlay_writer is not None:
                success, frame = cap.read()
                if not success:
                    raise RuntimeError(f"Video ended after {written} frames")
                for _ in range(args.step - 1):
                    cap.grab()
                overlay_writer.write(
                    compose(frame, flow, max_flow, args.alpha, args.arrow_every, args.arrow_scale, args.side_by_side)
                )
            if particle_writer is not None:
                previous, alive = particles.advance(flow.vectors, args.particle_substeps)
                canvas = (canvas * np.float32(args.particle_fade)).astype(np.uint8)
                draw_particles(
                    canvas, previous[alive], particles.positions[alive], particle_scale, args.particle_white,
                    particle_thickness,
                )
                particle_writer.write(canvas)
            written += 1
            if written % 50 == 0:
                print(f"rendered {written} frames")
    finally:
        cap.release()
        for writer in (overlay_writer, particle_writer):
            if writer is not None:
                writer.close()
    for label, path in (("overlay", args.overlay_output), ("particles", args.particles_output)):
        if path is not None:
            print(f"wrote {written} {label} frames to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path)
    add_flow_args(parser)
    parser.add_argument("--max-frames", type=int, default=None, help="only process the first M frame pairs")
    parser.add_argument("--device", default=None, help="torch device for RAFT, e.g. cuda or cpu")
    parser.add_argument("--recompute", action="store_true", help="ignore cached flow and overwrite it")

    overlay = parser.add_argument_group("overlay video")
    overlay.add_argument("--overlay-output", type=Path, default=None, help="write the flow overlay video here")
    overlay.add_argument("--side-by-side", action="store_true", help="show the original frame next to the overlay")
    overlay.add_argument("--alpha", type=float, default=0.5, help="opacity of the color-wheel layer (0-1)")
    overlay.add_argument("--max-flow", type=float, default=None,
                         help="flow (pixels) that maps to full brightness; default 2%% of width per step")  # fmt: skip
    overlay.add_argument("--arrow-every", type=int, default=48, help="arrow grid spacing in pixels; 0 disables arrows")
    overlay.add_argument("--arrow-scale", type=float, default=3.0, help="arrow length multiplier")

    particles = parser.add_argument_group("particle video")
    particles.add_argument("--particles-output", type=Path, default=None, help="write the particle video here")
    particles.add_argument("--particle-count", type=int, default=4000, help="number of particles")
    particles.add_argument("--particle-lifetime", type=int, default=90, help="frames before a particle respawns")
    particles.add_argument("--particle-fade", type=float, default=0.85,
                           help="fraction of the previous frame kept each frame; higher = longer trails (0-1)")  # fmt: skip
    particles.add_argument("--particle-substeps", type=int, default=4, help="integration steps per frame of flow")
    particles.add_argument("--particle-seed", type=int, default=0, help="random seed for particle placement")
    particles.add_argument("--particle-white", action="store_true", help="draw particles white, not colored by direction")
    particles.add_argument("--particle-height", type=int, default=720,
                           help="particle video height, keeping aspect (0 = source size)")  # fmt: skip
    args = parser.parse_args()

    validate_flow_args(parser, args)
    if not 0.0 <= args.alpha <= 1.0:
        parser.error("--alpha must be between 0 and 1")
    if args.particle_height < 0:
        parser.error("--particle-height must be >= 0")
    if args.particle_count < 1 or args.particle_lifetime < 1 or args.particle_substeps < 1:
        parser.error("--particle-count, --particle-lifetime and --particle-substeps must be >= 1")
    if not 0.0 <= args.particle_fade < 1.0:
        parser.error("--particle-fade must be in [0, 1)")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")

    render(args.video, args)


if __name__ == "__main__":
    main()
