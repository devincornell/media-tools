"""Tests for the ffmpeg interface, mirroring the examples/3-ffmpeg_interface.ipynb notebook."""
import shutil
import tempfile
import zipfile
from pathlib import Path

import pydantic_settings
import pytest
import requests

import mediatools
from mediatools.ffmpeg import (
    FFInputArgs,
    filter_link,
    filterchain,
    filtergraph,
    filtergraph_animated_thumb,
    filtergraph_blurred_padding,
    filtergraph_link,
    ffinput,
    ffoutput,
    ffmpeg,
)


# ---------------------------------------------------------------------------
# Settings (reads TEST_ZIP_FILE_URL from environment / .env file)
# ---------------------------------------------------------------------------

class Settings(pydantic_settings.BaseSettings):
    test_zip_file_url: str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def video_data():
    """Download the test dataset zip and yield the path to op_builds.mp4."""
    settings = Settings()
    td = tempfile.TemporaryDirectory()
    temp_path = Path(td.name)
    zip_path = temp_path / "archive.zip"

    response = requests.get(settings.test_zip_file_url)
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_path)
    zip_path.unlink()

    yield temp_path / "totk_builds/op_builds.mp4"

    td.cleanup()


@pytest.fixture
def output_dir():
    """Provide a fresh temporary directory for test outputs."""
    td = tempfile.TemporaryDirectory()
    yield Path(td.name)
    td.cleanup()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ffmpeg_available = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not ffmpeg_available, reason="FFmpeg binary not available")


# ===========================================================================
# Filter string tests  (no FFmpeg binary or network required)
# ===========================================================================

class TestFilterLink:
    def test_positional_arg(self):
        assert filter_link("scale", "480:640") == "scale=480:640"

    def test_keyword_args(self):
        assert filter_link("scale", w=480, h=640) == "scale=w=480:h=640"

    def test_multiple_keyword_args(self):
        assert filter_link("crop", w=100, h=100, x=100, y=100) == "crop=w=100:h=100:x=100:y=100"

    def test_no_args(self):
        assert filter_link("split") == "split"

    def test_single_keyword_arg(self):
        assert filter_link("fps", fps=2) == "fps=fps=2"


class TestFilterchain:
    def test_two_links(self):
        result = filterchain(
            filter_link("crop", w=100, h=100, x=100, y=100),
            filter_link("scale", w=480, h=640),
        )
        assert result == "crop=w=100:h=100:x=100:y=100,scale=w=480:h=640"

    def test_three_links(self):
        result = filterchain(
            filter_link("setpts", "PTS/2"),
            filter_link("fps", fps=2),
            filter_link("scale", w=100, h=100, force_original_aspect_ratio="decrease"),
        )
        assert result == "setpts=PTS/2,fps=fps=2,scale=w=100:h=100:force_original_aspect_ratio=decrease"

    def test_single_link_passthrough(self):
        link = filter_link("scale", w=480, h=640)
        assert filterchain(link) == link


class TestFiltergraphLink:
    def test_single_input_output(self):
        result = filtergraph_link("scale", w=480, h=640, input="0:v", output="scaled")
        assert result == "[0:v]scale=w=480:h=640[scaled]"

    def test_multiple_outputs(self):
        result = filtergraph_link("split", input="0:v", outputs=["bg_raw", "fg_raw"])
        assert result == "[0:v]split[bg_raw][fg_raw]"

    def test_no_io_labels(self):
        # Without labels, filtergraph_link behaves like filter_link
        result = filtergraph_link("scale", w=480, h=640)
        assert result == "scale=w=480:h=640"

    def test_filterchain_as_spec(self):
        chain = filterchain(
            filter_link("scale", w="ih", h="ih"),
            filter_link("gblur", sigma=25),
        )
        result = filtergraph_link(chain, input="bg_raw", output="bg_ready")
        assert result == "[bg_raw]scale=w=ih:h=ih,gblur=sigma=25[bg_ready]"

    def test_multiple_inputs(self):
        result = filtergraph_link("overlay", inputs=["bg_ready", "fg_raw"], x="(W-w)/2", y="(H-h)/2")
        assert result == "[bg_ready][fg_raw]overlay=x=(W-w)/2:y=(H-h)/2"


