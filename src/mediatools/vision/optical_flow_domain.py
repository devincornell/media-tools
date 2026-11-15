from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Self, runtime_checkable

import cv2
import numpy as np
import numpy.typing as npt

BgrFrame = npt.NDArray[np.uint8]


class OpticalFlowError(Exception):
    """Base exception for all optical flow errors."""


class FrameValidationError(OpticalFlowError):
    """An input frame is not a valid BGR uint8 image, or the pair does not match."""


class FlowShapeError(OpticalFlowError):
    """A flow array does not have shape (2, H, W)."""


class DeviceMemoryError(OpticalFlowError):
    """The accelerator ran out of memory while estimating flow."""


class DeviceUnavailableError(OpticalFlowError):
    """The requested compute device is not available."""


def validate_frame_pair(frame1: BgrFrame, frame2: BgrFrame) -> None:
    """Fail fast unless both frames are HxWx3 uint8 arrays of identical shape."""
    for name, frame in (("frame1", frame1), ("frame2", frame2)):
        if not isinstance(frame, np.ndarray):
            raise FrameValidationError(
                f"{name} must be a numpy array, got {type(frame).__name__}."
            )
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise FrameValidationError(
                f"{name} must have shape (H, W, 3), got {frame.shape}."
            )
        if frame.dtype != np.uint8:
            raise FrameValidationError(
                f"{name} must have dtype uint8, got {frame.dtype}."
            )
        if frame.shape[0] < 1 or frame.shape[1] < 1:
            raise FrameValidationError(f"{name} is empty: {frame.shape}.")
    if frame1.shape != frame2.shape:
        raise FrameValidationError(
            f"Frames must have identical shapes, got {frame1.shape} and {frame2.shape}."
        )


@dataclass(slots=True, frozen=True)
class FlowField:
    """A dense optical flow field in pixels, mapping frame 1 onto frame 2.

    `vectors` has shape (2, H, W) and dtype float32; channel 0 is the x (horizontal)
    displacement and channel 1 the y (vertical) displacement. The array is read-only.
    """

    vectors: npt.NDArray[np.float32]

    @classmethod
    def from_array(cls, vectors: npt.NDArray[np.floating]) -> Self:
        if vectors.ndim != 3 or vectors.shape[0] != 2:
            raise FlowShapeError(
                f"Flow array must have shape (2, H, W), got {vectors.shape}."
            )
        owned = np.array(vectors, dtype=np.float32, copy=True)
        owned.setflags(write=False)
        return cls(vectors=owned)

    @classmethod
    def from_hwc(cls, vectors: npt.NDArray[np.floating]) -> Self:
        """Build from OpenCV's (H, W, 2) layout."""
        if vectors.ndim != 3 or vectors.shape[2] != 2:
            raise FlowShapeError(
                f"Flow array must have shape (H, W, 2), got {vectors.shape}."
            )
        return cls.from_array(np.moveaxis(vectors, 2, 0))

    @property
    def height(self) -> int:
        return int(self.vectors.shape[1])

    @property
    def width(self) -> int:
        return int(self.vectors.shape[2])

    def magnitude(self) -> npt.NDArray[np.float32]:
        """Per-pixel displacement length in pixels, shape (H, W)."""
        return np.hypot(self.vectors[0], self.vectors[1]).astype(np.float32)

    def to_bgr(self, max_magnitude: float | None = None) -> BgrFrame:
        """Render with the standard HSV color wheel: hue is direction, value is speed.

        Pass `max_magnitude` to keep colors comparable across frames; by default each
        field is normalized by its own maximum.
        """
        mag = self.magnitude()
        angle = np.arctan2(self.vectors[1], self.vectors[0])
        scale = float(mag.max()) if max_magnitude is None else max_magnitude
        hsv = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        hsv[..., 0] = ((angle + np.pi) * (180.0 / (2 * np.pi))).astype(np.uint8)
        hsv[..., 1] = 255
        if scale > 0:
            hsv[..., 2] = np.clip(mag / scale * 255.0, 0, 255).astype(np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)  # type: ignore[no-any-return,return-value]


@runtime_checkable
class OpticalFlowEstimator(Protocol):
    """Strategy interface: any algorithm that estimates dense flow between two frames."""

    def estimate(self, frame1: BgrFrame, frame2: BgrFrame) -> FlowField:
        """Estimate flow from `frame1` to `frame2` (BGR uint8, identical shapes)."""
        ...
