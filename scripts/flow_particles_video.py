"""Render cached optical flow as particles drifting on a black background.

Particles are scattered over the frame and advected by the flow: each output frame, a
particle's velocity is the flow vector at its exact (sub-pixel) position, found by
bilinear interpolation between the four surrounding flow pixels. Each frame's flow is
integrated in --substeps smaller steps, re-sampling the velocity at every step so paths
curve with the field instead of jumping in a straight line. Particles that leave the
frame or reach --lifetime frames respawn at a random position, keeping coverage even.

Trails come from fading the previous frame by --fade and drawing each particle as a
line from its previous to its new position. Color is the direction of motion (same
color wheel as the overlay script).

Reads the flow cache written by optical_flow_video.py and never computes flow itself.
Pass the same flow flags (--algorithm, --step, --raft-*, --dis-preset, --cache-height,
--cache-dir) used for that run so the same cache is found. Rendering stops at the first
frame pair that is not cached; run optical_flow_video.py with a larger --max-frames
to fill it in.

Usage:
    python scripts/flow_particles_video.py VIDEO [-o OUTPUT] --algorithm raft [--raft-* ...]
        [--max-frames M] [--particles N] [--lifetime F] [--fade A] [--substeps S]
        [--white] [--output-height H]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt

from optical_flow_video import FlowCache, add_flow_args, validate_flow_args
from video_writer import H264Writer

Positions = npt.NDArray[np.float32]  # (N, 2) x, y in source-video pixels


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path, help="the source video (used to locate the cache and for fps/size)")
    parser.add_argument("-o", "--output", type=Path, default=None)
    add_flow_args(parser)
    parser.add_argument("--max-frames", type=int, default=None, help="only render the first M output frames")
    parser.add_argument("--particles", type=int, default=4000, help="number of particles")
    parser.add_argument("--lifetime", type=int, default=90, help="frames before a particle respawns elsewhere")
    parser.add_argument("--fade", type=float, default=0.85,
                        help="fraction of the previous frame kept each frame; higher = longer trails (0-1)")  # fmt: skip
    parser.add_argument("--substeps", type=int, default=4, help="integration steps per frame of flow")
    parser.add_argument("--seed", type=int, default=0, help="random seed for particle placement")
    parser.add_argument("--white", action="store_true", help="draw all particles white instead of colored by direction")
    parser.add_argument("--output-height", type=int, default=720,
                        help="output frame height, keeping aspect (0 = source size)")  # fmt: skip
    args = parser.parse_args()

    validate_flow_args(parser, args)
    if args.output_height < 0:
        parser.error("--output-height must be >= 0")
    if args.particles < 1 or args.lifetime < 1 or args.substeps < 1:
        parser.error("--particles, --lifetime and --substeps must be >= 1")
    if not 0.0 <= args.fade < 1.0:
        parser.error("--fade must be in [0, 1)")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    output = args.output or Path(f"{args.video.stem}_particles_{args.algorithm}.mp4")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        parser.error(f"failed to open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if width < 2 or height < 2:
        parser.error(f"video is too small: {width}x{height}")

    cache = FlowCache(args.cache_dir, args.video, args, width, height)
    if args.output_height and height > args.output_height:
        # Keep the aspect ratio; codecs want even dimensions.
        out_size = (round(width * args.output_height / height / 2) * 2, args.output_height // 2 * 2)
    else:
        out_size = (width, height)
    total = (frame_count - 1) // args.step
    wanted = range(total if args.max_frames is None else min(total, args.max_frames))
    if not cache.has(0):
        raise SystemExit(
            f"no cached flow in {cache.directory}\n"
            "run optical_flow_video.py on this video with the same flow flags first"
        )

    # Simulate in source pixels (the flow's units); draw directly at output size.
    scale = out_size[0] / width
    thickness = max(1, out_size[0] // 1280)
    particles = ParticleSystem(args.particles, width, height, args.lifetime, np.random.default_rng(args.seed))
    canvas = np.zeros((out_size[1], out_size[0], 3), dtype=np.uint8)

    writer = H264Writer(output, fps / args.step, out_size)
    written = 0
    try:
        for k in wanted:
            if not cache.has(k):
                print(f"flow for frame pair {k} is not cached; stopping")
                break
            previous, alive = particles.advance(cache.load(k).vectors, args.substeps)
            canvas = (canvas * np.float32(args.fade)).astype(np.uint8)
            draw_particles(canvas, previous[alive], particles.positions[alive], scale, args.white, thickness)
            writer.write(canvas)
            written += 1
            if written % 100 == 0:
                print(f"rendered {written} frames")
    finally:
        writer.close()
    print(f"wrote {written} frames to {output}")


if __name__ == "__main__":
    main()
