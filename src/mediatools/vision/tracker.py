from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ultralytics import YOLO

from .tracking_domain import TrackedFrame


class ObjectTracker:
    """Typed interface for multi-object tracking backed by ultralytics."""

    def __init__(
        self,
        model: str = "yolo11n.pt",
        tracker: str = "bytetrack.yaml",
        conf: float = 0.25,
    ) -> None:
        self._model = YOLO(model)
        self._tracker = tracker
        self._conf = conf

    def track_video(self, video_path: str | Path) -> Iterator[TrackedFrame]:
        """Lazily yield one `TrackedFrame` per video frame, in order."""
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Video not found: {path}")
        results = self._model.track(
            source=str(path),
            stream=True,
            persist=True,
            tracker=self._tracker,
            conf=self._conf,
            verbose=False,
        )
        for result in results:
            yield TrackedFrame.from_ultralytics_result(result)

    def track_frame(self, frame: Any) -> TrackedFrame:
        """Track a single BGR frame (numpy array); identities persist across calls."""
        result = self._model.track(
            frame,
            persist=True,
            tracker=self._tracker,
            conf=self._conf,
            verbose=False,
        )[0]
        return TrackedFrame.from_ultralytics_result(result)
