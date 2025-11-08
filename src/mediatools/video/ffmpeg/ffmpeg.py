from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
from pathlib import Path

from .errors import (
    FFMPEGError, 
    FFMPEGCommandTimeoutError, 
    FFMPEGExecutionError, 
    FFMPEGNotFoundError, 
    OutputFileIsEmptyError,
)

VideoStream: typing.TypeAlias = str
AudioStream: typing.TypeAlias = str
Stream: typing.TypeAlias = VideoStream | AudioStream
Duration: typing.TypeAlias = str
Time: typing.TypeAlias = str


LOGLEVEL_OPTIONS = typing.Literal['error', 'warning', 'info', 'quiet', 'panic']






@dataclasses.dataclass
class FFMPEG:
    """A dataclass for building and executing FFmpeg commands with type safety and structured configuration.
    
    This class provides a high-level interface for constructing FFmpeg commands using
    FFInput and FFOutput specifications. It handles command building, validation, and
    execution with proper error handling.
    
    Args:
        inputs: List of FFInput objects specifying input files and their options.
        outputs: List of FFOutput objects specifying output files and encoding parameters.
        filter_complex: Complex filter graph for advanced multi-input/output operations.
        loglevel: FFmpeg logging level ('error', 'warning', 'info', 'quiet', 'panic').
        hide_banner: Whether to hide the FFmpeg banner (default: True).
        nostats: Whether to disable statistics output (default: True).
        progress: File path for writing progress reports.
        other_args: Additional command arguments as (name, value) tuples.
        other_flags: Additional command flags as strings.
    
    Examples:
        Basic video compression:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("input.mp4")],
            ...     outputs=[FFOutput("output.mp4", vcodec="libx264", crf=23, overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Extract a video clip:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("movie.mp4", ss="00:01:30", t="00:00:10")],
            ...     outputs=[FFOutput("clip.mp4", overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Create a thumbnail at specific time:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("video.mp4")],
            ...     outputs=[FFOutput("thumb.jpg", ss="00:00:05", vframes=1, overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Resize video with aspect ratio preservation:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("input.mp4")],
            ...     outputs=[FFOutput("resized.mp4", vf="scale=1280:720:force_original_aspect_ratio=decrease", overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Convert to animated GIF with speed adjustment:
            >>> from .probe import probe
            >>> duration = probe("video.mp4").duration
            >>> target_duration = 10  # seconds
            >>> pts_factor = duration / target_duration
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("video.mp4")],
            ...     outputs=[FFOutput("animation.gif", 
            ...                      vf=f"setpts=PTS/{pts_factor},fps=10,scale=500:-1:flags=lanczos",
            ...                      overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Crop video to specific region:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("input.mp4")],
            ...     outputs=[FFOutput("cropped.mp4", vf="crop=640:480:100:50", overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Extract audio track:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("video.mp4")],
            ...     outputs=[FFOutput("audio.mp3", disable_video=True, acodec="libmp3lame", overwrite=True)]
            ... )
            >>> result = cmd.run()
        
        Concatenate multiple videos:
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("video1.mp4"), FFInput("video2.mp4"), FFInput("video3.mp4")],
            ...     outputs=[FFOutput("combined.mp4", overwrite=True)],
            ...     filter_complex="[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[outv][outa]",
            ... )
            >>> # Note: outputs should map the filter outputs
            >>> cmd.outputs[0].maps = ["[outv]", "[outa]"]
            >>> result = cmd.run()
        
        Apply hardware acceleration (NVIDIA):
            >>> cmd = FFMPEG(
            ...     inputs=[FFInput("input.mp4", hwaccel="cuda")],
            ...     outputs=[FFOutput("output.mp4", vcodec="h264_nvenc", preset="fast", overwrite=True)]
            ... )
            >>> result = cmd.run()
    
    Returns:
        FFMPEGResult: Container with the executed command, subprocess result, and convenience properties.
    
    Raises:
        FileExistsError: When output files exist and overwrite=False.
        FFMPEGExecutionError: When FFmpeg command fails during execution.
        FFMPEGCommandTimeoutError: When command exceeds specified timeout.
        FFMPEGNotFoundError: When FFmpeg executable is not found in PATH.
    """
    inputs: list[FFInput]
    outputs: list[FFOutput]

    # Global command options
    filter_complex: str|list[str]|None = dataclasses.field(default=None, metadata={'desc': 'Complex filter graph'})
    loglevel: LOGLEVEL_OPTIONS|None = dataclasses.field(default=None, metadata={"arg": "loglevel", 'desc': 'Set logging level'})
    hide_banner: bool = dataclasses.field(default=True, metadata={"flag": "hide_banner", 'desc': 'Hide banner'})
    nostats: bool = dataclasses.field(default=True, metadata={"flag": "nostats", 'desc': 'Disable stats'})
    progress: str|None = dataclasses.field(default=None, metadata={"arg": "progress", 'desc': 'Write progress report to file'})

    # Generic extensibility
    other_args: list[tuple[str,str]] = dataclasses.field(default_factory=list, metadata={'desc': 'Additional output arguments'})
    other_flags: list[str] = dataclasses.field(default_factory=list, metadata={'desc': 'Additional command flags'})

    def __post_init__(self):
        if isinstance(self.inputs, FFInput):
            self.inputs = [self.inputs]
        if isinstance(self.outputs, FFOutput):
            self.outputs = [self.outputs]

    def run(
        self,
        timeout: float|None = None,
        cwd: str|Path|None = None,
        env: str|Path|None = None,
    ) -> FFMPEGResult:
        '''Run the FFMPEG command with the provided parameters.'''
        # Check if any output files exist when overwrite is disabled
        for output in self.outputs:
            if not output.overwrite and Path(output.file).exists():
                raise FileExistsError(f'The output file {output.file} exists and overwrite=False.')
        
        result = FFMPEGResult(
            command=self, 
            result=run_ffmpeg_subprocess(self.build_command(), timeout=timeout, cwd=cwd, env=env)
        )

        for opath in result.output_files:
            if Path(opath).exists() and Path(opath).stat().st_size == 0: #if file does not exist, the output may not have been a path
                raise OutputFileIsEmptyError(f"FFMPEG command completed but output file is empty: {opath}")
            
        return result
    
    def get_command(self) -> str:
        '''Return the FFMPEG command as a string.'''
        cmd = self.build_command()
        return ' '.join(shlex.quote(arg) for arg in cmd)

    def build_command(self) -> list[str]:
        '''Build the FFMPEG command as a list of strings using FFInput and FFOutput specifications.'''
        args = CmdArgs()
        for input_spec in self.inputs:
            args.extend(input_spec.to_args())

        args.extend(CmdArgs.from_field_metadatas(self))
        
        # handle complex filters
        if self.filter_complex is not None:
            if isinstance(self.filter_complex, str):
                args.add_arg('filter_complex', self.filter_complex)
            else:
                args.add_arg('filter_complex', ';'.join(self.filter_complex))
        
        args.add_args(self.other_args)
        args.add_flags(self.other_flags)

        for output_spec in self.outputs:
            args.extend(output_spec.to_args())

        return CmdArgs(["ffmpeg"] + args)