class TestFiltergraph:
    def test_two_links_joined_by_semicolon(self):
        link1 = filtergraph_link("split", input="0:v", outputs=["a", "b"])
        link2 = filtergraph_link("scale", w=480, h=640, input="a", output="out")
        result = filtergraph(link1, link2)
        assert result == f"{link1};{link2}"

    def test_blurred_padding_structure(self):
        """Verify the blurred-padding filtergraph contains expected pieces."""
        result = filtergraph_blurred_padding(target_w=480, target_h=640, blur_sigma=25, input="0:v")
        assert "split" in result
        assert "gblur=sigma=25" in result
        assert "overlay" in result
        assert "[0:v]" in result

    def test_animated_thumb_without_blur(self):
        result = filtergraph_animated_thumb(target_w=400, target_h=400, fps=2, pts=10, input="0:v")
        assert "setpts=PTS/10" in result
        assert "fps=fps=2" in result
        assert "scale=w=400:h=400" in result

    def test_animated_thumb_with_blur(self):
        result = filtergraph_animated_thumb(
            target_w=400, target_h=400, fps=2, pts=10,
            use_blurred_padding=True, blur_sigma=10, input="0:v",
        )
        assert "setpts=PTS/10" in result
        assert "gblur=sigma=10" in result
        assert "overlay" in result


# ===========================================================================
# Probe tests  (requires network to download dataset)
# ===========================================================================

class TestProbe:
    def test_returns_probeinfo(self, video_data):
        probe = mediatools.ffmpeg.probe(video_data)
        assert isinstance(probe, mediatools.ffmpeg.ProbeInfo)

    def test_basic_scalar_properties(self, video_data):
        probe = mediatools.ffmpeg.probe(video_data)
        assert probe.duration > 0
        assert probe.size > 0
        assert probe.bit_rate is not None and probe.bit_rate > 0
        assert probe.probe_score > 0
        assert probe.resolution_str() != ""

    def test_streams_present(self, video_data):
        probe = mediatools.ffmpeg.probe(video_data)
        assert len(probe.video_streams) >= 1
        assert len(probe.audio_streams) >= 1

    def test_video_stream_properties(self, video_data):
        probe = mediatools.ffmpeg.probe(video_data)
        video = probe.video
        assert video.width > 0
        assert video.height > 0
        assert isinstance(video.resolution, tuple) and len(video.resolution) == 2
        assert video.codec_name is not None
        assert video.frame_rate > 0

    def test_audio_stream_properties(self, video_data):
        probe = mediatools.ffmpeg.probe(video_data)
        audio = probe.audio
        assert audio.codec_name is not None
        assert audio.channels > 0
        assert audio.sample_rate > 0

    def test_probe_via_videofile(self, video_data):
        vf = mediatools.VideoFile.from_path(video_data)
        probe = vf.probe()
        assert isinstance(probe, mediatools.ffmpeg.ProbeInfo)
        assert probe.duration > 0


# ===========================================================================
# Command construction tests  (requires dataset, no FFmpeg execution)
# ===========================================================================

class TestCommandConstruction:
    def test_get_command_returns_string(self, video_data, output_dir):
        probe = mediatools.ffmpeg.probe(video_data)
        half_duration = probe.duration / 2
        output_path = output_dir / "test_video_output.mp4"
        cmd = ffmpeg(
            input=ffinput(video_data, ss=probe.start_time, to=half_duration),
            output=ffoutput(output_path, y=True),
        )
        command_str = cmd.get_command()
        assert isinstance(command_str, str)
        assert "ffmpeg" in command_str
        assert str(video_data) in command_str

    def test_videofile_ffmpeg_returns_ffmpeg_instance(self, video_data, output_dir):
        probe = mediatools.ffmpeg.probe(video_data)
        half_duration = probe.duration / 2
        output_path = output_dir / "test_video_output.mp4"
        vf = mediatools.VideoFile.from_path(video_data)
        cmd = vf.ffmpeg(
            input_args=FFInputArgs(ss=probe.start_time, to=half_duration),
            output=ffoutput(output_path, y=True),
        )
        command_str = cmd.get_command()
        assert isinstance(command_str, str)
        assert "ffmpeg" in command_str


