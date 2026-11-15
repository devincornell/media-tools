from __future__ import annotations

from typing import ClassVar

import cv2

from .optical_flow_domain import BgrFrame, FlowField, validate_frame_pair


class FarnebackFlow:
    """Classical dense optical flow (Farneback polynomial expansion) from OpenCV."""

    def __init__(
        self,
        pyr_scale: float = 0.5,
        levels: int = 3,
        winsize: int = 15,
        iterations: int = 3,
        poly_n: int = 5,
        poly_sigma: float = 1.2,
    ) -> None:
        self._params = {
            "pyr_scale": pyr_scale,
            "levels": levels,
            "winsize": winsize,
            "iterations": iterations,
            "poly_n": poly_n,
            "poly_sigma": poly_sigma,
        }

    def estimate(self, frame1: BgrFrame, frame2: BgrFrame) -> FlowField:
        validate_frame_pair(frame1, frame2)
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        p = self._params
        flow = cv2.calcOpticalFlowFarneback(  # type: ignore[call-overload]
            gray1, gray2, None,
            p["pyr_scale"], p["levels"], p["winsize"], p["iterations"], p["poly_n"], p["poly_sigma"],
            0,
        )  # fmt: skip
        return FlowField.from_hwc(flow)


class DisFlow:
    """Dense Inverse Search (DIS) optical flow from OpenCV: much faster than Farneback."""

    _PRESETS: ClassVar[dict[str, int]] = {
        "ultrafast": cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST,
        "fast": cv2.DISOPTICAL_FLOW_PRESET_FAST,
        "medium": cv2.DISOPTICAL_FLOW_PRESET_MEDIUM,
    }

    def __init__(self, preset: str = "medium") -> None:
        if preset not in self._PRESETS:
            raise ValueError(
                f"Unknown DIS preset {preset!r}; choose from {sorted(self._PRESETS)}."
            )
        self._dis = cv2.DISOpticalFlow_create(  # type: ignore[attr-defined]
            self._PRESETS[preset]
        )

    def estimate(self, frame1: BgrFrame, frame2: BgrFrame) -> FlowField:
        validate_frame_pair(frame1, frame2)
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        return FlowField.from_hwc(self._dis.calc(gray1, gray2, None))
