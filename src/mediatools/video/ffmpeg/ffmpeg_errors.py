from __future__ import annotations

import typing
from pathlib import Path
####################### FFMPEG Errors #######################

if typing.TYPE_CHECKING:
    import ffmpeg  # type: ignore[import]

class FFMPEGError(Exception):
    pass

class FFMPEGExecutionError(FFMPEGError):
    stdout: str
    stderr: str

    @classmethod
    def from_stderr(cls, stderr: str | bytes, msg: str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stderr string.'''
        return cls.from_stdout_stderr(stdout=None, stderr=stderr, msg=msg)
    
    @classmethod
    def from_stdout(cls, stderr: str | bytes, msg: str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stdout and stderr strings.'''
        return cls.from_stdout_stderr(stdout=None, stderr=stderr, msg=msg)
    
    @classmethod
    def from_ffmpeg_error(cls, error: ffmpeg.Error, msg: str|None=None) -> typing.Self:
        '''Create a FFMPEGError from an ffmpeg.Error.'''
        return cls.from_stdout_stderr(stdout=error.stdout, stderr=error.stderr, msg=msg)
    
    @classmethod
    def from_stdout_stderr(cls, stdout:str|bytes|None=None, stderr:str|bytes|None=None, msg:str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stdout and stderr strings.'''
        o = cls(msg)
        o.stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
        o.stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
        return o
    
    def clean_stdout(self) -> str:
        '''Clean the stdout string by removing newlines and extra spaces.'''
        if self.stdout is None:
            return ''
        return clean_stdout(self.stdout)
    
    def clean_stderr(self) -> str:
        '''Clean the stderr string by removing newlines and extra spaces.'''
        if self.stderr is None:
            return ''
        return clean_stdout(self.stderr)



class FFMPEGNotFoundError(FFMPEGError):
    pass


class FFMPEGCommandTimeoutError(FFMPEGError):
    pass


def clean_stdout(stdout: str) -> str:
    return ' '.join(stdout.split('\n')).strip()

