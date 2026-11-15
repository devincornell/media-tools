"""Tests for mediatools.vision optical flow."""

import cv2
import numpy as np
import pytest
import torch

from mediatools.vision import (
    DisFlow,
    FarnebackFlow,
    FlowField,
    FlowShapeError,
    FrameValidationError,
    OpticalFlowEstimator,
    RaftFlow,
    estimate_video_flow,
)
from mediatools.vision.optical_flow_raft import working_size

SHIFT_X = 6


@pytest.fixture(scope="module")
def shifted_pair():
    """Textured frames where scene content moves SHIFT_X pixels left (flow x = -SHIFT_X)."""
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (240, 360, 3), dtype=np.uint8)
    base = cv2.normalize(
        cv2.GaussianBlur(noise, (0, 0), 3), None, 0, 255, cv2.NORM_MINMAX
    )
    return base[:, :320].copy(), base[:, SHIFT_X : 320 + SHIFT_X].copy()


class TestFlowField:
    def test_from_array_is_read_only_copy(self):
        source = np.zeros((2, 4, 5), dtype=np.float64)
        field = FlowField.from_array(source)
        source[:] = 1
        assert field.vectors.dtype == np.float32
        assert not field.vectors.any()
        with pytest.raises(ValueError):
            field.vectors[0, 0, 0] = 1

    def test_rejects_bad_shapes(self):
        with pytest.raises(FlowShapeError):
            FlowField.from_array(np.zeros((3, 4, 5)))
        with pytest.raises(FlowShapeError):
            FlowField.from_hwc(np.zeros((4, 5, 3)))

    def test_from_hwc_puts_x_first(self):
        hwc = np.zeros((4, 5, 2), dtype=np.float32)
        hwc[..., 0] = 3
        field = FlowField.from_hwc(hwc)
        assert (field.height, field.width) == (4, 5)
        assert (field.vectors[0] == 3).all() and (field.vectors[1] == 0).all()

    def test_to_bgr_shape(self):
        field = FlowField.from_array(np.ones((2, 4, 5)))
        assert field.to_bgr().shape == (4, 5, 3)
        assert FlowField.from_array(np.zeros((2, 4, 5))).to_bgr().shape == (4, 5, 3)


@pytest.mark.parametrize("estimator_cls", [FarnebackFlow, DisFlow])
class TestOpenCvEstimators:
    def test_recovers_horizontal_shift(self, estimator_cls, shifted_pair):
        estimator = estimator_cls()
        assert isinstance(estimator, OpticalFlowEstimator)
        field = estimator.estimate(*shifted_pair)
        inner = field.vectors[:, 40:-40, 40:-40]
        assert np.median(inner[0]) == pytest.approx(-SHIFT_X, abs=1.0)
        assert np.median(inner[1]) == pytest.approx(0.0, abs=0.5)

    def test_rejects_invalid_frames(self, estimator_cls, shifted_pair):
        frame, other = shifted_pair
        estimator = estimator_cls()
        with pytest.raises(FrameValidationError):
            estimator.estimate(frame, other[:100])
        with pytest.raises(FrameValidationError):
            estimator.estimate(frame.astype(np.float32), frame.astype(np.float32))
        with pytest.raises(FrameValidationError):
            estimator.estimate(frame[..., 0], frame[..., 0])


class _ConstantFlowModel(torch.nn.Module):
    """Stands in for RAFT: predicts a uniform (1, 2) px flow at the size it was given."""

    def __init__(self):
        super().__init__()
        self.seen_shape = None

    def forward(self, img1, img2, **kwargs):
        self.seen_shape = tuple(img1.shape)
        flow = torch.zeros(img1.shape[0], 2, *img1.shape[2:])
        flow[:, 0], flow[:, 1] = 1.0, 2.0
        return [flow * 0, flow]


class TestRaftFlow:
    def test_working_size(self):
        assert working_size(1080, 1920, 360) == (360, 640)
        assert working_size(101, 203, 360) == (104, 200)  # small frames only snap to x8
        assert working_size(1000, 10, 360) == (360, 8)

    def test_downscales_and_rescales_vectors_per_axis(self):
        model = _ConstantFlowModel()
        raft = RaftFlow(device="cpu", max_height=64, model=model)
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        field = raft.estimate(frame, frame)

        new_h, new_w = working_size(200, 300, 64)
        assert model.seen_shape == (1, 3, new_h, new_w)
        assert (field.height, field.width) == (200, 300)
        assert np.allclose(field.vectors[0], 300 / new_w, atol=1e-4)
        assert np.allclose(field.vectors[1], 200 / new_h * 2, atol=1e-4)

    def test_no_resize_when_already_small(self):
        model = _ConstantFlowModel()
        raft = RaftFlow(device="cpu", max_height=360, model=model)
        frame = np.zeros((64, 96, 3), dtype=np.uint8)
        field = raft.estimate(frame, frame)
        assert model.seen_shape == (1, 3, 64, 96)
        assert np.allclose(field.vectors[0], 1.0) and np.allclose(field.vectors[1], 2.0)

    def test_rejects_invalid_arguments(self):
        with pytest.raises(ValueError):
            RaftFlow(device="cpu", max_height=4, model=_ConstantFlowModel())
        raft = RaftFlow(device="cpu", model=_ConstantFlowModel())
        with pytest.raises(FrameValidationError):
            raft.estimate(
                np.zeros((64, 64, 3), np.uint8), np.zeros((64, 72, 3), np.uint8)
            )


class TestVideoFlow:
    def test_yields_one_field_per_frame_pair(self, tmp_path, shifted_pair):
        frame, _ = shifted_pair
        path = tmp_path / "clip.avi"
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, frame.shape[1::-1]
        )
        for _ in range(5):
            writer.write(frame)
        writer.release()

        fields = list(estimate_video_flow(path, FarnebackFlow()))
        assert len(fields) == 4
        assert len(list(estimate_video_flow(path, FarnebackFlow(), step=2))) == 2

    def test_rejects_bad_input(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            next(estimate_video_flow(tmp_path / "missing.mp4", FarnebackFlow()))
        with pytest.raises(ValueError):
            next(estimate_video_flow(tmp_path / "x.mp4", FarnebackFlow(), step=0))
