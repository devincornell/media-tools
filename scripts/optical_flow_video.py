"""Estimate dense optical flow for a video and render it as an overlay for visual checking.

Each output frame is the source frame with the flow drawn on top: a color-wheel layer
(hue = direction, brightness = speed) blended in, plus a sparse grid of motion arrows.

Usage:
    python scripts/optical_flow_video.py VIDEO [-o OUTPUT] [--algorithm raft|dis|farneback]
        [--step N] [--max-frames M] [--side-by-side]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from mediatools.vision import (
    DisFlow,
    FarnebackFlow,
    FlowField,
    OpticalFlowEstimator,
    RaftFlow,
    estimate_video_flow,
)

BgrFrame = np.ndarray


def build_estimator(args: argparse.Namespace) -> OpticalFlowEstimator:
    if args.algorithm == "raft":
        return RaftFlow(device=args.device, max_height=args.raft_max_height, variant=args.raft_variant)
    if args.algorithm == "dis":
        return DisFlow(preset=args.dis_preset)
    return FarnebackFlow()


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


def render(video: Path, output: Path, estimator: OpticalFlowEstimator, args: argparse.Namespace) -> int:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_size = (width * 2 if args.side_by_side else width, height)
    # Flow is only computed every `step` frames, so the output plays at a proportionally lower rate.
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps / args.step, out_size)
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open writer for: {output}")

    max_flow = args.max_flow or 0.02 * width * args.step
    written = 0
    try:
        for flow in estimate_video_flow(video, estimator, step=args.step):
            if args.max_frames is not None and written >= args.max_frames:
                break
            # estimate_video_flow reads frames 0, step, 2*step, ...; the flow pairs with the first of each pair.
            success, frame = cap.read()
            if not success:
                raise RuntimeError(f"Video ended after {written} frames")
            for _ in range(args.step - 1):
                cap.read()
            writer.write(compose(frame, flow, max_flow, args.alpha, args.arrow_every, args.arrow_scale, args.side_by_side))
            written += 1
            if written % 50 == 0:
                print(f"rendered {written} frames")
    finally:
        cap.release()
        writer.release()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--algorithm", choices=["raft", "dis", "farneback"], default="dis",
                        help="flow estimator; raft is the most accurate, dis the fastest on CPU")  # fmt: skip
    parser.add_argument("--step", type=int, default=1, help="estimate flow between frames N apart")
    parser.add_argument("--max-frames", type=int, default=None, help="only render the first M output frames")
    parser.add_argument("--side-by-side", action="store_true", help="show the original frame next to the overlay")
    parser.add_argument("--alpha", type=float, default=0.5, help="opacity of the color-wheel layer (0-1)")
    parser.add_argument("--max-flow", type=float, default=None,
                        help="flow (pixels) that maps to full brightness; default 2%% of width per step")  # fmt: skip
    parser.add_argument("--arrow-every", type=int, default=48, help="arrow grid spacing in pixels; 0 disables arrows")
    parser.add_argument("--arrow-scale", type=float, default=3.0, help="arrow length multiplier")
    parser.add_argument("--dis-preset", choices=["ultrafast", "fast", "medium"], default="medium")
    parser.add_argument("--raft-max-height", type=int, default=360, help="downscale frames to this height for RAFT")
    parser.add_argument("--raft-variant", choices=["small", "large"], default="small")
    parser.add_argument("--device", default=None, help="torch device for RAFT, e.g. cuda or cpu")
    args = parser.parse_args()

    if args.step < 1:
        parser.error("--step must be >= 1")
    if not 0.0 <= args.alpha <= 1.0:
        parser.error("--alpha must be between 0 and 1")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    output = args.output or Path(f"{args.video.stem}_flow_{args.algorithm}.mp4")

    written = render(args.video, output, build_estimator(args), args)
    print(f"wrote {written} frames to {output}")


if __name__ == "__main__":
    main()