@dataclasses.dataclass
class FFInput:
    """Dataclass representing FFmpeg input specifications with comprehensive options.
    
    This class encapsulates all input-related FFmpeg options including file paths, codecs,
    timing, hardware acceleration, and format-specific settings. Each parameter corresponds
    directly to FFmpeg command-line arguments.
    
    Args:
        file: Input file path or URL.
        f: Input format override (FFmpeg: `-f`).
        t: Input duration limit in seconds or time format (FFmpeg: `-t`).
        ss: Input start time/seek position (FFmpeg: `-ss`).
        to: Input end time (FFmpeg: `-to`).
        itsoffset: Input timestamp offset in seconds (FFmpeg: `-itsoffset`).
        cv: Video codec for input decoding (FFmpeg: `-c:v`).
        ca: Audio codec for input decoding (FFmpeg: `-c:a`).
        
        # Video Input Options
        r: Input frame rate override (FFmpeg: `-r`).
        s: Input frame size as 'WxH' format (FFmpeg: `-s`).
        pix_fmt: Input pixel format (FFmpeg: `-pix_fmt`).
        aspect: Input aspect ratio override (FFmpeg: `-aspect`).
        vframes: Maximum number of video frames to read (FFmpeg: `-vframes`).
        top: Top field first flag for interlaced content (FFmpeg: `-top`).
        
        # Audio Input Options
        ar: Audio sample rate in Hz (FFmpeg: `-ar`).
        ac: Number of audio channels (FFmpeg: `-ac`).
        aframes: Maximum number of audio frames to read (FFmpeg: `-aframes`).
        vol: Audio volume adjustment, deprecated (FFmpeg: `-vol`).
        
        # Hardware Acceleration
        hwaccel: Hardware acceleration method like 'cuda', 'vaapi', 'qsv' (FFmpeg: `-hwaccel`).
        hwaccel_device: Specific hardware device to use (FFmpeg: `-hwaccel_device`).
        
        # Stream Selection
        map_metadata: Metadata mapping specification (FFmpeg: `-map_metadata`).
        map_chapters: Chapter mapping specification (FFmpeg: `-map_chapters`).
        
        # Input Format Specific
        probesize: Buffer size for format detection in bytes (FFmpeg: `-probesize`).
        analyzeduration: Analysis duration in microseconds (FFmpeg: `-analyzeduration`).
        fpsprobesize: Number of frames to probe for fps detection (FFmpeg: `-fpsprobesize`).
        safe: Enable safe file access for concat demuxer (FFmpeg: `-safe`).
        
        # Loop & Repeat
        loop: Loop input file, useful for images (FFmpeg: `-loop`).
        stream_loop: Loop input streams specified number of times (FFmpeg: `-stream_loop`).
        
        # Seeking & Timing
        accurate_seek: Enable accurate seeking at cost of speed (FFmpeg: `-accurate_seek`).
        seek_timestamp: Seek by timestamp instead of frame number (FFmpeg: `-seek_timestamp`).
        
        # Extensibility
        other_args: Additional input arguments as (name, value) tuples.
        other_flags: Additional input flags as strings.
    
    Examples:
        Basic input file:
            >>> input_spec = FFInput("video.mp4")
        
        Seek to specific time and duration:
            >>> input_spec = FFInput("movie.mp4", ss="00:01:30", t="00:00:10")
        
        Hardware accelerated input:
            >>> input_spec = FFInput("video.mp4", hwaccel="cuda")
        
        Image sequence with frame rate:
            >>> input_spec = FFInput("frame_%03d.jpg", r="25", f="image2")
        
        Loop image input:
            >>> input_spec = FFInput("background.jpg", loop=1, t="10")
    """
    file: str|Path
    f: str|None = dataclasses.field(default=None, metadata={"arg": "f", 'desc': 'Input format'})
    t: str|None = dataclasses.field(default=None, metadata={"arg": "t", 'desc': 'Input duration'})
    ss: str|None = dataclasses.field(default=None, metadata={"arg": "ss", 'desc': 'Input start time'})
    to: str|None = dataclasses.field(default=None, metadata={"arg": "to", 'desc': 'Input end time'})
    itsoffset: str|None = dataclasses.field(default=None, metadata={"arg": "itsoffset", 'desc': 'Input timestamp offset'})
    cv: str|None = dataclasses.field(default=None, metadata={"arg": "c:v", 'desc': 'Video codec'})
    ca: str|None = dataclasses.field(default=None, metadata={"arg": "c:a", 'desc': 'Audio codec'})

    # Video Input Options
    r: Time|None = dataclasses.field(default=None, metadata={"arg": "r", 'desc': 'Input frame rate'})
    s: str|None = dataclasses.field(default=None, metadata={"arg": "s", 'desc': 'Input frame size (WxH)'})
    pix_fmt: str|None = dataclasses.field(default=None, metadata={"arg": "pix_fmt", 'desc': 'Input pixel format'})
    aspect: str|None = dataclasses.field(default=None, metadata={"arg": "aspect", 'desc': 'Input aspect ratio'})
    vframes: int|None = dataclasses.field(default=None, metadata={"arg": "vframes", 'desc': 'Number of video frames to read'})
    top: int|None = dataclasses.field(default=None, metadata={"arg": "top", 'desc': 'Top field first'})

    # Audio Input Options
    ar: str|None = dataclasses.field(default=None, metadata={"arg": "ar", 'desc': 'Audio sample rate'})
    ac: int|None = dataclasses.field(default=None, metadata={"arg": "ac", 'desc': 'Audio channels'})
    aframes: int|None = dataclasses.field(default=None, metadata={"arg": "aframes", 'desc': 'Number of audio frames to read'})
    vol: str|None = dataclasses.field(default=None, metadata={"arg": "vol", 'desc': 'Audio volume (deprecated)'})

    # Hardware Acceleration (Input)
    hwaccel: str|None = dataclasses.field(default=None, metadata={"arg": "hwaccel", 'desc': 'Hardware acceleration method (cuda, vaapi, etc.)'})
    hwaccel_device: str|None = dataclasses.field(default=None, metadata={"arg": "hwaccel_device", 'desc': 'Hardware acceleration device'})

    # Stream Selection
    map_metadata: str|None = dataclasses.field(default=None, metadata={"arg": "map_metadata", 'desc': 'Map metadata'})
    map_chapters: str|None = dataclasses.field(default=None, metadata={"arg": "map_chapters", 'desc': 'Map chapters'})

    # Input Format Specific
    probesize: int|None = dataclasses.field(default=None, metadata={"arg": "probesize", 'desc': 'Probe size for format detection'})
    analyzeduration: int|None = dataclasses.field(default=None, metadata={"arg": "analyzeduration", 'desc': 'Analysis duration in microseconds'})
    fpsprobesize: int|None = dataclasses.field(default=None, metadata={"arg": "fpsprobesize", 'desc': 'Frames to probe for fps'})
    safe: int|None = dataclasses.field(default=None, metadata={"arg": "safe", 'desc': 'Safe file access (for concat demuxer)'})

    # Loop & Repeat
    loop: int|None = dataclasses.field(default=None, metadata={"arg": "loop", 'desc': 'Loop input (images/video)'})
    stream_loop: int|None = dataclasses.field(default=None, metadata={"arg": "stream_loop", 'desc': 'Loop input streams'})

    # Seeking & Timing
    accurate_seek: bool|None = dataclasses.field(default=None, metadata={"flag": "accurate_seek", 'desc': 'Enable accurate seeking'})
    seek_timestamp: bool|None = dataclasses.field(default=None, metadata={"flag": "seek_timestamp", 'desc': 'Seek by timestamp instead of frame'})

    # Generic extensibility
    other_args: list[tuple[str,str]] = dataclasses.field(default_factory=list)  # Additional output arguments
    other_flags: list[str] = dataclasses.field(default_factory=list)  # Additional command flags

    def to_args(self) -> CmdArgs:
        '''Convert the FFInput to a string representation for FFMPEG command.'''

        cmd = CmdArgs.from_field_metadatas(self)
        cmd.add_args(self.other_args)
        cmd.add_flags(self.other_flags)
        cmd.add_arg('i', str(self.file))

        return cmd


