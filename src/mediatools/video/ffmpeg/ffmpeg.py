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
    '''Execute an ffmpeg command.'''
    return FFMPEG(
        input_files = input_files,
        output_file = output_file,
        overwrite_output = overwrite_output,
        ss = ss,
        duration = duration,
        vf = vf,
        af = af,
        vcodec = vcodec,
        acodec = acodec,
        video_bitrate = video_bitrate,
        audio_bitrate = audio_bitrate,
        framerate = framerate,
        format = format,
        filter_complex = filter_complex,
        disable_audio = disable_audio,
        disable_video = disable_video,
        crf = crf,
        preset = preset,
        hwaccel = hwaccel,
        loglevel = loglevel,
        hide_banner = hide_banner,
        nostats = nostats,
        output_args = output_args,
        input_args = input_args,
        command_flags = command_flags,
    ).run()

@dataclasses.dataclass
class FFMPEG:
    '''Dataclass used to build an FFMPEG command.'''
    input_files: list[str|Path]
    output_file: str|Path
    overwrite_output: bool = False
    ss: str|None = None
    duration: str|None = None
    vf: str|None = None
    af: str|None = None
    vcodec: str|None = None
    acodec: str|None = None
    video_bitrate: str|None = None
    audio_bitrate: str|None = None
    framerate: int|None = None
    format: str|None = None
    filter_complex: str|None = None
    disable_audio: bool = False
    disable_video: bool = False
    crf: int|None = None
    preset: str|None = None
    hwaccel: str|None = None
    loglevel: LOGLEVEL_OPTIONS|None = None
    hide_banner: bool = True
    nostats: bool = True
    output_args: list[tuple[str,str]]|None = None
    input_args: list[tuple[str,str]]|None = None
    command_flags: list[str]|None = None

    def __post_init__(self):
        self.input_files = [Path(f) for f in self.input_files]
        self.output_file = Path(self.output_file)

    def run(
        self,
        timeout: float|None = None,
        cwd: str|Path|None = None,
        env: str|Path|None = None,
    ) -> list[str]:
        '''Run the FFMPEG command with the provided parameters.'''
        if not self.overwrite_output and self.output_file.exists():
            raise FileExistsError(f'The output file {self.output_file} exists and overwrite_output=False.')
        return FFMPEGResult(
            command=self, 
            result=run_ffmpeg_subprocess(self.build_command(), timeout=timeout, cwd=cwd, env=env)
        )
    

    def get_command(self) -> str:
        '''Return the FFMPEG command as a string.'''
        cmd = self.build_command()
        return ' '.join(shlex.quote(arg) for arg in cmd)


    def build_command(self) -> list[str]:
        '''Build the FFMPEG command as a list of strings.'''

        cmd = ["ffmpeg"]
        
        cmd.extend([f'-{cf}' for cf in self.get_flags()] or [])

        for an,av in self.get_args():
            cmd.extend([str(an) if str(an).startswith('-') else f'-{an}', str(av)])

        cmd.append(str(self.output_file))

        return cmd


    def get_flags(self) -> list[str]:
        '''Get the command flags for the FFMPEG command.'''
        command_flags = list(self.command_flags) if self.command_flags is not None else []
        
        if self.overwrite_output:
            command_flags.append('y')
        if self.disable_audio:
            command_flags.append('an')
        if self.disable_video:
            command_flags.append('vn')
        if self.hide_banner:
            command_flags.append('hide_banner')
        if self.nostats:
            command_flags.append('nostats')
        
        return command_flags

    def get_args(self) -> list[tuple[str,str]]:
        '''Get the command arguments for the FFMPEG command.'''
        command_args = list()# if self.command_args is not None else dict()

        if self.hwaccel is not None:
            command_args.append(('hwaccel', self.hwaccel))

        if self.input_args is not None:
            for an,av in self.input_args:
                command_args.append((an,av))

        for input_file in self.input_files:
            command_args.append(('i', str(input_file)))

        arg_map = [
            ("vf", self.vf),
            ("af", self.af),
            ("ss", self.ss),
            ("t", self.duration),
            ('r', self.framerate),
            ("b:v", self.video_bitrate),
            ("b:a", self.audio_bitrate),
            ("c:v", self.vcodec),
            ("c:a", self.acodec),
            ('crf', self.crf),
            ('f', self.format),
            ('filter_complex', self.filter_complex),
            ('preset', self.preset),
            #('hwaccel', self.hwaccel),
            ('loglevel', self.loglevel),
        ]
        
        # Add non-None arguments to command_args
        #for an,av in arg_map:
        #    if av is not None:
        #        command_args.append((an, av))
        command_args.extend([(an,av) for an,av in arg_map if av is not None])
        if self.output_args is not None:
        #    command_args = {**command_args, **self.command_args}
            for an,av in self.output_args:
                command_args.append((an,av))
        return command_args



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

    #@property
    #def stderr(self) -> str:
    #    '''Return progress and diagnostic output of the FFMPEG command (ffmpeg sends it to stdout).'''
    #    return self.result.stderr.strip()

    #@property
    #def stdout(self) -> str:
    #    '''Return stdout of the FFMPEG command. This is unliklely to be useful.'''
    #    return self.result.stdout.strip()

    @property
    def output_file(self) -> Path:
        '''Return the output file path of the FFMPEG command.'''
        return Path(self.command.output_file)

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
    def from_dict(cls, args: dict[str, str], flags: dict[str, bool]) -> CmdArgs:
        '''Create CmdArgs from a dictionary of name-value pairs.'''
        cmd_args = cls()
        cmd_args.add_args(args)
        cmd_args.add_flags(flags)
        return cmd_args
    
    def add_args(self, name_values: dict[str, str|int|None]):
        '''Add multiple arguments to the command.'''
        for name, value in name_values.items():
            if value is not None:
                self.extend([f'-{name}', str(value)])
    def add_arg(self, name: str, value: str|int|None):
        '''Add an argument to the command.'''
        if value is not None:
            self.extend([f'-{name}', str(value)])
    def add_flags(self, name_flags: dict[str, bool]):
        '''Add multiple flags to the command.'''
        for name, enabled in name_flags.items():
            if bool(enabled):
                self.append(f'-{name}')
    def add_flag(self, name: str, enabled: bool):
        '''Add a flag to the command.'''
        if bool(enabled):
            self.append(f'-{name}')




