from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]


def detect_objects(
    image_path: str | Path,
    model: str = "yolov8n.pt",
    conf: float = 0.25,
) -> list[Detection]:
    """Run YOLO object detection on a single image."""
    result = YOLO(model)(str(image_path), conf=conf, verbose=False)[0]
    return [
        Detection(
            label=result.names[int(b.cls)],
            confidence=float(b.conf),
            box_xyxy=tuple(float(v) for v in b.xyxy[0].tolist()),  # type: ignore[arg-type]
        )
        for b in result.boxes
    ]
