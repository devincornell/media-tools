
import typing
import datetime
import dataclasses
from pathlib import Path

import ffmpeg

from .errors import FFMPEGCommandError

if typing.TYPE_CHECKING:
    from .video_file import VideoFile


@dataclasses.dataclass
class NewVideoResult:
    fname: Path
    stdout: str

    @classmethod
    def check_file_exists(cls, fname: Path, stdout: str) -> 'NewVideoResult':
        '''Check that the file exists and return a NewVideoResult.'''
        fname = Path(fname)
        if not fname.exists():
            raise FileNotFoundError(f'The video file "{fname}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return cls(fname=fname, stdout=stdout)




@dataclasses.dataclass
class FFRunResult:
    '''Stores results of run instead of raising exception so that custom exceptions can be raised.'''
    stdout: str
    new_file: typing.Optional[Path]
