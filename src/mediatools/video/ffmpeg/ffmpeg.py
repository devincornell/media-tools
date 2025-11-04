from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
from pathlib import Path

from .errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError

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

    def to_str(self) -> str:
        '''Convert the FFInput to a string representation for FFMPEG command.'''
        parts = list()

        def add_part(argname: str, argval: str|int|None):
            if argval is not None:
                parts.extend([f'-{argname}', str(argval)])

        def add_flag(argname: str, add_flag: bool|None):
            if add_flag is True:
                parts.append(f'-{argname}')

        # Video Input Options
        add_part('r', self.r)
        add_part('s', self.s)
        add_part('pix_fmt', self.pix_fmt)
        add_part('aspect', self.aspect)
        add_part('vframes', self.vframes)
        add_part('top', self.top)
        
        # Audio Input Options
        add_part('ar', self.ar)
        add_part('ac', self.ac)
        add_part('aframes', self.aframes)
        add_part('vol', self.vol)
        
        # Hardware Acceleration (Input)
        add_part('hwaccel', self.hwaccel)
        add_part('hwaccel_device', self.hwaccel_device)
        
        # Stream Selection
        add_part('map', self.map)
        add_part('map_metadata', self.map_metadata)
        add_part('map_chapters', self.map_chapters)
        
        # Input Format Specific
        add_part('probesize', self.probesize)
        add_part('analyzeduration', self.analyzeduration)
        add_part('fpsprobesize', self.fpsprobesize)
        add_flag('safe', self.safe)
        
        # Loop & Repeat
        add_part('loop', self.loop)
        add_part('stream_loop', self.stream_loop)
        
        # Seeking & Timing
        add_flag('accurate_seek', self.accurate_seek)
        add_flag('seek_timestamp', self.seek_timestamp)
        
        # Existing attributes
        add_part('f', self.f)
        add_part('t', self.t)
        add_part('ss', self.ss)
        add_part('to', self.to)
        add_part('c:v', self.cv)
        add_part('c:a', self.ca)
        add_part('i', str(self.file))

        return parts
