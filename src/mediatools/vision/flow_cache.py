"""Settings for dense optical flow over a video, and the on-disk cache of its results."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .optical_flow_domain import FlowField, OpticalFlowEstimator
from .optical_flow_opencv import DisFlow, FarnebackFlow
from .optical_flow_raft import RaftFlow

DEFAULT_CACHE_DIR = Path("~/.cache/mediatools/optical_flow").expanduser()

Algorithm = Literal["raft", "dis", "farneback"]
_CACHE_FORMAT = 1


@dataclasses.dataclass(frozen=True)
class FlowSettings:
    """Everything that decides which flow is computed (and so which cache is used).

    `device` only affects where RAFT runs, not its result, so it is not part of the cache key.
    """

    algorithm: Algorithm = "dis"
    step: int = 1
    cache_height: int = 360
    dis_preset: Literal["ultrafast", "fast", "medium"] = "medium"
    raft_max_height: int = 360
    raft_variant: Literal["small", "large"] = "small"
    raft_flow_updates: int | None = None
    device: str | None = None

    def __post_init__(self) -> None:
        if self.step < 1:
            raise ValueError(f"step must be at least 1, got {self.step}.")
        if self.cache_height < 0:
            raise ValueError(f"cache_height must be 0 (full resolution) or more, got {self.cache_height}.")

    def key_params(self) -> dict[str, object]:
        """The settings of the chosen algorithm that change its output."""
        if self.algorithm == "raft":
            params: dict[str, object] = {"max_height": self.raft_max_height, "variant": self.raft_variant}
            if self.raft_flow_updates is not None:
                params["num_flow_updates"] = self.raft_flow_updates
            return params
        if self.algorithm == "dis":
            return {"preset": self.dis_preset}
        return {}

    def build_estimator(self) -> OpticalFlowEstimator:
        if self.algorithm == "raft":
            return RaftFlow(
                device=self.device,
                max_height=self.raft_max_height,
                variant=self.raft_variant,
                num_flow_updates=self.raft_flow_updates,
            )
        if self.algorithm == "dis":
            return DisFlow(preset=self.dis_preset)
        return FarnebackFlow()


class FlowCache:
    """Per-frame-pair flow files for one (video, settings) combination.

    The cache folder is named after the video and a hash of its path, size, modification time and
    the flow settings, so changing any of them selects a different folder. Pair `k` is the flow
    between frames `k * step` and `(k + 1) * step`. Flow is stored downscaled to `cache_height`
    rows as float16, and rescaled to full resolution when loaded.
    """

    def __init__(self, root: Path, video: Path, settings: FlowSettings, width: int, height: int) -> None:
        stat = video.stat()
        self.key: dict[str, object] = {
            "video": str(video.resolve()),
            "video_size": stat.st_size,
            "video_mtime_ns": stat.st_mtime_ns,
            "algorithm": settings.algorithm,
            "params": settings.key_params(),
            "step": settings.step,
            "cache_height": settings.cache_height,
            "format": _CACHE_FORMAT,
        }
        digest = hashlib.sha256(json.dumps(self.key, sort_keys=True).encode()).hexdigest()[:12]
        self.directory = root / f"{video.stem}-{digest}"
        self._width, self._height = width, height
        if settings.cache_height and height > settings.cache_height:
            self._size = (max(1, round(width * settings.cache_height / height)), settings.cache_height)
        else:
            self._size = (width, height)

    def _path(self, index: int) -> Path:
        return self.directory / f"{index:07d}.npy"

    def has(self, index: int) -> bool:
        return self._path(index).is_file()

    def save(self, index: int, flow: FlowField) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        meta = self.directory / "key.json"
        if not meta.exists():
            meta.write_text(json.dumps(self.key, indent=2))
        small_w, small_h = self._size
        hwc = np.moveaxis(flow.vectors, 0, 2)
        if (small_w, small_h) != (self._width, self._height):
            hwc = cv2.resize(hwc, (small_w, small_h), interpolation=cv2.INTER_AREA)  # type: ignore[assignment]
            hwc = hwc * np.array([small_w / self._width, small_h / self._height], dtype=np.float32)
        # Write to a temporary name first so an interrupted run never leaves a truncated file.
        path = self._path(index)
        tmp = path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            np.save(f, np.moveaxis(hwc, 2, 0).astype(np.float16))
        os.replace(tmp, path)

    def load(self, index: int) -> FlowField:
        vectors = np.load(self._path(index)).astype(np.float32)
        small_w, small_h = self._size
        if (small_w, small_h) == (self._width, self._height):
            return FlowField.from_array(vectors)
        hwc = cv2.resize(np.moveaxis(vectors, 0, 2), (self._width, self._height), interpolation=cv2.INTER_LINEAR)
        hwc = hwc * np.array([self._width / small_w, self._height / small_h], dtype=np.float32)
        return FlowField.from_hwc(hwc)
