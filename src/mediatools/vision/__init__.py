"""Optional vision components. Requires: pip install 'mediatools[vision]'."""

try:
    import cv2  # noqa: F401
    import ultralytics  # noqa: F401
except ImportError as e:
    raise ImportError(
        "mediatools.vision requires extra dependencies: pip install 'mediatools[vision]'"
    ) from e

from .detect import Detection, detect_objects

__all__ = ["Detection", "detect_objects"]