@dataclasses.dataclass
class FFOutput:
    """Dataclass representing FFmpeg output specifications with comprehensive encoding options.
    
    This class encapsulates all output-related FFmpeg options including file paths, codecs,
    quality settings, filters, and format specifications. Each parameter corresponds directly
    to FFmpeg command-line arguments for precise control over output encoding.
    
    Args:
        file: Output file path.
        overwrite: Overwrite output file if it exists (FFmpeg: `-y`).
        
        # Stream Selection & Mapping
        maps: List of stream mapping specifications like '0:v:0' (FFmpeg: `-map`).
        map_metadata: Metadata mapping from input (FFmpeg: `-map_metadata`).
        map_chapters: Chapter mapping from input (FFmpeg: `-map_chapters`).
        
        # Timing & Seeking
        ss: Start time offset for output (FFmpeg: `-ss`).
        t: Output duration, alias for duration (FFmpeg: `-t`).
        duration: Output duration in seconds or time format (FFmpeg: `-duration`).
        to: End time for output (FFmpeg: `-to`).
        
        # Video Output Options
        vcodec: Video codec like 'libx264', 'libx265' (FFmpeg: `-c:v`).
        video_bitrate: Video bitrate like '1000k', '2M' (FFmpeg: `-b:v`).
        crf: Constant rate factor for quality-based encoding 0-51 (FFmpeg: `-crf`).
        qscale_v: Video quality scale, lower is better (FFmpeg: `-q:v`).
        maxrate: Maximum bitrate for rate control (FFmpeg: `-maxrate`).
        bufsize: Buffer size for rate control (FFmpeg: `-bufsize`).
        framerate: Output frame rate (FFmpeg: `-r`).
        fps: Alternative frame rate specification (FFmpeg: `-fps`).
        s: Output frame size as 'WxH' format (FFmpeg: `-s`).
        aspect: Output aspect ratio (FFmpeg: `-aspect`).
        pix_fmt: Output pixel format like 'yuv420p' (FFmpeg: `-pix_fmt`).
        vframes: Number of video frames to output (FFmpeg: `-vframes`).
        keyint_min: Minimum GOP size (FFmpeg: `-keyint_min`).
        g: GOP size, keyframe interval (FFmpeg: `-g`).
        bf: Number of B-frames (FFmpeg: `-bf`).
        profile_v: Video profile like 'main', 'high' (FFmpeg: `-profile:v`).
        level: Video level specification (FFmpeg: `-level`).
        tune: Encoding tune like 'film', 'animation' (FFmpeg: `-tune`).
        
        # Audio Output Options
        acodec: Audio codec like 'aac', 'libmp3lame' (FFmpeg: `-c:a`).
        audio_bitrate: Audio bitrate like '128k', '320k' (FFmpeg: `-b:a`).
        ar: Audio sample rate in Hz (FFmpeg: `-ar`).
        ac: Number of audio channels (FFmpeg: `-ac`).
        vol: Audio volume adjustment (FFmpeg: `-vol`).
        aframes: Number of audio frames to output (FFmpeg: `-aframes`).
        profile_a: Audio profile specification (FFmpeg: `-profile:a`).
        qscale_a: Audio quality scale (FFmpeg: `-q:a`).
        
        # Filters
        vf: Video filter chain like 'scale=1280:720' (FFmpeg: `-vf`).
        af: Audio filter chain like 'volume=0.5' (FFmpeg: `-af`).
        filter_complex: Complex filter graph for multi-input operations (FFmpeg: `-filter_complex`).
        
        # Format & Container Options
        format: Output format like 'mp4', 'avi', 'gif' (FFmpeg: `-f`).
        movflags: MOV/MP4 specific flags like 'faststart' (FFmpeg: `-movflags`).
        brand: Brand for MP4 container (FFmpeg: `-brand`).
        
        # Hardware Acceleration
        hwaccel: Hardware acceleration method (FFmpeg: `-hwaccel`).
        hwaccel_output_format: Hardware accelerated output format (FFmpeg: `-hwaccel_output_format`).
        vaapi_device: VAAPI device specification (FFmpeg: `-vaapi_device`).
        
        # Encoding Presets & Quality
        preset: Encoding preset like 'ultrafast', 'medium', 'slow' (FFmpeg: `-preset`).
        x264_params: x264-specific parameters (FFmpeg: `-x264_params`).
        x265_params: x265-specific parameters (FFmpeg: `-x265_params`).
        
        # Stream Control
        disable_audio: Disable audio streams (FFmpeg: `-an`).
        disable_video: Disable video streams (FFmpeg: `-vn`).
        disable_subtitles: Disable subtitle streams (FFmpeg: `-sn`).
        disable_data: Disable data streams (FFmpeg: `-dn`).
        
        # Metadata
        metadata: Metadata key-value pairs for output file (FFmpeg: `-metadata`).
        
        # Subtitles
        scodec: Subtitle codec (FFmpeg: `-c:s`).
        
        # Threading & Performance
        threads: Number of encoding threads (FFmpeg: `-threads`).
        
        # Extensibility
        other_args: Additional output arguments as (name, value) tuples.
        other_flags: Additional output flags as strings.
    
    Examples:
        Basic video compression:
            >>> output = FFOutput("compressed.mp4", vcodec="libx264", crf=23, overwrite=True)
        
        High quality with specific bitrate:
            >>> output = FFOutput("output.mp4", vcodec="libx264", video_bitrate="5M", 
            ...                   acodec="aac", audio_bitrate="128k", overwrite=True)
        
        Resize and convert to GIF:
            >>> output = FFOutput("animation.gif", vf="scale=500:-1,fps=10", overwrite=True)
        
        Extract audio only:
            >>> output = FFOutput("audio.mp3", disable_video=True, acodec="libmp3lame", overwrite=True)
        
        Hardware accelerated encoding:
            >>> output = FFOutput("output.mp4", vcodec="h264_nvenc", preset="fast", 
            ...                   crf=20, overwrite=True)
        
        Custom metadata:
            >>> output = FFOutput("video.mp4", vcodec="libx264", 
            ...                   metadata={"title": "My Video", "artist": "Author"}, overwrite=True)
    """
    file: str|Path
    overwrite: bool = dataclasses.field(default=False, metadata={"flag": "y", "desc": 'Overwrite output file if it exists'})
    
    # Stream Selection & Mapping
    maps: list[Stream] = dataclasses.field(default_factory=list, metadata={"desc": 'Stream mapping specifications'})
    map_metadata: str|None = dataclasses.field(default=None, metadata={"arg": "map_metadata", "desc": "Map metadata from input"})
    map_chapters: str|None = dataclasses.field(default=None, metadata={"arg": "map_chapters", "desc": "Map chapters from input"})

    # Timing & Seeking
    ss: Time|None = dataclasses.field(default=None, metadata={"arg": "ss", "desc": "Start time offset"})
    t: Time|None = dataclasses.field(default=None, metadata={"arg": "t", "desc": "Duration (alias for duration)"})
    duration: Duration|None = dataclasses.field(default=None, metadata={"arg": "duration", "desc": "Duration"})
    to: Time|None = dataclasses.field(default=None, metadata={"arg": "to", "desc": "End time"})

    # Video Output Options
    vcodec: str|None = dataclasses.field(default=None, metadata={"arg": "c:v", "desc": "Video codec (c:v)"})
    video_bitrate: str|None = dataclasses.field(default=None, metadata={"arg": "b:v", "desc": "Video bitrate (b:v)"})
    crf: int|None = dataclasses.field(default=None, metadata={"arg": "crf", "desc": "Constant rate factor"})
    qscale_v: int|None = dataclasses.field(default=None, metadata={"arg": "q:v", "desc": "Video quality scale (q:v)"})
    maxrate: str|None = dataclasses.field(default=None, metadata={"arg": "maxrate", "desc": "Maximum bitrate"})
    bufsize: str|None = dataclasses.field(default=None, metadata={"arg": "bufsize", "desc": "Buffer size"})
    framerate: int|None = dataclasses.field(default=None, metadata={"arg": "r", "desc": "Output frame rate (r)"})
    fps: str|None = dataclasses.field(default=None, metadata={"arg": "fps", "desc": "Frame rate (alternative to framerate)"})
    s: str|None = dataclasses.field(default=None, metadata={"arg": "s", "desc": "Output frame size (WxH)"})
    aspect: str|None = dataclasses.field(default=None, metadata={"arg": "aspect", "desc": "Output aspect ratio"})
    pix_fmt: str|None = dataclasses.field(default=None, metadata={"arg": "pix_fmt", "desc": "Output pixel format"})
    vframes: int|None = dataclasses.field(default=None, metadata={"arg": "vframes", "desc": "Number of video frames to output"})
    keyint_min: int|None = dataclasses.field(default=None, metadata={"arg": "keyint_min", "desc": "Minimum GOP size"})
    g: int|None = dataclasses.field(default=None, metadata={"arg": "g", "desc": "GOP size"})
    bf: int|None = dataclasses.field(default=None, metadata={"arg": "bf", "desc": "B-frames"})
    profile_v: str|None = dataclasses.field(default=None, metadata={"arg": "profile:v", "desc": "Video profile"})
    level: str|None = dataclasses.field(default=None, metadata={"arg": "level", "desc": "Video level"})
    tune: str|None = dataclasses.field(default=None, metadata={"arg": "tune", "desc": "Encoding tune (film, animation, etc.)"})

    # Audio Output Options
    acodec: str|None = dataclasses.field(default=None, metadata={"arg": "c:a", "desc": "Audio codec (c:a)"})
    audio_bitrate: str|None = dataclasses.field(default=None, metadata={"arg": "b:a", "desc": "Audio bitrate (b:a)"})
    ar: str|None = dataclasses.field(default=None, metadata={"arg": "ar", "desc": "Audio sample rate"})
    ac: int|None = dataclasses.field(default=None, metadata={"arg": "ac", "desc": "Audio channels"})
    vol: str|None = dataclasses.field(default=None, metadata={"arg": "vol", "desc": "Audio volume"})
    aframes: int|None = dataclasses.field(default=None, metadata={"arg": "aframes", "desc": "Number of audio frames to output"})
    profile_a: str|None = dataclasses.field(default=None, metadata={"arg": "profile:a", "desc": "Audio profile"})
    qscale_a: int|None = dataclasses.field(default=None, metadata={"arg": "q:a", "desc": "Audio quality scale (q:a)"})

    # Filters
    vf: str|None = dataclasses.field(default=None, metadata={"arg": "vf", "desc": "Video filter chain"})
    af: str|None = dataclasses.field(default=None, metadata={"arg": "af", "desc": "Audio filter chain"})
    filter_complex: str|None = dataclasses.field(default=None, metadata={"arg": "filter_complex", "desc": "Complex filter graph"})

    # Format & Container Options
    format: str|None = dataclasses.field(default=None, metadata={"arg": "f", "desc": "Output format (f)"})
    movflags: str|None = dataclasses.field(default=None, metadata={"arg": "movflags", "desc": "MOV/MP4 specific flags"})
    brand: str|None = dataclasses.field(default=None, metadata={"arg": "brand", "desc": "Brand for MP4"})

    # Hardware Acceleration (Output)
    hwaccel: str|None = dataclasses.field(default=None, metadata={"arg": "hwaccel", "desc": "Hardware acceleration method"})
    hwaccel_output_format: str|None = dataclasses.field(default=None, metadata={"arg": "hwaccel_output_format", "desc": "Hardware accelerated output format"})
    vaapi_device: str|None = dataclasses.field(default=None, metadata={"arg": "vaapi_device", "desc": "VAAPI device"})

    # Encoding Presets & Quality
    preset: str|None = dataclasses.field(default=None, metadata={"arg": "preset", "desc": "Encoding preset (ultrafast, fast, medium, etc.)"})
    x264_params: str|None = dataclasses.field(default=None, metadata={"arg": "x264_params", "desc": "x264 specific parameters"})
    x265_params: str|None = dataclasses.field(default=None, metadata={"arg": "x265_params", "desc": "x265 specific parameters"})

    # Stream Control
    disable_audio: bool = dataclasses.field(default=False, metadata={"flag": "an", "desc": "Disable audio streams (an)"})
    disable_video: bool = dataclasses.field(default=False, metadata={"flag": "vn", "desc": "Disable video streams (vn)"})
    disable_subtitles: bool = dataclasses.field(default=False, metadata={"flag": "sn", "desc": "Disable subtitle streams (sn)"})
    disable_data: bool = dataclasses.field(default=False, metadata={"flag": "dn", "desc": "Disable data streams (dn)"})

    # Metadata
    metadata: dict[str, str] = dataclasses.field(default_factory=dict, metadata={"desc": "Metadata key-value pairs"})
    
    # Subtitles
    scodec: str|None = dataclasses.field(default=None, metadata={"arg": "c:s", "desc": "Subtitle codec (c:s)"})

    # Threading & Performance
    threads: int|None = dataclasses.field(default=None, metadata={"arg": "threads", "desc": "Number of threads"})

    # Generic extensibility
    other_args: list[tuple[str,str]] = dataclasses.field(default_factory=list, metadata={"desc": "Additional output arguments"})
    other_flags: list[str] = dataclasses.field(default_factory=list, metadata={"desc": "Additional command flags"})

    def to_args(self) -> list[str]:
        '''Convert the FFOutput to arguments for FFMPEG command.'''
        args = CmdArgs.from_field_metadatas(self)
        
        # Handle maps separately since it's a list
        for map_spec in self.maps:
            args.add_arg('map', map_spec)
        
        # Handle metadata separately since it needs special formatting
        for key, value in self.metadata.items():
            args.add_arg('metadata', f'{key}={value}')
        
        # Generic extensibility
        args.add_args(self.other_args)
        args.add_flags(self.other_flags)
        args.append(str(self.file))
        
        return args

