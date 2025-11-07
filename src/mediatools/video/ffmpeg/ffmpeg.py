from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
from pathlib import Path

from .errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError

VideoStream: typing.TypeAlias = str
AudioStream: typing.TypeAlias = str
Stream: typing.TypeAlias = VideoStream | AudioStream
Duration: typing.TypeAlias = str
Time: typing.TypeAlias = str


LOGLEVEL_OPTIONS = typing.Literal['error', 'warning', 'info', 'quiet', 'panic']





def ffmpeg(
    input_files: list[str|Path],
    output_file: str|Path,
    overwrite_output: bool = False,
    ss: str|None = None,
    duration: str|None = None,
    vf: str|None = None,
    af: str|None = None,
    vcodec: str|None = None,
    acodec: str|None = None,
    video_bitrate: str|None = None,
    audio_bitrate: str|None = None,
    framerate: int|None = None,
    format: str|None = None,
    filter_complex: str|None = None,
    disable_audio: bool = False,
    disable_video: bool = False,
    crf: int|None = None,
    preset: str|None = None,
    hwaccel: str|None = None,
    loglevel: LOGLEVEL_OPTIONS|None = None,
    hide_banner: bool = True,
    nostats: bool = True,
    output_args: list[tuple[str,str]]|None = None,
    input_args: list[tuple[str,str]]|None = None,
    command_flags: list[str]|None = None,
) -> FFMPEGResult:
    '''Execute an ffmpeg command (legacy interface - creates simple FFInput/FFOutput internally).'''
    
    # Create FFInput objects for each input file
    inputs = []
    for input_file in input_files:
        # Extract input-specific args if provided
        input_spec = FFInput(file=input_file, hwaccel=hwaccel)
        if input_args:
            input_spec.other = [f"-{name}" if not str(name).startswith('-') else str(name) for name, value in input_args for item in [str(name), str(value)]]
        inputs.append(input_spec)
    
    # Create FFOutput object
    output_spec = FFOutput(
        file=output_file,
        overwrite=overwrite_output,
        ss=ss,
        duration=duration,
        vf=vf,
        af=af,
        vcodec=vcodec,
        acodec=acodec,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        framerate=framerate,
        format=format,
        filter_complex=filter_complex,
        disable_audio=disable_audio,
        disable_video=disable_video,
        crf=crf,
        preset=preset,
        output_args=output_args,
        command_flags=command_flags,
    )
    
    return FFMPEG(
        inputs=inputs,
        outputs=[output_spec],
        loglevel=loglevel,
        hide_banner=hide_banner,
        nostats=nostats,
    ).run()




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
        
        return FFMPEGResult(
            command=self, 
            result=run_ffmpeg_subprocess(self.build_command(), timeout=timeout, cwd=cwd, env=env)
        )
    
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
    '''Dataclass used to build an FFMPEG command.'''
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
    safe: bool|None = dataclasses.field(default=None, metadata={"flag": "safe", 'desc': 'Safe file access (for concat demuxer)'})

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
    '''Dataclass used to build an FFMPEG output specification.'''
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
