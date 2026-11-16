"""Estimate dense optical flow for a video and render it as an overlay for visual checking.

Each output frame is the source frame with the flow drawn on top: a color-wheel layer
(hue = direction, brightness = speed) blended in, plus a sparse grid of motion arrows.

Computed flow is cached on disk, one file per frame pair, keyed by the video (path, size,
modification time), the algorithm and its parameters, `--step`, and `--cache-height`. Any
run, whatever its `--max-frames`, only computes the frame pairs that are not cached yet, so
extending 500 frames to 1000 computes just the new 500 and shrinking back to 500 computes
nothing. Flow is stored downscaled to `--cache-height` rows (float16) to keep the cache
small, and upscaled when rendering; both fresh and cached runs go through that same
round trip, so their output is identical.

Usage:
    python scripts/optical_flow_video.py VIDEO [-o OUTPUT] [--algorithm raft|dis|farneback]
        [--step N] [--max-frames M] [--side-by-side] [--cache-dir DIR] [--recompute]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np

from mediatools.vision import (
    DisFlow,
    FarnebackFlow,
    FlowField,
    OpticalFlowEstimator,
    RaftFlow,
)
from video_writer import H264Writer

BgrFrame = np.ndarray

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


def render(video: Path, output: Path, args: argparse.Namespace) -> int:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    cache = FlowCache(args.cache_dir, video, args, width, height)
    total = (frame_count - 1) // args.step
    wanted = range(total if args.max_frames is None else min(total, args.max_frames))
    missing = [k for k in wanted if args.recompute or not cache.has(k)]
    print(f"{len(wanted) - len(missing)}/{len(wanted)} flows cached in {cache.directory}")
    if missing:
        compute_missing(video, missing, cache, args)

    out_size = (width * 2 if args.side_by_side else width, height)
    # Flow is only computed every `step` frames, so the output plays at a proportionally lower rate.
    writer = H264Writer(output, fps / args.step, out_size)

    max_flow = args.max_flow or 0.02 * width * args.step
    written = 0
    try:
        for k in wanted:
            if not cache.has(k):
                break  # the video ended before this pair
            success, frame = cap.read()
            if not success:
                raise RuntimeError(f"Video ended after {written} frames")
            for _ in range(args.step - 1):
                cap.grab()
            flow = cache.load(k)
            writer.write(compose(frame, flow, max_flow, args.alpha, args.arrow_every, args.arrow_scale, args.side_by_side))
            written += 1
            if written % 50 == 0:
                print(f"rendered {written} frames")
    finally:
        cap.release()
        writer.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    add_flow_args(parser)
    parser.add_argument("--max-frames", type=int, default=None, help="only render the first M output frames")
    parser.add_argument("--side-by-side", action="store_true", help="show the original frame next to the overlay")
    parser.add_argument("--alpha", type=float, default=0.5, help="opacity of the color-wheel layer (0-1)")
    parser.add_argument("--max-flow", type=float, default=None,
                        help="flow (pixels) that maps to full brightness; default 2%% of width per step")  # fmt: skip
    parser.add_argument("--arrow-every", type=int, default=48, help="arrow grid spacing in pixels; 0 disables arrows")
    parser.add_argument("--arrow-scale", type=float, default=3.0, help="arrow length multiplier")
    parser.add_argument("--device", default=None, help="torch device for RAFT, e.g. cuda or cpu")
    parser.add_argument("--recompute", action="store_true", help="ignore cached flow and overwrite it")
    args = parser.parse_args()

    validate_flow_args(parser, args)
    if not 0.0 <= args.alpha <= 1.0:
        parser.error("--alpha must be between 0 and 1")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    output = args.output or Path(f"{args.video.stem}_flow_{args.algorithm}.mp4")

    written = render(args.video, output, args)
    print(f"wrote {written} frames to {output}")


if __name__ == "__main__":
    main()
