from __future__ import annotations

import sys
import dataclasses
import typing
#import pathlib
from pathlib import Path
import tqdm

import datetime

import mediatools.util

from .probe_info import ProbeInfo, NoDurationError
from .video_info import VideoInfo
from .errors import VideoFileDoesNotExistError
from .ffmpeg import FFMPEG, FFMPEGResult



@dataclasses.dataclass(repr=False)
class VideoFile:
    '''Represents a video file.'''
    fpath: Path
    
    @classmethod
    def from_path(cls,
        fpath: str | Path,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and (not fp.exists() or not fp.is_file()):
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(fp)

    def get_info(self) -> VideoInfo:
        '''Get the video information for this video file.'''
        return VideoInfo.from_video_file(self, do_check=True)


    ######################## dunder Methods ########################
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.fpath}")'
    
    ######################## File Methods ########################
    def exists(self) -> bool:
        return self.fpath.exists()

    ############################# Utility #############################
    def is_probable(self) -> bool:
        '''Returns True of video file is probe-able.'''
        try:
            self.probe()
        except Exception as e:
            return False
        else:
            return True

    def probe(self, check_for_errors: bool = False) -> ProbeInfo:
        '''Probe the file in question.'''
        return ProbeInfo.read_from_file(str(self.fpath))    

    ############################# file operations #############################
    def copy(self, new_fpath: Path, overwrite: bool = False) -> VideoFile:
        '''Copy the file to a new location.'''
        new_fpath = Path(new_fpath)
        if new_fpath.exists() and not overwrite:
            raise FileExistsError(f'The file {new_fpath} already exists. User overwrite=True to overwrite it.')
        new_fpath.write_bytes(self.fpath.read_bytes())
        return VideoFile.from_path(new_fpath)


@dataclasses.dataclass
class NewVideoResult:
    vf: VideoFile
    result: FFMPEGResult

    @classmethod
    def from_ffmpeg_result(cls, result: FFMPEGResult, check_exists: bool = False) -> NewVideoResult:
        '''Check that the file exists and return a NewVideoResult.'''
        fpath = Path(result.command.output_file)
        if check_exists and not fpath.exists():
            raise FileNotFoundError(f'The video file "{fpath}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return cls(vf=VideoFile.from_path(fpath), result=result)

@dataclasses.dataclass
class NewThumbResult:
    fp: Path
    result: FFMPEGResult


