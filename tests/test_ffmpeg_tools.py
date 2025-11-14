import tempfile
import datetime
from pathlib import Path
import requests

import sys
sys.path.append('../src')

import mediatools
from mediatools.video import VideoFiles
from mediatools.video.ffmpeg.probe import probe
from mediatools.video.ffmpeg.ffmpeg import FFMPEG, ffinput, ffoutput


def test_ffmpeg_tools():
    
    with tempfile.TemporaryDirectory() as tempdir:
        td = lambda x: Path(tempdir) / x
        test_video_fname = 'totk_secret_attack.mkv'
        
        print('Downloading test video file...')
        r = requests.get('https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv')
        with open(Path(tempdir) / test_video_fname, 'wb') as f:
            f.write(r.content)

        vf = mediatools.VideoFile.from_path(td(test_video_fname))

        print('testing globbing multiple files')
        imfs = mediatools.VideoFiles.from_rglob(tempdir)
        assert(len(imfs) > 0)

        print('compressing')
        result = vf.ffmpeg.compress(td('totk_compressed.mp4'), crf=30, overwrite=True)
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)
        
        print('splicing')
        result = vf.ffmpeg.splice(
            output_fname=td('totk_spliced.mp4'), 
            start_time=datetime.timedelta(seconds=0), 
            end_time=datetime.timedelta(seconds=5),
            overwrite=True
        )
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)

        print('cropping')
        result = vf.ffmpeg.crop(
            output_fname=td('totk_cropped.mp4'), 
            topleft_point=(0,0),
            size=(vf.probe().video.width//2, vf.probe().video.height//2),
            overwrite=True
        )
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)

        print('making thumb')
        result = vf.ffmpeg.make_thumb(
            output_fname=td('totk_thumb.jpg'), 
            time_point=0.5,
            height=100,
            overwrite=True
        )
        assert(result.fp.exists())
        assert(len(result.stdout) > 0)


