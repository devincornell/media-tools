from __future__ import annotations

import sys
import dataclasses
import typing
import pathlib
import ffmpeg

from .errors import FFMPEGCommandError

@dataclasses.dataclass
class FFRunResult:
    '''Stores results of run instead of raising exception so that custom exceptions can be raised.'''
    stdout: str

    @classmethod
    def run(cls, ffmpeg_command, overwrite_output: bool, verbose: bool = True) -> typing.Self:
        '''Actually run the ffmpeg command provided.'''
        if overwrite_output:
            ffmpeg_command = ffmpeg_command.overwrite_output()
        
        try:
            # actually execute the command
            stdout = ffmpeg_command.run(capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            # raise a generic expression
            raise FFMPEGCommandError.from_stderr(e.stderr, f'There was an error executing the ffmpeg command: {ffmpeg_command}.') from e
        else:
            return cls('\n'.join([s.decode() for s in stdout]))