def stream_filter(
    instreams: Stream|typing.Iterable[Stream], 
    outstreams: Stream|typing.Iterable[Stream], 
    filter_str: str|None, 
    **filter_args
) -> str:
    '''Build a filter_complex string for FFMPEG command. Each call is one filter link, so it will be used in sequence.
    Examples:
        stream_filter(['0:v'], ['scaled'], scale='640:480')
        stream_filter('0:a', 'normalized', 'loudnorm', I='-16', LRA='11', TP='-1.5')
    '''
    if isinstance(instreams, (str)):
        instreams = [instreams]
    if isinstance(outstreams, (str)):
        outstreams = [outstreams]
    
    in_labels = ''.join(f'[{s}]' for s in instreams) if len(instreams) > 0 else ''
    out_labels = ''.join(f'[{s}]' for s in outstreams) if len(outstreams) > 0 else ''
    filter_arg_str = ''.join(f':{k}={v}' for k,v in filter_args.items())
    if filter_str is not None:
        filter_arg_str = f'{filter_str}{filter_arg_str}'
    return f'{in_labels}{filter_arg_str}{out_labels}'



@dataclasses.dataclass(repr=False)
class FFMPEGResult:
    '''A class to represent the result of an FFMPEG command.
    Description: this is a container for both the subprocess.CompletedProcess and 
    the FFMPEG command that was run to generate it. You can access the command's
    output (stderrr), return code, etc. via this class.
    '''
    command: FFMPEG
    result: subprocess.CompletedProcess
    
    @property
    def output(self) -> str:
        '''Return progress and diagnostic output of the FFMPEG command (note: ffmpeg sends it to stdout).'''
        return self.result.stderr.strip()

    @property
    def stderr(self) -> str:
        '''Return progress and diagnostic output of the FFMPEG command (ffmpeg sends it to stdout).'''
        return self.result.stderr.strip()

    @property
    def stdout(self) -> str:
        '''Return stdout of the FFMPEG command. This is unliklely to be useful.'''
        return self.result.stdout.strip()

    @property
    def output_files(self) -> list[Path]:
        '''Return the output file paths of the FFMPEG command.'''
        return [Path(output.file) for output in self.command.outputs]
    
    @property
    def output_file(self) -> Path:
        '''Return the first output file path of the FFMPEG command (for backward compatibility).'''
        if self.command.outputs:
            return Path(self.command.outputs[0].file)
        raise ValueError("No output files specified in command.")

    @property
    def returncode(self) -> int:
        '''Return the return code of the FFMPEG command.'''
        return self.result.returncode
    
    def __str__(self) -> str:
        '''Return a string representation of the FFMPEGResult.'''
        return f"{self.__class__.__name__}(command={self.command.get_command()}, returncode={self.returncode}, output_length={len(self.result.stderr)})"


