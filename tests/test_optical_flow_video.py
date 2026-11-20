"""FlowVideo: cache keys, resumable computation, and rendering from the cache. Uses DIS flow, so no model downloads."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

pytest.importorskip("ultralytics")

from mediatools.vision import (
    FlowCache,
    FlowSettings,
    FlowVideo,
    OverlayOptions,
    ParticleOptions,
)
from mediatools.vision.flow_render import ParticleSystem, sample_bilinear

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def sliding_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A textured scene panning left 3 px per frame."""
    path = tmp_path_factory.mktemp("flow") / "slide.mp4"
    rng = np.random.default_rng(0)
    texture = cv2.GaussianBlur(rng.integers(0, 255, (160, 400, 3), dtype=np.uint8), (0, 0), 2)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (192, 128))
    for i in range(16):
        writer.write(texture[16:144, i * 3 : i * 3 + 192].copy())
    writer.release()
    return path


def frame_count(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    codec, frames = out.split(",")
    assert codec == "h264"
    return int(frames)


def test_cache_key_and_folder_name_are_stable(tmp_path: Path):
    # Existing caches must stay valid, so the key's contents and hashing may not change.
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 1234)
    os.utime(video, ns=(0, 1_700_000_000_123_456_789))
    settings = FlowSettings(algorithm="raft", raft_max_height=720, raft_variant="large", raft_flow_updates=24, cache_height=720)
    cache = FlowCache(tmp_path / "cache", video, settings, 1920, 1080)
    expected = {
        "video": str(video.resolve()), "video_size": 1234, "video_mtime_ns": 1_700_000_000_123_456_789,
        "algorithm": "raft", "params": {"max_height": 720, "variant": "large", "num_flow_updates": 24},
        "step": 1, "cache_height": 720, "format": 1,
    }
    assert cache.key == expected
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()[:12]
    assert cache.directory == tmp_path / "cache" / f"clip-{digest}"
    # The device only changes where RAFT runs, not its result.
    assert FlowCache(tmp_path / "cache", video, FlowSettings(**{**settings.__dict__, "device": "cpu"}), 1920, 1080).directory == cache.directory
    assert FlowCache(tmp_path / "cache", video, FlowSettings(**{**settings.__dict__, "step": 2}), 1920, 1080).directory != cache.directory


def test_compute_resumes_and_extends_the_cache(sliding_video: Path, tmp_path: Path):
    settings = FlowSettings(algorithm="dis", dis_preset="ultrafast")
    first = FlowVideo(sliding_video, settings, tmp_path, max_frames=5)
    assert len(first.pairs) == 5 and first.missing() == [0, 1, 2, 3, 4]
    assert list(first.compute(first.missing())) == [0, 1, 2, 3, 4]

    longer = FlowVideo(sliding_video, settings, tmp_path)
    assert len(longer.pairs) == 15  # 16 frames
    assert longer.missing() == list(range(5, 15))
    assert list(longer.compute([7, 8])) == [7, 8]  # only what is asked for, from the middle of the video
    assert longer.missing() == [5, 6, 9, 10, 11, 12, 13, 14]
    assert longer.missing(recompute=True) == list(range(15))

    flow = longer.cache.load(0)
    assert (flow.height, flow.width) == (128, 192)
    assert abs(float(flow.vectors[0].mean()) + 3.0) < 0.5  # the scene pans left by 3 px per frame


def test_cached_flow_is_stored_downscaled_and_restored_to_full_size(sliding_video: Path, tmp_path: Path):
    flow = FlowVideo(sliding_video, FlowSettings(dis_preset="ultrafast", cache_height=64), tmp_path)
    list(flow.compute([0]))
    stored = np.load(flow.cache.directory / "0000000.npy")
    assert stored.shape == (2, 64, 96) and stored.dtype == np.float16
    restored = flow.cache.load(0)
    assert (restored.height, restored.width) == (128, 192)
    assert abs(float(restored.vectors[0].mean()) + 3.0) < 0.5  # vectors rescaled with the image


def test_step_skips_frames(sliding_video: Path, tmp_path: Path):
    flow = FlowVideo(sliding_video, FlowSettings(dis_preset="ultrafast", step=3), tmp_path)
    assert len(flow.pairs) == 5  # (16 - 1) // 3
    assert list(flow.compute(flow.missing())) == [0, 1, 2, 3, 4]
    assert abs(float(flow.cache.load(2).vectors[0].mean()) + 9.0) < 1.0  # 3 frames = 9 px


@needs_ffmpeg
def test_render_writes_h264_and_stops_at_the_first_uncached_pair(sliding_video: Path, tmp_path: Path):
    flow = FlowVideo(sliding_video, FlowSettings(dis_preset="ultrafast"), tmp_path / "cache")
    list(flow.compute([0, 1, 2, 4, 5]))  # pair 3 is missing
    overlay = OverlayOptions(output=tmp_path / "overlay.mp4", side_by_side=True)
    particles = ParticleOptions(output=tmp_path / "particles.mp4", count=300, height=64)
    assert list(flow.render(overlay, particles)) == [1, 2, 3]
    assert frame_count(overlay.output) == 3 and frame_count(particles.output) == 3
    size = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
         str(particles.output)], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert size == "96,64"


@needs_ffmpeg
def test_closing_render_early_still_finishes_the_files(sliding_video: Path, tmp_path: Path):
    flow = FlowVideo(sliding_video, FlowSettings(dis_preset="ultrafast"), tmp_path / "cache")
    list(flow.compute(flow.missing()))
    generator = flow.render(None, ParticleOptions(output=tmp_path / "p.mp4", count=100, height=0))
    assert next(generator) == 1 and next(generator) == 2
    generator.close()
    assert frame_count(tmp_path / "p.mp4") == 2


def test_bilinear_sampling_is_exact_for_a_linear_field():
    ys, xs = np.mgrid[0:40, 0:60].astype(np.float32)
    field = np.stack([2 * xs + 3 * ys, -xs + 0.5 * ys])
    points = np.random.default_rng(1).random((500, 2), dtype=np.float32) * [59, 39]
    expected = np.stack([2 * points[:, 0] + 3 * points[:, 1], -points[:, 0] + 0.5 * points[:, 1]], axis=1)
    assert np.abs(sample_bilinear(field, points) - expected).max() < 1e-3
    corner = sample_bilinear(field, np.array([[59.0, 39.0]], dtype=np.float32))
    assert np.allclose(corner, [[2 * 59 + 3 * 39, -59 + 0.5 * 39]])


def test_particles_follow_the_flow_and_respawn_when_they_leave():
    field = np.zeros((2, 50, 100), dtype=np.float32)
    field[0] = 10.0  # everything moves right by 10 px per frame
    system = ParticleSystem(200, 100, 50, lifetime=1000, rng=np.random.default_rng(0))
    start = system.positions.copy()
    previous, alive = system.advance(field, substeps=4)
    assert np.allclose(previous, start)
    moved = np.where(alive)[0]
    assert np.allclose(system.positions[moved] - start[moved], [10.0, 0.0], atol=1e-4)
    assert (~alive).any() and ((system.positions >= 0) & (system.positions < [100, 50])).all()  # leavers respawn inside