@dataclasses.dataclass
class FFInput:
    '''Dataclass used to build an FFMPEG command.'''
    file: str|Path
    f: str|None = None
    cv: str|None = None
    ca: str|None = None
    t: str|None = None
    ss: str|None = None
    to: str|None = None
    itsoffset: str|None = None
    
    # Video Input Options
    r: str|None = None  # Input frame rate
    s: str|None = None  # Input frame size (WxH)
    pix_fmt: str|None = None  # Input pixel format
    aspect: str|None = None  # Input aspect ratio
    vframes: int|None = None  # Number of video frames to read
    top: int|None = None  # Top field first
    
    # Audio Input Options
    ar: str|None = None  # Audio sample rate
    ac: int|None = None  # Audio channels
    aframes: int|None = None  # Number of audio frames to read
    vol: str|None = None  # Audio volume (deprecated)
    
    # Hardware Acceleration (Input)
    hwaccel: str|None = None  # Hardware acceleration method (cuda, vaapi, etc.)
    hwaccel_device: str|None = None  # Hardware acceleration device
    
    # Stream Selection
    map: str|None = None  # Map input streams to output
    map_metadata: str|None = None  # Map metadata
    map_chapters: str|None = None  # Map chapters
    
    # Input Format Specific
    probesize: int|None = None  # Probe size for format detection
    analyzeduration: int|None = None  # Analysis duration in microseconds
    fpsprobesize: int|None = None  # Frames to probe for fps
    safe: bool|None = None  # Safe file access (for concat demuxer)
    
    # Loop & Repeat
    loop: int|None = None  # Loop input (images/video)
    stream_loop: int|None = None  # Loop input streams
    
    # Seeking & Timing
    accurate_seek: bool|None = None  # Enable accurate seeking
    seek_timestamp: bool|None = None  # Seek by timestamp instead of frame

    other: list[str]|None = None  # Other arbitrary input options

    def to_args(self) -> list[str]:
        '''Convert the FFInput to a string representation for FFMPEG command.'''

        args = CmdArgs.from_dict(
            args={
                # Video Input Options
                'r': self.r,
                's': self.s,
                'pix_fmt': self.pix_fmt,
                'aspect': self.aspect,
                'vframes': self.vframes,
                'top': self.top,
                
                # Audio Input Options
                'ar': self.ar,
                'ac': self.ac,
                'aframes': self.aframes,
                'vol': self.vol,
                
                # Hardware Acceleration (Input)
                'hwaccel': self.hwaccel,
                'hwaccel_device': self.hwaccel_device,
                
                # Input Format Specific
                'probesize': self.probesize,
                'analyzeduration': self.analyzeduration,
                'fpsprobesize': self.fpsprobesize,
                
                # Loop & Repeat
                'loop': self.loop,
                'stream_loop': self.stream_loop,
                
                # Existing attributes
                'f': self.f,
                't': self.t,
                'ss': self.ss,
                'to': self.to,
                'c:v': self.cv,
                'c:a': self.ca,
                'i': str(self.file),
            },
            flags={
                # Input Format Specific
                'safe': self.safe,
                
                # Seeking & Timing
                'accurate_seek': self.accurate_seek,
                'seek_timestamp': self.seek_timestamp,
            }
        )

        if self.other:
            args.extend(self.other)

        return args


