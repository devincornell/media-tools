"""Render cached optical flow as arrows on a black background.

Reads the flow cache written by optical_flow_video.py and never computes flow itself.
Pass the same flow flags (--algorithm, --step, --raft-*, --dis-preset, --cache-height,
--cache-dir) used for that run so the same cache is found. Rendering stops at the first
frame pair that is not cached; run optical_flow_video.py with a larger --max-frames
to fill it in.

Arrow color is the flow direction (same color wheel as the overlay script) and arrow
length is the local mean displacement times --arrow-scale.

Usage:
    python scripts/flow_arrows_video.py VIDEO [-o OUTPUT] --algorithm raft [--raft-* ...]
        [--max-frames M] [--arrow-every PX] [--arrow-scale S] [--min-flow PX] [--white]
        [--output-height H]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from mediatools.vision import FlowField
from optical_flow_video import FlowCache, add_flow_args, validate_flow_args
from video_writer import H264Writer

BgrFrame = np.ndarray


def direction_colors(vx: np.ndarray, vy: np.ndarray) -> np.ndarray:
    """BGR color per vector, matching FlowField.to_bgr's hue convention at full brightness."""
    hue = ((np.arctan2(vy, vx) + np.pi) * (180.0 / (2 * np.pi))).astype(np.uint8)
    hsv = np.stack([hue, np.full_like(hue, 255), np.full_like(hue, 255)], axis=-1)
    return cv2.cvtColor(hsv[np.newaxis], cv2.COLOR_HSV2BGR)[0]


def draw_frame(
    flow: FlowField,
    spacing: int,
    scale: float,
    min_flow: float,
    white: bool,
    thickness: int,
) -> BgrFrame:
    image = np.zeros((flow.height, flow.width, 3), dtype=np.uint8)
    rows, cols = flow.height // spacing, flow.width // spacing
    if rows == 0 or cols == 0:
        return image
    # Area-resizing the cropped field to the grid gives the mean flow of each cell.
    hwc = np.moveaxis(flow.vectors[:, : rows * spacing, : cols * spacing], 0, 2)
    cells = cv2.resize(hwc, (cols, rows), interpolation=cv2.INTER_AREA)
    vx, vy = cells[..., 0].ravel(), cells[..., 1].ravel()
    ys, xs = np.mgrid[0:rows, 0:cols]
    cx = (xs.ravel() * spacing + spacing // 2).astype(np.float32)
    cy = (ys.ravel() * spacing + spacing // 2).astype(np.float32)

    keep = np.hypot(vx, vy) >= min_flow
    vx, vy, cx, cy = vx[keep], vy[keep], cx[keep], cy[keep]
    colors = np.full((len(vx), 3), 255, dtype=np.uint8) if white else direction_colors(vx, vy)
    for x, y, dx, dy, color in zip(cx, cy, vx, vy, colors):
        start = (int(x), int(y))
        tip = (int(round(x + dx * scale)), int(round(y + dy * scale)))
        cv2.arrowedLine(image, start, tip, tuple(int(c) for c in color), thickness, cv2.LINE_AA, tipLength=0.3)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path, help="the source video (used to locate the cache and for fps/size)")
    parser.add_argument("-o", "--output", type=Path, default=None)
    add_flow_args(parser)
    parser.add_argument("--max-frames", type=int, default=None, help="only render the first M output frames")
    parser.add_argument("--arrow-every", type=int, default=24, help="arrow grid spacing in pixels")
    parser.add_argument("--arrow-scale", type=float, default=3.0, help="arrow length multiplier")
    parser.add_argument("--min-flow", type=float, default=0.5, help="hide arrows shorter than this many pixels of flow")
    parser.add_argument("--white", action="store_true", help="draw all arrows white instead of colored by direction")
    parser.add_argument("--output-height", type=int, default=720,
                        help="downscale the finished frames to this height, keeping aspect (0 = source size)")  # fmt: skip
    args = parser.parse_args()

    validate_flow_args(parser, args)
    if args.output_height < 0:
        parser.error("--output-height must be >= 0")
    if args.arrow_every < 2:
        parser.error("--arrow-every must be >= 2")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    output = args.output or Path(f"{args.video.stem}_arrows_{args.algorithm}.mp4")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        parser.error(f"failed to open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

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

    writer = H264Writer(output, fps / args.step, out_size)
    thickness = max(1, width // 960)
    written = 0
    try:
        for k in wanted:
            if not cache.has(k):
                print(f"flow for frame pair {k} is not cached; stopping")
                break
            image = draw_frame(cache.load(k), args.arrow_every, args.arrow_scale, args.min_flow, args.white, thickness)
            if out_size != (width, height):
                image = cv2.resize(image, out_size, interpolation=cv2.INTER_AREA)
            writer.write(image)
            written += 1
            if written % 100 == 0:
                print(f"rendered {written} frames")
    finally:
        writer.close()
    print(f"wrote {written} frames to {output}")


if __name__ == "__main__":
    main()
