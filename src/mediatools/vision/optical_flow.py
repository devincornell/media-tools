from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2

from .optical_flow_domain import FlowField, OpticalFlowError, OpticalFlowEstimator


def estimate_video_flow(
    video_path: str | Path,
    estimator: OpticalFlowEstimator,
    step: int = 1,
) -> Iterator[FlowField]:
    """Lazily yield the flow between each frame and the frame `step` later.

    A video with N frames yields (N - 1) / step fields (rounded down).
    """
    if step < 1:
        raise ValueError(f"step must be at least 1, got {step}.")
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {path}")
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise OpticalFlowError(f"Could not open video: {path}")
    try:
        ok, previous = capture.read()
        while ok:
            current = previous
            for _ in range(step):
                ok, current = capture.read()
                if not ok:
                    return
            yield estimator.estimate(previous, current)  # type: ignore[arg-type]
            previous = current
    finally:
        capture.release()
