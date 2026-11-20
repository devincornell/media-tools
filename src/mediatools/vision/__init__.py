"""Optional vision components. Requires: pip install 'mediatools[vision]'."""

try:
    import cv2  # noqa: F401
    import ultralytics  # noqa: F401
except ImportError as e:
    raise ImportError(
        "mediatools.vision requires extra dependencies: pip install 'mediatools[vision]'"
    ) from e

from .detect import Detection, detect_objects
from .flow_cache import DEFAULT_CACHE_DIR, FlowCache, FlowSettings
from .flow_video import FlowVideo, OverlayOptions, ParticleOptions
from .optical_flow import estimate_video_flow
from .optical_flow_domain import (
    DeviceMemoryError,
    DeviceUnavailableError,
    FlowField,
    FlowShapeError,
    FrameValidationError,
    OpticalFlowError,
    OpticalFlowEstimator,
)
from .optical_flow_opencv import DisFlow, FarnebackFlow
from .optical_flow_raft import RaftFlow
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
    "DEFAULT_CACHE_DIR",
    "BoundingBox",
    "BoundingBoxDimensionError",
    "ClassId",
    "ClassName",
    "ConfidenceScore",
    "ConfidenceScoreBoundsError",
    "Detection",
    "DeviceMemoryError",
    "DeviceUnavailableError",
    "DisFlow",
    "FarnebackFlow",
    "FlowCache",
    "FlowField",
    "FlowSettings",
    "FlowShapeError",
    "FlowVideo",
    "FrameValidationError",
    "MissingTrackingIdError",
    "ObjectTracker",
    "OpticalFlowError",
    "OpticalFlowEstimator",
    "OverlayOptions",
    "ParticleOptions",
    "RaftFlow",
    "TrackId",
    "TrackedFrame",
    "TrackedObject",
    "TrackingConfigurationError",
    "TrackingDomainError",
    "detect_objects",
    "estimate_video_flow",
]
