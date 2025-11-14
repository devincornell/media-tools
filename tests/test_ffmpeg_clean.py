import tempfile
import datetime
from pathlib import Path
import requests
import pytest
import shutil

import sys
sys.path.append('../src')

import mediatools
from mediatools.video import VideoFiles
from mediatools.video.ffmpeg.probe import probe
from mediatools.video.ffmpeg.ffmpeg import FFMPEG, ffinput, ffoutput


@pytest.fixture(scope="module")
def test_video():
    """Download a test video for the entire test session"""
    url = "https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv"
    temp_dir = tempfile.mkdtemp()
    video_path = Path(temp_dir) / "test_video.mkv"
    
    print(f"\nDownloading test video to {video_path}...")
    response = requests.get(url, stream=True)
    with open(video_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    yield video_path
    
    # Cleanup after all tests
    shutil.rmtree(temp_dir)

@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

# Skip tests that require FFmpeg if not available
ffmpeg_available = shutil.which('ffmpeg') is not None
requires_ffmpeg = pytest.mark.skipif(not ffmpeg_available, reason="FFmpeg not available")


def test_probe_video_properties(test_video):
    """Test that we can probe a video file and get detailed info"""
    probe_info = probe(test_video)
    
    # Basic assertions
    assert probe_info.duration > 0
    assert probe_info.video.width > 0
    assert probe_info.video.height > 0
    assert probe_info.format_name is not None
    
    # Check that the video has reasonable properties for the TOTK video
    assert probe_info.video.width == 480  # This is a portrait video
    assert probe_info.video.height == 854
    assert probe_info.duration > 5  # Should be around 23 seconds
    assert probe_info.format_name in ["matroska,webm", "mov,mp4,m4a,3gp,3g2,mj2"]
    
    # Test video stream properties
    video_stream = probe_info.video
    assert video_stream.codec_name in ["h264", "mpeg4"]
    assert video_stream.pixels == 480 * 854
    assert abs(video_stream.aspect_ratio - (480/854)) < 0.01
    assert video_stream.resolution == (480, 854)
    
    # Test audio stream properties if available
    if probe_info.audio_streams:
        audio_stream = probe_info.audio
        assert audio_stream.codec_name in ["aac", "mp3", "ac3", "vorbis"]
        assert audio_stream.channels > 0
        assert audio_stream.sample_rate > 0


def test_ffmpeg_command_generation(test_video, temp_output_dir):
    """Test that FFMPEG generates correct command lines"""
    output_path = temp_output_dir / "test.mp4"
    
    # Create a command with various options
    cmd = FFMPEG(
        inputs=[
            ffinput(test_video, ss="10", t="5")
        ],
        outputs=[
            ffoutput(output_path, c_v="libx264", crf=23, preset="fast", v_f="scale=640:360", y=True)
        ],
        hide_banner=True,
        loglevel="error"
    )
    
    # Get the command as list of strings
    command_list = cmd.build_command()
    command_str = ' '.join(command_list)
    
    # Verify key components are present
    assert "ffmpeg" in command_str
    assert str(test_video) in command_str
    assert str(output_path) in command_str
    assert "-ss 10" in command_str
    assert "-t 5" in command_str
    assert "-c:v libx264" in command_str
    assert "-crf 23" in command_str
    assert "-preset fast" in command_str
    assert "-vf scale=640:360" in command_str
    assert "-y" in command_str
    assert "-hide_banner" in command_str
    assert "-loglevel error" in command_str


@requires_ffmpeg
def test_ffmpeg_basic_conversion(test_video, temp_output_dir):
    """Test basic video format conversion using FFMPEG class"""
    output_path = temp_output_dir / "output.mp4"
    
    # Get original video properties
    original_probe = probe(test_video)
    
    # Create FFMPEG command for format conversion
    cmd = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, c_v="libx264", c_a="aac", y=True)]
    )
    
    # Run the command
    cmd.run()
    
    # Verify output exists
    assert output_path.exists()
    
    # Probe the output and verify properties
    output_probe = probe(output_path)
    
    # Video should maintain same resolution
    assert output_probe.video.width == original_probe.video.width
    assert output_probe.video.height == original_probe.video.height
    
    # Duration should be approximately the same (within 1 second)
    assert abs(output_probe.duration - original_probe.duration) < 1.0
    
    # Format should be mp4
    assert "mp4" in output_probe.format_name
    
    # Video codec should be H.264
    assert output_probe.video.codec_name == "h264"


@requires_ffmpeg
def test_ffmpeg_video_scaling(test_video, temp_output_dir):
    """Test video scaling using FFMPEG class"""
    output_path = temp_output_dir / "scaled.mp4"
    
    # Get original video properties
    original_probe = probe(test_video)
    
    # Scale video to 720p
    target_width, target_height = 1280, 720
    cmd = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, v_f=f"scale={target_width}:{target_height}", c_v="libx264", y=True)]
    )
    
    cmd.run()
    
    # Verify output
    assert output_path.exists()
    output_probe = probe(output_path)
    
    # Check that scaling worked
    assert output_probe.video.width == target_width
    assert output_probe.video.height == target_height
    
    # Duration should be preserved
    assert abs(output_probe.duration - original_probe.duration) < 1.0


