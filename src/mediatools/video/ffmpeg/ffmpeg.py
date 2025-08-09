from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
from pathlib import Path

from .ffmpeg_errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError



@dataclasses.dataclass
class FFMPEG:
    '''A class to represent an FFMPEG command.'''
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
    loglevel: typing.Literal['error', 'warning', 'info', 'quiet', 'panic']|None = None
    hide_banner: bool = True
    nostats: bool = True
    
    command_args: dict[str,str]|None = None
    command_flags: list[str]|None = None

    def __post_init__(self):
        self.input_files = [str(f) for f in self.input_files]
        self.output_file = str(self.output_file)    

    def run(
        self,
        timeout: float|None = None,
        cwd: str|Path|None = None,
        env: str|Path|None = None,
    ) -> list[str]:
        '''Run the FFMPEG command with the provided parameters.'''
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

        for an,av in self.get_args().items():
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
        command_args = dict()# if self.command_args is not None else dict()

        if self.hwaccel is not None:
            command_args['hwaccel'] = self.hwaccel

        for input_file in self.input_files:
            command_args['i'] = str(input_file)

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
        for an,av in arg_map:
            if av is not None:
                command_args[an] = av
        #command_args.extend([(an,av) for an,av in arg_map if av is not None])
        if self.command_args is not None:
            command_args = {**command_args, **self.command_args}

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
            check=True
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