@dataclasses.dataclass
class FFOutput:
    '''Dataclass used to build an FFMPEG output specification.'''
    file: str|Path
    overwrite_output: bool = False
    
    # Stream Selection & Mapping
    maps: list[Stream]|None = None  # Stream mapping specifications
    map_metadata: str|None = None  # Map metadata from input
    map_chapters: str|None = None  # Map chapters from input
    
    # Timing & Seeking
    ss: str|None = None  # Start time offset
    t: str|None = None  # Duration (alias for duration)
    duration: str|None = None  # Duration
    to: str|None = None  # End time
    
    # Video Output Options
    vcodec: str|None = None  # Video codec (c:v)
    video_bitrate: str|None = None  # Video bitrate (b:v)
    crf: int|None = None  # Constant rate factor
    qscale_v: int|None = None  # Video quality scale (q:v)
    maxrate: str|None = None  # Maximum bitrate
    bufsize: str|None = None  # Buffer size
    framerate: int|None = None  # Output frame rate (r)
    fps: str|None = None  # Frame rate (alternative to framerate)
    s: str|None = None  # Output frame size (WxH)
    aspect: str|None = None  # Output aspect ratio
    pix_fmt: str|None = None  # Output pixel format
    vframes: int|None = None  # Number of video frames to output
    keyint_min: int|None = None  # Minimum GOP size
    g: int|None = None  # GOP size
    bf: int|None = None  # B-frames
    profile_v: str|None = None  # Video profile
    level: str|None = None  # Video level
    tune: str|None = None  # Encoding tune (film, animation, etc.)
    
    # Audio Output Options  
    acodec: str|None = None  # Audio codec (c:a)
    audio_bitrate: str|None = None  # Audio bitrate (b:a)
    ar: str|None = None  # Audio sample rate
    ac: int|None = None  # Audio channels
    vol: str|None = None  # Audio volume
    aframes: int|None = None  # Number of audio frames to output
    profile_a: str|None = None  # Audio profile
    qscale_a: int|None = None  # Audio quality scale (q:a)
    
    # Filters
    vf: str|None = None  # Video filter chain
    af: str|None = None  # Audio filter chain
    filter_complex: str|None = None  # Complex filter graph
    
    # Format & Container Options
    format: str|None = None  # Output format (f)
    movflags: str|None = None  # MOV/MP4 specific flags
    brand: str|None = None  # Brand for MP4
    
    # Hardware Acceleration (Output)
    hwaccel: str|None = None  # Hardware acceleration method
    hwaccel_output_format: str|None = None  # Hardware accelerated output format
    vaapi_device: str|None = None  # VAAPI device
    
    # Encoding Presets & Quality
    preset: str|None = None  # Encoding preset (ultrafast, fast, medium, etc.)
    x264_params: str|None = None  # x264 specific parameters
    x265_params: str|None = None  # x265 specific parameters
    
    # Stream Control
    disable_audio: bool = False  # Disable audio streams (an)
    disable_video: bool = False  # Disable video streams (vn)
    disable_subtitles: bool = False  # Disable subtitle streams (sn)
    disable_data: bool = False  # Disable data streams (dn)
    
    # Metadata
    metadata: dict[str, str]|None = None  # Metadata key-value pairs
    
    # Subtitles
    scodec: str|None = None  # Subtitle codec (c:s)
    
    # Threading & Performance
    threads: int|None = None  # Number of threads
    
    # Logging & Output Control
    loglevel: LOGLEVEL_OPTIONS|None = None  # Log level
    hide_banner: bool = True  # Hide banner
    nostats: bool = True  # No stats output
    progress: str|None = None  # Progress output URL
    
    # Generic extensibility
    output_args: list[tuple[str,str]]|None = None  # Additional output arguments
    command_flags: list[str]|None = None  # Additional command flags
    other: list[str]|None = None  # Other arbitrary output options

    def to_args(self) -> list[str]:
        '''Convert the FFOutput to arguments for FFMPEG command.'''
        args = CmdArgs.from_dict(
            args={
                # Stream Selection & Mapping
                'map_metadata': self.map_metadata,
                'map_chapters': self.map_chapters,
                
                # Timing & Seeking
                'ss': self.ss,
                't': self.t or self.duration,
                'to': self.to,
                
                # Video Output Options
                'c:v': self.vcodec,
                'b:v': self.video_bitrate,
                'crf': self.crf,
                'q:v': self.qscale_v,
                'maxrate': self.maxrate,
                'bufsize': self.bufsize,
                'r': self.framerate or self.fps,
                's': self.s,
                'aspect': self.aspect,
                'pix_fmt': self.pix_fmt,
                'vframes': self.vframes,
                'keyint_min': self.keyint_min,
                'g': self.g,
                'bf': self.bf,
                'profile:v': self.profile_v,
                'level': self.level,
                'tune': self.tune,
                
                # Audio Output Options
                'c:a': self.acodec,
                'b:a': self.audio_bitrate,
                'ar': self.ar,
                'ac': self.ac,
                'vol': self.vol,
                'aframes': self.aframes,
                'profile:a': self.profile_a,
                'q:a': self.qscale_a,
                
                # Filters
                'vf': self.vf,
                'af': self.af,
                'filter_complex': self.filter_complex,
                
                # Format & Container Options
                'f': self.format,
                'movflags': self.movflags,
                'brand': self.brand,
                
                # Hardware Acceleration
                'hwaccel_output_format': self.hwaccel_output_format,
                'vaapi_device': self.vaapi_device,
                
                # Encoding Presets & Quality
                'preset': self.preset,
                'x264-params': self.x264_params,
                'x265-params': self.x265_params,
                
                # Subtitles
                'c:s': self.scodec,
                
                # Threading & Performance
                'threads': self.threads,
                
                # Logging & Output Control
                'loglevel': self.loglevel,
                'progress': self.progress,
            },
            flags={
                # Stream Control
                'an': self.disable_audio,
                'vn': self.disable_video,
                'sn': self.disable_subtitles,
                'dn': self.disable_data,
                
                # Logging & Output Control
                'hide_banner': self.hide_banner,
                'nostats': self.nostats,
            }
        )
        
        # Handle maps separately since it's a list
        if self.maps:
            for map_spec in self.maps:
                args.add_arg('map', map_spec)
        
        # Handle metadata separately since it needs special formatting
        if self.metadata:
            for key, value in self.metadata.items():
                args.add_arg('metadata', f'{key}={value}')
        
        # Generic extensibility
        if self.output_args:
            for arg_name, arg_value in self.output_args:
                args.add_arg(arg_name, arg_value)
        
        if self.command_flags:
            for flag in self.command_flags:
                args.add_flag(flag, True)
        
        if self.other:
            args.extend(self.other)
        
        # Output file
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