@requires_ffmpeg
def test_ffmpeg_video_trimming(test_video, temp_output_dir):
    """Test video trimming using FFMPEG class"""
    output_path = temp_output_dir / "trimmed.mp4"
    
    # Trim first 10 seconds of video
    start_time = "00:00:00"
    duration = "10"
    
    cmd = FFMPEG(
        inputs=[ffinput(test_video, ss=start_time)],
        outputs=[ffoutput(output_path, t=duration, c_v="libx264", y=True)]
    )
    
    cmd.run()
    
    # Verify output
    assert output_path.exists()
    output_probe = probe(output_path)
    
    # Duration should be approximately 10 seconds
    assert 9.0 <= output_probe.duration <= 11.0
    
    # Resolution should be preserved
    original_probe = probe(test_video)
    assert output_probe.video.width == original_probe.video.width
    assert output_probe.video.height == original_probe.video.height


@requires_ffmpeg
def test_ffmpeg_quality_adjustment(test_video, temp_output_dir):
    """Test video quality adjustment using CRF"""
    output_path = temp_output_dir / "quality_adjusted.mp4"
    
    # Apply higher compression (lower quality)
    cmd = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, c_v="libx264", crf=28, y=True)]  # Higher CRF = more compression
    )
    
    cmd.run()
    
    # Verify output
    assert output_path.exists()
    output_probe = probe(output_path)
    
    # Resolution should be preserved
    original_probe = probe(test_video)
    assert output_probe.video.width == original_probe.video.width
    assert output_probe.video.height == original_probe.video.height
    
    # File should be smaller (more compressed)
    assert output_path.stat().st_size < test_video.stat().st_size


@requires_ffmpeg
def test_ffmpeg_audio_extraction(test_video, temp_output_dir):
    """Test audio extraction using FFMPEG class"""
    output_path = temp_output_dir / "audio.mp3"
    
    # Extract audio only
    cmd = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, vn=True, c_a="libmp3lame", y=True)]
    )
    
    cmd.run()
    
    # Verify output
    assert output_path.exists()
    output_probe = probe(output_path)
    
    # Should have no video streams
    assert len(output_probe.video_streams) == 0
    
    # Should have audio stream(s)
    assert len(output_probe.audio_streams) > 0
    
    # Duration should be approximately the same
    original_probe = probe(test_video)
    assert abs(output_probe.duration - original_probe.duration) < 1.0


@requires_ffmpeg
def test_ffmpeg_multiple_outputs(test_video, temp_output_dir):
    """Test creating multiple outputs with different settings"""
    output_720p = temp_output_dir / "output_720p.mp4"
    output_480p = temp_output_dir / "output_480p.mp4"
    
    # Create two outputs with different resolutions
    cmd = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[
            ffoutput(output_720p, v_f="scale=1280:720", c_v="libx264", b_v="2M", y=True),
            ffoutput(output_480p, v_f="scale=854:480", c_v="libx264", b_v="1M", y=True)
        ]
    )
    
    cmd.run()
    
    # Verify both outputs exist and have correct properties
    assert output_720p.exists()
    assert output_480p.exists()
    
    probe_720p = probe(output_720p)
    probe_480p = probe(output_480p)
    
    # Check resolutions
    assert probe_720p.video.width == 1280
    assert probe_720p.video.height == 720
    assert probe_480p.video.width == 854
    assert probe_480p.video.height == 480
    
    # Both should have similar durations
    original_probe = probe(test_video)
    assert abs(probe_720p.duration - original_probe.duration) < 1.0
    assert abs(probe_480p.duration - original_probe.duration) < 1.0


@requires_ffmpeg
def test_ffmpeg_seeking_with_accuracy(test_video, temp_output_dir):
    """Test seeking to specific time with frame accuracy"""
    output_path = temp_output_dir / "seek_test.mp4"
    
    # Seek to 30 seconds and extract 5 seconds
    cmd = FFMPEG(
        inputs=[ffinput(test_video, ss="30")],
        outputs=[ffoutput(output_path, t="5", c_v="libx264", y=True)]
    )
    
    cmd.run()
    
    # Verify output
    assert output_path.exists()
    output_probe = probe(output_path)
    
    # Duration should be approximately 5 seconds
    assert 4.5 <= output_probe.duration <= 5.5
    
    # Resolution should be preserved
    original_probe = probe(test_video)
    assert output_probe.video.width == original_probe.video.width
    assert output_probe.video.height == original_probe.video.height


@requires_ffmpeg
def test_ffmpeg_overwrite_protection(test_video, temp_output_dir):
    """Test that overwrite protection works correctly"""
    output_path = temp_output_dir / "overwrite_test.mp4"
    
    # First conversion
    cmd1 = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, c_v="libx264", y=True)]
    )
    cmd1.run()
    
    # Verify file exists
    assert output_path.exists()
    original_size = output_path.stat().st_size
    
    # Second conversion with overwrite flag
    cmd2 = FFMPEG(
        inputs=[ffinput(test_video)],
        outputs=[ffoutput(output_path, c_v="libx264", crf=30, y=True)]
    )
    cmd2.run()
    
    # File should still exist (possibly different size due to different CRF)
    assert output_path.exists()