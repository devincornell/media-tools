from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, NewType, Self

from pydantic import Field


class TrackingDomainError(Exception):
    """Base exception for all tracking domain errors."""


class MissingTrackingIdError(TrackingDomainError):
    """Tracking IDs are expected but missing from the detector payload."""


class TrackingConfigurationError(TrackingDomainError):
    """The model's class mapping is inconsistent with its output."""


class BoundingBoxDimensionError(TrackingDomainError):
    """A bounding box does not have exactly four coordinates."""


class ConfidenceScoreBoundsError(TrackingDomainError):
    """A confidence score falls outside [0.0, 1.0]."""


TrackId = NewType("TrackId", int)
ClassId = NewType("ClassId", int)
ClassName = NewType("ClassName", str)
ConfidenceScore = Annotated[
    float,
    Field(description="Detection probability score bounded between 0.0 and 1.0."),
]


@dataclass(slots=True, frozen=True)
class BoundingBox:
    """A 2D bounding box in pixel coordinates."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @classmethod
    def from_xyxy(cls, coords: list[float] | tuple[float, ...]) -> Self:
        if len(coords) != 4:
            raise BoundingBoxDimensionError(
                f"Expected exactly 4 coordinates for a bounding box, got {len(coords)}."
            )
        return cls(
            x_min=float(coords[0]),
            y_min=float(coords[1]),
            x_max=float(coords[2]),
            y_max=float(coords[3]),
        )


@dataclass(slots=True, frozen=True)
class TrackedObject:
    """A single detected and tracked object in one frame."""

    track_id: TrackId
    class_id: ClassId
    class_name: ClassName
    confidence: ConfidenceScore
    bounding_box: BoundingBox

    @classmethod
    def from_raw_data(
        cls,
        track_id: int,
        class_id: int,
        class_name: str,
        confidence: float,
        bbox_coords: list[float],
    ) -> Self:
        if not 0.0 <= confidence <= 1.0:
            raise ConfidenceScoreBoundsError(
                f"Confidence score {confidence} is out of bounds [0.0, 1.0]."
            )
        return cls(
            track_id=TrackId(track_id),
            class_id=ClassId(class_id),
            class_name=ClassName(class_name),
            confidence=confidence,
            bounding_box=BoundingBox.from_xyxy(bbox_coords),
        )


class TrackedFrame(tuple[TrackedObject, ...]):
    """Immutable collection of the objects tracked in a single frame."""

    @classmethod
    def from_ultralytics_result(cls, result: Any) -> Self:
        """Anti-corruption layer: convert an ultralytics `Results` into domain types."""
        if result.boxes is None or len(result.boxes) == 0:
            return cls()

        if result.boxes.id is None:
            raise MissingTrackingIdError(
                "Tracking IDs missing from detection results. "
                "Use a tracking call (persist=True with a tracker config), not plain detection."
            )

        boxes = result.boxes.xyxy.cpu().tolist()
        track_ids = result.boxes.id.cpu().tolist()
        confs = result.boxes.conf.cpu().tolist()
        class_ids = result.boxes.cls.cpu().tolist()
        names = result.names

        objects: list[TrackedObject] = []
        for box, t_id, conf, c_id in zip(boxes, track_ids, confs, class_ids):
            try:
                class_name = names[int(c_id)]
            except KeyError as e:
                raise TrackingConfigurationError(
                    f"Class ID {int(c_id)} missing from model class mapping."
                ) from e
            objects.append(
                TrackedObject.from_raw_data(
                    track_id=int(t_id),
                    class_id=int(c_id),
                    class_name=class_name,
                    confidence=float(conf),
                    bbox_coords=box,
                )
            )
        return cls(objects)