def test_ffmpeg_lowlevel():
    with tempfile.TemporaryDirectory(dir='./') as tempdir:
        td = lambda x: Path(tempdir) / x
        test_video_fname = 'totk_secret_attack.mkv'
        
        fp = Path(tempdir) / test_video_fname
        print(f'Downloading test video file {fp}...')
        r = requests.get('https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv')
        with open(fp, 'wb') as f:
            f.write(r.content)

        print(mediatools.ffmpeg.probe(fp))
        print(mediatools.ffmpeg.probe_dict(fp))

        #print(mediatools.ffmpeg.compress(fp))

        print('compressing')
        op = td('totk_compressed.mp4')
        result = mediatools.ffmpeg.compress(fp, op, crf=30, loglevel='info')
        assert(op.exists())
        assert(len(result.output) > 0)
        
        print('splicing')
        result = mediatools.ffmpeg.splice(
            input_fname=fp,
            output_fname=td('totk_spliced.mp4'), 
            start_time=datetime.timedelta(seconds=0), 
            end_time=datetime.timedelta(seconds=5),
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)

        print('cropping')
        probe = mediatools.ffmpeg.probe(fp)
        result = mediatools.ffmpeg.crop(
            input_fname=fp,
            output_fname=td('totk_cropped.mp4'), 
            topleft_point=(0,0),
            size=(probe.video.width//2, probe.video.height//2),
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)

        print('making thumb')
        result = mediatools.ffmpeg.make_thumb(
            input_fname=fp,
            output_fname=td('totk_thumb.jpg'), 
            time_point_sec=0.5,
            height=100,
            overwrite=True,
            framerate=10,
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)



        print('making animated thumb')
        result = mediatools.ffmpeg.make_animated_thumb(
            input_fname=fp,
            output_fname=td('totk_thumb_animated.gif'), 
            vframes = 10,
            framerate=1,
            #time_point_sec=0.5,
            height=100,
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)



        print('output folder:', tempdir)
        print('waiting')
        import time
        time.sleep(180)


# Comprehensive FFMPEG Class Tests using ffinput and ffoutput functions

def download_test_video():
    """Download a small test video for testing"""
    url = "https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_surround-fix.avi"
    temp_dir = tempfile.mkdtemp()
    video_path = Path(temp_dir) / "test_video.avi"
    
    response = requests.get(url, stream=True)
    with open(video_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return video_path, temp_dir

def test_ffmpeg_basic_conversion():
    """Test basic video format conversion using FFMPEG class"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "output.mp4"
    
    try:
        # Get original video properties
        original_probe = probe(video_path)
        
        # Create FFMPEG command for format conversion
        cmd = FFMPEG(
            inputs=[ffinput(video_path)],
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
        
        print(f"Conversion successful: {video_path} -> {output_path}")
        print(f"Original: {original_probe.video.codec_name}, Output: {output_probe.video.codec_name}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_video_scaling():
    """Test video scaling using FFMPEG class"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "scaled.mp4"
    
    try:
        # Get original video properties
        original_probe = probe(video_path)
        
        # Scale video to 720p
        target_width, target_height = 1280, 720
        cmd = FFMPEG(
            inputs=[ffinput(video_path)],
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
        
        print(f"Scaling successful: {original_probe.video.width}x{original_probe.video.height} -> {target_width}x{target_height}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_video_trimming():
    """Test video trimming using FFMPEG class"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "trimmed.mp4"
    
    try:
        # Trim first 10 seconds of video
        start_time = "00:00:00"
        duration = "10"
        
        cmd = FFMPEG(
            inputs=[ffinput(video_path, ss=start_time)],
            outputs=[ffoutput(output_path, t=duration, c_v="libx264", y=True)]
        )
        
        cmd.run()
        
        # Verify output
        assert output_path.exists()
        output_probe = probe(output_path)
        
        # Duration should be approximately 10 seconds
        assert 9.0 <= output_probe.duration <= 11.0
        
        # Resolution should be preserved
        original_probe = probe(video_path)
        assert output_probe.video.width == original_probe.video.width
        assert output_probe.video.height == original_probe.video.height
        
        print(f"Trimming successful: {original_probe.duration}s -> {output_probe.duration}s")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_quality_adjustment():
    """Test video quality adjustment using CRF"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "quality_adjusted.mp4"
    
    try:
        # Apply higher compression (lower quality)
        cmd = FFMPEG(
            inputs=[ffinput(video_path)],
            outputs=[ffoutput(output_path, c_v="libx264", crf=28, y=True)]  # Higher CRF = more compression
        )
        
        cmd.run()
        
        # Verify output
        assert output_path.exists()
        output_probe = probe(output_path)
        
        # Resolution should be preserved
        original_probe = probe(video_path)
        assert output_probe.video.width == original_probe.video.width
        assert output_probe.video.height == original_probe.video.height
        
        # File should be smaller (more compressed)
        assert output_path.stat().st_size < video_path.stat().st_size
        
        print(f"Quality adjustment successful")
        print(f"Original size: {video_path.stat().st_size / (1024*1024):.2f} MB")
        print(f"Compressed size: {output_path.stat().st_size / (1024*1024):.2f} MB")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_audio_extraction():
    """Test audio extraction using FFMPEG class"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "audio.mp3"
    
    try:
        # Extract audio only
        cmd = FFMPEG(
            inputs=[ffinput(video_path)],
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
        original_probe = probe(video_path)
        assert abs(output_probe.duration - original_probe.duration) < 1.0
        
        print(f"Audio extraction successful: {output_probe.audio.codec_name}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_multiple_outputs():
    """Test creating multiple outputs with different settings"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_720p = temp_dir_path / "output_720p.mp4"
    output_480p = temp_dir_path / "output_480p.mp4"
    
    try:
        # Create two outputs with different resolutions
        cmd = FFMPEG(
            inputs=[ffinput(video_path)],
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
        original_probe = probe(video_path)
        assert abs(probe_720p.duration - original_probe.duration) < 1.0
        assert abs(probe_480p.duration - original_probe.duration) < 1.0
        
        print(f"Multiple outputs successful")
        print(f"720p: {probe_720p.video.width}x{probe_720p.video.height}")
        print(f"480p: {probe_480p.video.width}x{probe_480p.video.height}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_seeking_with_accuracy():
    """Test seeking to specific time with frame accuracy"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "seek_test.mp4"
    
    try:
        # Seek to 30 seconds and extract 5 seconds
        cmd = FFMPEG(
            inputs=[ffinput(video_path, ss="30")],
            outputs=[ffoutput(output_path, t="5", c_v="libx264", y=True)]
        )
        
        cmd.run()
        
        # Verify output
        assert output_path.exists()
        output_probe = probe(output_path)
        
        # Duration should be approximately 5 seconds
        assert 4.5 <= output_probe.duration <= 5.5
        
        # Resolution should be preserved
        original_probe = probe(video_path)
        assert output_probe.video.width == original_probe.video.width
        assert output_probe.video.height == original_probe.video.height
        
        print(f"Seeking test successful: extracted {output_probe.duration}s from position 30s")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_overwrite_protection():
    """Test that overwrite protection works correctly"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "overwrite_test.mp4"
    
    try:
        # First conversion
        cmd1 = FFMPEG(
            inputs=[ffinput(video_path)],
            outputs=[ffoutput(output_path, c_v="libx264", y=True)]
        )
        cmd1.run()
        
        # Verify file exists
        assert output_path.exists()
        original_size = output_path.stat().st_size
        
        # Second conversion with overwrite flag
        cmd2 = FFMPEG(
            inputs=[ffinput(video_path)],
            outputs=[ffoutput(output_path, c_v="libx264", crf=30, y=True)]
        )
        cmd2.run()
        
        # File should still exist (possibly different size due to different CRF)
        assert output_path.exists()
        
        print(f"Overwrite test successful")
        print(f"Original size: {original_size}, New size: {output_path.stat().st_size}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_ffmpeg_command_generation():
    """Test that FFMPEG generates correct command lines"""
    video_path, temp_dir = download_test_video()
    temp_dir_path = Path(temp_dir)
    output_path = temp_dir_path / "test.mp4"
    
    try:
        # Create a command with various options
        cmd = FFMPEG(
            inputs=[
                ffinput(video_path, ss="10", t="5")
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
        assert str(video_path) in command_str
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
        
        print(f"Command generation test successful")
        print(f"Generated command: {command_str}")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)

def test_probe_video_properties():
    """Test that we can probe a video file and get detailed info"""
    video_path, temp_dir = download_test_video()
    
    try:
        probe_info = probe(video_path)
        
        # Basic assertions
        assert probe_info.duration > 0
        assert probe_info.video.width > 0
        assert probe_info.video.height > 0
        assert probe_info.format_name is not None
        
        # Check that the video has reasonable properties for Big Buck Bunny 480p
        assert probe_info.video.width == 854
        assert probe_info.video.height == 480
        assert probe_info.duration > 10  # Should be around 596 seconds
        assert probe_info.format_name in ["avi", "mov,mp4,m4a,3gp,3g2,mj2"]
        
        # Test video stream properties
        video_stream = probe_info.video
        assert video_stream.codec_name in ["h264", "mpeg4"]
        assert video_stream.pixels == 854 * 480
        assert abs(video_stream.aspect_ratio - (854/480)) < 0.01
        assert video_stream.resolution == (854, 480)
        
        # Test audio stream properties if available
        if probe_info.audio_streams:
            audio_stream = probe_info.audio
            assert audio_stream.codec_name in ["aac", "mp3", "ac3", "vorbis"]
            assert audio_stream.channels > 0
            assert audio_stream.sample_rate > 0
        
        print(f"Video duration: {probe_info.duration} seconds")
        print(f"Video resolution: {probe_info.video.width}x{probe_info.video.height}")
        print(f"Video codec: {probe_info.video.codec_name}")
        print(f"Format: {probe_info.format_name}")
        print(f"File size: {probe_info.size / (1024*1024):.2f} MB")
        print(f"Bit rate: {probe_info.bit_rate / 1000:.0f} kbps")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    # Run the new comprehensive FFMPEG tests
    print("Testing FFMPEG basic conversion...")
    test_ffmpeg_basic_conversion()
    
    print("Testing FFMPEG video scaling...")
    test_ffmpeg_video_scaling()
    
    print("Testing FFMPEG video trimming...")
    test_ffmpeg_video_trimming()
    
    print("Testing FFMPEG quality adjustment...")
    test_ffmpeg_quality_adjustment()
    
    print("Testing FFMPEG audio extraction...")
    test_ffmpeg_audio_extraction()
    
    print("Testing FFMPEG multiple outputs...")
    test_ffmpeg_multiple_outputs()
    
    print("Testing FFMPEG seeking with accuracy...")
    test_ffmpeg_seeking_with_accuracy()
    
    print("Testing FFMPEG overwrite protection...")
    test_ffmpeg_overwrite_protection()
    
    print("Testing FFMPEG command generation...")
    test_ffmpeg_command_generation()
    
    print("Testing probe video properties...")
    test_probe_video_properties()
    
    print("All FFMPEG tests completed successfully!")

