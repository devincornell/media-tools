"""Optional vision components. Requires: pip install 'mediatools[vision]'."""

try:
    import cv2  # noqa: F401
    import ultralytics  # noqa: F401
except ImportError as e:
    raise ImportError(
        "mediatools.vision requires extra dependencies: pip install 'mediatools[vision]'"
    ) from e

from .detect import Detection, detect_objects
from .tracker import ObjectTracker
from .tracking_domain import (
    BoundingBox,
    BoundingBoxDimensionError,
    ClassId,
    ClassName,
    ConfidenceScore,
    ConfidenceScoreBoundsError,
    MissingTrackingIdError,
    TrackedFrame,
    TrackedObject,
    TrackId,
    TrackingConfigurationError,
    TrackingDomainError,
)

__all__ = [
    "BoundingBox",
    "BoundingBoxDimensionError",
    "ClassId",
    "ClassName",
    "ConfidenceScore",
    "ConfidenceScoreBoundsError",
    "Detection",
    "MissingTrackingIdError",
    "ObjectTracker",
    "TrackId",
    "TrackedFrame",
    "TrackedObject",
    "TrackingConfigurationError",
    "TrackingDomainError",
    "detect_objects",
]
