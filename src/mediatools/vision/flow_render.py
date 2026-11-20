"""Drawing optical flow: a color/arrow overlay on the source frame, and drifting particles."""
from __future__ import annotations

import cv2
import numpy as np
import numpy.typing as npt

from .optical_flow_domain import BgrFrame, FlowField

Positions = npt.NDArray[np.float32]  # (N, 2) x, y in source-video pixels


def draw_arrows(image: BgrFrame, flow: FlowField, spacing: int, scale: float) -> None:
    """Draw one arrow per `spacing`-pixel grid cell, pointing along the local mean flow."""
    dx, dy = flow.vectors
    half = spacing // 2
    thickness = max(1, image.shape[1] // 960)
    for y in range(half, flow.height - half, spacing):
        for x in range(half, flow.width - half, spacing):
            vx = float(dx[y - half : y + half, x - half : x + half].mean())
            vy = float(dy[y - half : y + half, x - half : x + half].mean())
            if abs(vx) + abs(vy) < 0.5:
                continue
            tip = (round(x + vx * scale), round(y + vy * scale))
            cv2.arrowedLine(image, (x, y), tip, (255, 255, 255), thickness + 1, cv2.LINE_AA, tipLength=0.3)
            cv2.arrowedLine(image, (x, y), tip, (0, 0, 0), thickness, cv2.LINE_AA, tipLength=0.3)


def compose_overlay(
    frame: BgrFrame,
    flow: FlowField,
    max_flow: float,
    alpha: float,
    arrow_spacing: int,
    arrow_scale: float,
    side_by_side: bool,
) -> BgrFrame:
    """The source frame with the flow's color wheel blended in and a grid of motion arrows on top."""
    color = flow.to_bgr(max_magnitude=max_flow)
    out = cv2.addWeighted(frame, 1.0 - alpha, color, alpha, 0.0)
    if arrow_spacing > 0:
        draw_arrows(out, flow, arrow_spacing, arrow_scale)  # type: ignore[arg-type]
    mean_speed = float(flow.magnitude().mean())
    cv2.putText(out, f"mean flow {mean_speed:.2f}px", (20, 50), cv2.FONT_HERSHEY_SIMPLEX,
                max(0.6, frame.shape[1] / 1600), (255, 255, 255), 2, cv2.LINE_AA)  # fmt: skip
    return np.hstack([frame, out]) if side_by_side else out  # type: ignore[no-any-return,return-value]


def sample_bilinear(vectors: npt.NDArray[np.float32], positions: Positions) -> Positions:
    """Flow at arbitrary sub-pixel positions, bilinearly interpolated from the (2, H, W) field."""
    _, height, width = vectors.shape
    x = np.clip(positions[:, 0], 0, width - 1)
    y = np.clip(positions[:, 1], 0, height - 1)
    x0 = np.minimum(x.astype(np.int64), width - 2)
    y0 = np.minimum(y.astype(np.int64), height - 2)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    hwc = np.moveaxis(vectors, 0, 2)  # view, (H, W, 2)
    top = hwc[y0, x0] * (1 - fx) + hwc[y0, x0 + 1] * fx
    bottom = hwc[y0 + 1, x0] * (1 - fx) + hwc[y0 + 1, x0 + 1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32)


class ParticleSystem:
    """Particles scattered over the frame that drift with the flow, respawning when they leave or age out."""

    def __init__(self, count: int, width: int, height: int, lifetime: int, rng: np.random.Generator) -> None:
        self._size = np.array([width, height], dtype=np.float32)
        self._lifetime = lifetime
        self._rng = rng
        self.positions = self._random_positions(count)
        # Stagger ages so particles do not all respawn on the same frame.
        self._age = rng.integers(0, lifetime, count)

    def _random_positions(self, count: int) -> Positions:
        return (self._rng.random((count, 2), dtype=np.float32) * self._size).astype(np.float32)

    def advance(self, vectors: npt.NDArray[np.float32], substeps: int) -> tuple[Positions, npt.NDArray[np.bool_]]:
        """Move every particle through one frame of flow.

        Returns the positions before the move and a mask of particles that survived it
        (respawned particles should not be drawn with a trail from their old spot).
        """
        previous = self.positions.copy()
        for _ in range(substeps):
            self.positions += sample_bilinear(vectors, self.positions) / substeps
        self._age += 1
        inside = np.all((self.positions >= 0) & (self.positions < self._size), axis=1)
        alive = inside & (self._age < self._lifetime)
        dead = ~alive
        self.positions[dead] = self._random_positions(int(dead.sum()))
        self._age[dead] = 0
        return previous, alive


def direction_colors(delta: Positions) -> npt.NDArray[np.uint8]:
    """BGR color per displacement, matching FlowField.to_bgr's hue convention at full brightness."""
    hue = ((np.arctan2(delta[:, 1], delta[:, 0]) + np.pi) * (180.0 / (2 * np.pi))).astype(np.uint8)
    hsv = np.stack([hue, np.full_like(hue, 255), np.full_like(hue, 255)], axis=-1)
    return cv2.cvtColor(hsv[np.newaxis], cv2.COLOR_HSV2BGR)[0]  # type: ignore[no-any-return]


def draw_particles(
    canvas: npt.NDArray[np.uint8],
    start: Positions,
    end: Positions,
    scale: float,
    white: bool,
    thickness: int,
) -> None:
    """Draw each particle as a line from where it was to where it is, scaled to the canvas."""
    colors = np.full((len(start), 3), 255, dtype=np.uint8) if white else direction_colors(end - start)
    a = np.rint(start * scale).astype(np.int32)
    b = np.rint(end * scale).astype(np.int32)
    for (x0, y0), (x1, y1), color in zip(a, b, colors):
        cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), tuple(int(c) for c in color), thickness, cv2.LINE_AA)


def particle_output_size(width: int, height: int, max_height: int) -> tuple[int, int]:
    """Output size for the particle video: capped at `max_height` rows (0 = source size), even dimensions."""
    if max_height and height > max_height:
        return round(width * max_height / height / 2) * 2, max_height // 2 * 2
    return width, height