def run_ffmpeg_subprocess(
    cmd: list[str], 
    timeout: float|None = None, 
    cwd: str|Path|None = None, 
    env: str|Path|None = None
) -> subprocess.CompletedProcess:
    '''Run a subprocess with the given command and parameters.'''
    try:
        # Execute the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=True,
            #stdin=subprocess.DEVNULL, # not sure if I should hard-code this, but here we are.
        )
        
    except subprocess.CalledProcessError as e:
        error_msg = f"FFMPEG command failed: {' '.join(cmd)}"
        raise FFMPEGExecutionError.from_stdout_stderr(
            stdout=e.stdout,
            stderr=e.stderr,
            msg=f'{error_msg} - {e.stderr.strip() if e.stderr else "<no stderr output>"}'
        ) from e
        
    except subprocess.TimeoutExpired as e:
        raise FFMPEGCommandTimeoutError(f"FFMPEG command timed out after {timeout} seconds: {' '.join(cmd)}")
        
    except FileNotFoundError as e:
        raise FFMPEGNotFoundError("FFMPEG not found in PATH. Please ensure FFMPEG is installed and available.")

    return result



class CmdArgs(list[str]):
    '''Class to build command line arguments for FFMPEG.'''
    @classmethod
    def from_dict(cls, args: dict[str, str], flags: dict[str, bool]) -> typing.Self:
        '''Create CmdArgs from a dictionary of name-value pairs.'''
        cmd_args = cls()
        cmd_args.add_args(list(args.items()))
        cmd_args.add_flags([f for f,b in flags if b])
        return cmd_args

    def add_args(self, name_values: list[tuple[str, str|int|None]]):
        '''Add multiple arguments to the command.'''
        for name, value in name_values:
            if value is not None:
                self.extend([CmdArgs.add_dash(name), str(value)])

    def add_arg(self, name: str, value: str|int|None):
        '''Add an argument to the command.'''
        if value is not None:
            self.extend([CmdArgs.add_dash(name), str(value)])

    def add_flags(self, names: list[str]):
        '''Add multiple flags to the command.'''
        for name in names:
            self.append(CmdArgs.add_dash(name))

    def add_flag(self, name: str, enabled: bool = True):
        '''Add a flag to the command.'''
        if bool(enabled):
            self.append(CmdArgs.add_dash(name))

    @classmethod
    def add_dash(cls, name: str) -> str:
        '''Ensure the argument name starts with a dash.'''
        return name if name.startswith('-') else f'-{name}'

    @classmethod
    def from_annotated_types(cls, instance: typing.Type) -> typing.Self:
        '''Create CmdArgs from a dataclass with Annotated types.'''
        cmd_args = cls()
        for f in dataclasses.fields(instance):
            if typing.get_origin(f.type) is typing.Annotated:
                type_desc: str = typing.get_args(f.type)[1]
                value = getattr(instance, f.name)
                if value is not None:
                    if type_desc.startswith('arg='):
                        arg_name = type_desc.split('=',1)[1]
                        cmd_args.add_arg(arg_name, value)
                    elif type_desc.startswith('flag='):
                        flag_name = type_desc.split('=',1)[1]
                        cmd_args.add_flag(flag_name, value)
                    else:
                        raise NotImplementedError(f"Unsupported annotation type: {type_desc}. Check the class definition!")
        return cmd_args

    @classmethod
    def from_field_metadatas(cls, instance: typing.Type) -> typing.Self:
        '''Create CmdArgs from a dataclass with field metadata.'''
        cmd_args = cls()
        for f in dataclasses.fields(instance):
            if 'arg' in f.metadata and (value := getattr(instance, f.name)) is not None:
                cmd_args.add_arg(f.metadata['arg'], value)
            elif 'flag' in f.metadata and (value := getattr(instance, f.name)):
                cmd_args.add_flag(f.metadata['flag'], value)

        return cmd_args
