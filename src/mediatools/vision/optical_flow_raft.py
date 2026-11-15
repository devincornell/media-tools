from __future__ import annotations

from typing import Literal

try:
    import torch
    import torch.nn.functional as F
    from torchvision.models.optical_flow import (  # type: ignore[import-untyped]
        Raft_Large_Weights,
        Raft_Small_Weights,
        raft_large,
        raft_small,
    )
except ImportError as e:
    raise ImportError(
        "RaftFlow requires torch and torchvision: pip install 'mediatools[vision]'"
    ) from e

from .optical_flow_domain import (
    BgrFrame,
    DeviceMemoryError,
    DeviceUnavailableError,
    FlowField,
    validate_frame_pair,
)

_DIVISOR = 8  # RAFT's feature encoder downsamples by 8, so spatial sizes must be multiples of it.


def working_size(height: int, width: int, max_height: int) -> tuple[int, int]:
    """Size RAFT runs at: no taller than `max_height` (when possible), multiples of 8."""
    scale = min(1.0, max_height / height)

    def snap(size: int) -> int:
        return max(_DIVISOR, round(size * scale / _DIVISOR) * _DIVISOR)

    return snap(height), snap(width)


class RaftFlow:
    """Deep-learning dense optical flow using torchvision's RAFT, tuned for small GPUs.

    RAFT builds an all-pairs correlation volume, so memory grows with the square of the
    pixel count, not with the (tiny) model weights. To stay within a few GB of VRAM the
    frames are downscaled to at most `max_height` rows, inference runs in fp16 on CUDA,
    and the predicted flow is upscaled back to the input resolution with its vectors
    rescaled to match (separately per axis, since snapping to multiples of 8 changes the
    aspect ratio slightly).

    Pretrained weights are downloaded by torchvision on first use.
    """

    def __init__(
        self,
        device: str | None = None,
        max_height: int = 360,
        variant: Literal["small", "large"] = "small",
        num_flow_updates: int | None = None,
        model: torch.nn.Module | None = None,
    ) -> None:
        """
        Args:
            device: torch device string; defaults to "cuda" when available, else "cpu".
            max_height: frames taller than this are downscaled before inference.
            variant: "small" (under 25MB) or "large" (more accurate, more memory).
            num_flow_updates: recurrent refinement iterations; model default if None.
            model: a preloaded RAFT-compatible module (skips downloading weights).
        """
        if max_height < _DIVISOR:
            raise ValueError(
                f"max_height must be at least {_DIVISOR}, got {max_height}."
            )
        if num_flow_updates is not None and num_flow_updates < 1:
            raise ValueError(
                f"num_flow_updates must be positive, got {num_flow_updates}."
            )
        resolved = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._device = torch.device(resolved)
        if self._device.type == "cuda" and not torch.cuda.is_available():
            raise DeviceUnavailableError(
                "CUDA device requested but torch cannot see a GPU."
            )
        self._max_height = max_height
        self._num_flow_updates = num_flow_updates

        if model is None:
            if variant == "small":
                model = raft_small(weights=Raft_Small_Weights.DEFAULT, progress=False)
            elif variant == "large":
                model = raft_large(weights=Raft_Large_Weights.DEFAULT, progress=False)
            else:
                raise ValueError(
                    f"Unknown RAFT variant {variant!r}; use 'small' or 'large'."
                )
        self._model = model.to(self._device).eval()

    def estimate(self, frame1: BgrFrame, frame2: BgrFrame) -> FlowField:
        validate_frame_pair(frame1, frame2)
        height, width = frame1.shape[:2]
        new_h, new_w = working_size(height, width, self._max_height)

        try:
            with torch.inference_mode():
                batch1 = self._preprocess(frame1, (new_h, new_w))
                batch2 = self._preprocess(frame2, (new_h, new_w))
                kwargs = {}
                if self._num_flow_updates is not None:
                    kwargs["num_flow_updates"] = self._num_flow_updates
                with torch.autocast(
                    device_type=self._device.type,
                    dtype=torch.float16,
                    enabled=self._device.type == "cuda",
                ):
                    flow = self._model(batch1, batch2, **kwargs)[
                        -1
                    ]  # last GRU iteration
                flow = flow.float()
                if (new_h, new_w) != (height, width):
                    flow = F.interpolate(
                        flow, size=(height, width), mode="bilinear", align_corners=False
                    )
                    flow[:, 0] *= width / new_w
                    flow[:, 1] *= height / new_h
                result = flow[0].cpu().numpy()
        except torch.cuda.OutOfMemoryError as e:
            torch.cuda.empty_cache()
            raise DeviceMemoryError(
                f"GPU ran out of memory at {new_w}x{new_h}; lower max_height."
            ) from e
        return FlowField.from_array(result)

    def _preprocess(self, frame: BgrFrame, size: tuple[int, int]) -> torch.Tensor:
        """BGR uint8 (H, W, 3) -> RGB float (1, 3, h, w) in [-1, 1], resized to `size`."""
        tensor = torch.from_numpy(frame[..., ::-1].copy()).to(self._device)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0).float() / 255.0
        if tensor.shape[-2:] != size:
            tensor = F.interpolate(
                tensor, size=size, mode="bilinear", align_corners=False, antialias=True
            )
        return tensor * 2.0 - 1.0