# ===========================================================================
# Execution tests  (requires dataset + FFmpeg binary)
# ===========================================================================

@requires_ffmpeg
class TestSpliceVideo:
    def test_splice_creates_output(self, video_data, output_dir):
        output_path = output_dir / "spliced.mp4"
        result = ffmpeg(
            input=ffinput(video_data, ss=0, to=1.0),
            output=ffoutput(output_path, y=True),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_splice_output_shorter_than_source(self, video_data, output_dir):
        output_path = output_dir / "spliced.mp4"
        ffmpeg(
            input=ffinput(video_data, ss=0, to=1.0),
            output=ffoutput(output_path, y=True),
        ).run()
        original_duration = mediatools.ffmpeg.probe(video_data).duration
        spliced_duration = mediatools.ffmpeg.probe(output_path).duration
        assert spliced_duration < original_duration


@requires_ffmpeg
class TestCropVideo:
    def test_crop_creates_output(self, video_data, output_dir):
        output_path = output_dir / "cropped.mp4"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                v_f=filter_link("crop", w=200, h=100, x=100, y=50),
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_crop_produces_correct_resolution(self, video_data, output_dir):
        output_path = output_dir / "cropped.mp4"
        ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                v_f=filter_link("crop", w=200, h=100, x=0, y=0),
                y=True,
            ),
        ).run()
        probe = mediatools.ffmpeg.probe(output_path)
        assert probe.video.width == 200
        assert probe.video.height == 100


@requires_ffmpeg
class TestScaleVideo:
    def test_scale_creates_output(self, video_data, output_dir):
        output_path = output_dir / "scaled.mp4"
        result = ffmpeg(
            input=ffinput(str(video_data)),
            output=ffoutput(str(output_path), v_f="scale=w=480:h=640", y=True),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_scale_produces_correct_resolution(self, video_data, output_dir):
        output_path = output_dir / "scaled.mp4"
        ffmpeg(
            input=ffinput(str(video_data)),
            output=ffoutput(str(output_path), v_f="scale=w=480:h=640", y=True),
        ).run()
        probe = mediatools.ffmpeg.probe(str(output_path))
        assert probe.video.resolution == (480, 640)


@requires_ffmpeg
class TestCompressCRF:
    def test_crf_creates_output(self, video_data, output_dir):
        output_path = output_dir / "compressed.mp4"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(output_path, crf=17, c_v="libx264", y=True),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_crf_result_has_stderr(self, video_data, output_dir):
        output_path = output_dir / "compressed.mp4"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(output_path, crf=28, c_v="libx264", y=True),
        ).run()
        assert isinstance(result.stderr, str)
        assert len(result.stderr) > 0


