# FFMPEG Class High-Quality Test Suite

This test suite provides comprehensive testing for the FFMPEG class using the `ffinput()` and `ffoutput()` convenience functions. The tests are designed to validate both command generation and actual video processing operations using probe-based assertions.

## Overview

The test suite downloads a test video (Big Buck Bunny 480p) and validates various FFMPEG operations:

1. **Video Probe Properties** - Tests the probe functionality for detailed video analysis
2. **Command Generation** - Validates that correct FFmpeg commands are generated
3. **Basic Video Conversion** - Tests format conversion with codec changes
4. **Video Scaling** - Tests resolution changes with aspect ratio preservation
5. **Video Trimming** - Tests temporal editing operations
6. **Quality Adjustment** - Tests CRF-based compression
7. **Audio Extraction** - Tests audio-only output generation
8. **Multiple Outputs** - Tests creating multiple files with different settings
9. **Seeking with Accuracy** - Tests precise temporal seeking
10. **Overwrite Protection** - Tests file overwrite handling

## Key Features

### Probe-Based Validation
All tests use the `probe()` function to validate:
- Video resolution (width/height)
- Duration accuracy
- Codec information
- File format verification
- Stream properties (video/audio)
- File size comparisons

### Real Video Processing
- Downloads Big Buck Bunny test video (596 seconds, 854x480, ~210MB)
- Tests actual FFmpeg operations, not just mocks
- Validates output files exist and have correct properties
- Cleans up temporary files after each test

### Comprehensive Parameter Testing
Tests cover all major FFmpeg parameters:
- **Input options**: `ss` (seek start), `t` (duration), input codecs
- **Output options**: `c_v` (video codec), `c_a` (audio codec), `crf`, `preset`
- **Filters**: `v_f` (video filters) for scaling, cropping
- **Stream control**: `vn` (no video), `an` (no audio)
- **Global options**: `y` (overwrite), `loglevel`, `hide_banner`

## Test Examples

### Basic Conversion Test
```python
cmd = FFMPEG(
    inputs=[ffinput(video_path)],
    outputs=[ffoutput(output_path, c_v="libx264", c_a="aac", y=True)]
)
cmd.run()

# Validate with probe
output_probe = probe(output_path)
assert output_probe.video.codec_name == "h264"
assert "mp4" in output_probe.format_name
```

### Video Scaling Test
```python
cmd = FFMPEG(
    inputs=[ffinput(video_path)],
    outputs=[ffoutput(output_path, v_f="scale=1280:720", c_v="libx264", y=True)]
)
cmd.run()

# Validate resolution
output_probe = probe(output_path)
assert output_probe.video.width == 1280
assert output_probe.video.height == 720
```

### Command Generation Test
```python
cmd = FFMPEG(
    inputs=[ffinput(video_path, ss="10", t="5")],
    outputs=[ffoutput(output_path, c_v="libx264", crf=23, v_f="scale=640:360", y=True)]
)

command_str = ' '.join(cmd.build_command())
assert "-ss 10" in command_str
assert "-t 5" in command_str
assert "-c:v libx264" in command_str
assert "-vf scale=640:360" in command_str
```

## Running the Tests

### Basic Test (No FFmpeg Required)
Tests command generation and probe functionality:
```bash
python run_ffmpeg_tests.py
```

### Full Test Suite (FFmpeg Required)
Edit `run_ffmpeg_tests.py` to uncomment the FFmpeg execution tests:
```python
tests = [
    (test_probe_video_properties, "Video Probe Properties"),
    (test_ffmpeg_command_generation, "Command Generation"),
    (test_ffmpeg_basic_conversion, "Basic Video Conversion"),
    (test_ffmpeg_video_scaling, "Video Scaling"),
    # ... all other tests
]
```

### Individual Test
```bash
python -c "
import sys; sys.path.append('./src')
from tests.test_ffmpeg_tools import test_ffmpeg_basic_conversion
test_ffmpeg_basic_conversion()
"
```

## Test Dependencies

- **Python packages**: `requests`, `tqdm` (auto-installed)
- **For probe tests**: No FFmpeg binary needed
- **For execution tests**: FFmpeg binary in PATH
- **Test video**: Downloads automatically (~210MB)

## Validation Strategy

Each test follows this pattern:
1. **Setup**: Download test video, create temp directories
2. **Execute**: Run FFMPEG command with specific parameters
3. **Validate**: Use probe() to verify output properties
4. **Assert**: Check resolution, duration, codecs, file existence
5. **Cleanup**: Remove temporary files

## Error Handling

Tests include proper error handling:
- Temporary directory cleanup in finally blocks
- Assertion failures with descriptive messages
- Probe validation for missing streams/properties
- File existence and size validations

## Benefits

This test suite provides:
- **Confidence**: Real video processing validation
- **Coverage**: All major FFmpeg operations tested
- **Reliability**: Probe-based assertions for accurate validation
- **Maintainability**: Clean test structure with shared utilities
- **Documentation**: Tests serve as usage examples

The tests demonstrate that the `ffinput()` and `ffoutput()` convenience functions successfully wrap all FFmpeg functionality while maintaining type safety and parameter validation.