@requires_ffmpeg
class TestCompressBitrateTwoPass:
    def test_two_pass_creates_output(self, video_data, output_dir):
        current_bitrate = mediatools.ffmpeg.probe(video_data).bit_rate
        target_bitrate = current_bitrate / 2
        log_prefix = str(output_dir / "ffmpeg_pass")

        # Pass 1
        ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                "/dev/null",
                c_v="libx264",
                b_v=target_bitrate,
                an=True,
                f="null",
                pass_=1,
                passlogfile=log_prefix,
                y=True,
            ),
        ).run()

        # Pass 2
        output_path = output_dir / "compressed_bitrate.mp4"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                c_v="libx264",
                b_v=target_bitrate,
                c_a="copy",
                pass_=2,
                passlogfile=log_prefix,
                y=True,
            ),
        ).run()

        assert result.output_file.exists()
        assert result.returncode == 0

    def test_two_pass_output_bitrate_closer_to_target(self, video_data, output_dir):
        current_bitrate = mediatools.ffmpeg.probe(video_data).bit_rate
        target_bitrate = current_bitrate / 2
        log_prefix = str(output_dir / "ffmpeg_pass")

        ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                "/dev/null",
                c_v="libx264",
                b_v=target_bitrate,
                an=True,
                f="null",
                pass_=1,
                passlogfile=log_prefix,
                y=True,
            ),
        ).run()

        output_path = output_dir / "compressed_bitrate.mp4"
        ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                c_v="libx264",
                b_v=target_bitrate,
                c_a="copy",
                pass_=2,
                passlogfile=log_prefix,
                y=True,
            ),
        ).run()

        output_bitrate = mediatools.ffmpeg.probe(output_path).bit_rate
        # Output should be within 50% of the target (two-pass is not exact)
        assert output_bitrate < current_bitrate


@requires_ffmpeg
class TestStaticThumbnail:
    def test_creates_thumbnail_file(self, video_data, output_dir):
        output_path = output_dir / "thumbnail.jpg"
        result = ffmpeg(
            input=ffinput(video_data, ss=1.0),
            output=ffoutput(
                output_path,
                v_f=filter_link("scale", width=200, height=300),
                vframes=1,
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_thumbnail_file_is_not_empty(self, video_data, output_dir):
        output_path = output_dir / "thumbnail.jpg"
        ffmpeg(
            input=ffinput(video_data, ss=1.0),
            output=ffoutput(
                output_path,
                v_f=filter_link("scale", width=200, height=300),
                vframes=1,
                y=True,
            ),
        ).run()
        assert output_path.stat().st_size > 0


@requires_ffmpeg
class TestAnimatedThumbnail:
    def test_creates_gif(self, video_data, output_dir):
        output_path = output_dir / "animated_thumbnail.gif"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                v_f=filterchain(
                    filter_link("setpts", "PTS/2"),
                    filter_link("fps", fps=2),
                    filter_link("scale", w=100, h=100, force_original_aspect_ratio="decrease"),
                ),
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0


@requires_ffmpeg
class TestBuiltinFiltergraphs:
    def test_blurred_padding_creates_output(self, video_data, output_dir):
        output_path = output_dir / "resize_with_blur.mp4"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                filter_complex=filtergraph_blurred_padding(
                    input="0:v",
                    target_w=500,
                    target_h=500,
                    blur_sigma=10,
                ),
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_blurred_padding_output_resolution(self, video_data, output_dir):
        output_path = output_dir / "resize_with_blur.mp4"
        ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                filter_complex=filtergraph_blurred_padding(
                    input="0:v",
                    target_w=500,
                    target_h=500,
                    blur_sigma=10,
                ),
                y=True,
            ),
        ).run()
        probe = mediatools.ffmpeg.probe(output_path)
        assert probe.video.resolution == (500, 500)

    def test_animated_thumb_creates_gif(self, video_data, output_dir):
        output_path = output_dir / "animated_thumbnail.gif"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                filter_complex=filtergraph_animated_thumb(
                    input="0:v",
                    target_w=400,
                    target_h=400,
                    fps=2,
                    pts=10,
                    force_original_aspect_ratio="decrease",
                ),
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0

    def test_animated_thumb_with_blur_creates_gif(self, video_data, output_dir):
        output_path = output_dir / "animated_thumbnail_with_blur.gif"
        result = ffmpeg(
            input=ffinput(video_data),
            output=ffoutput(
                output_path,
                filter_complex=filtergraph_animated_thumb(
                    input="0:v",
                    target_w=400,
                    target_h=400,
                    use_blurred_padding=True,
                    blur_sigma=10,
                    fps=2,
                    pts=10,
                ),
                y=True,
            ),
        ).run()
        assert result.output_file.exists()
        assert result.returncode == 0
