from __future__ import annotations

import sys
import dataclasses
import typing
#import pathlib
from pathlib import Path
import ffmpeg
import tqdm

import datetime

import mediatools.util

from .probe_info import ProbeInfo, NoDurationError
from .video_info import VideoInfo
from .errors import FFMPEGError, VideoFileDoesNotExistError




@dataclasses.dataclass(repr=False)
class VideoFile:
    '''Represents a video file.'''
    fpath: Path
    
    #def __post_init__(self):
    #    '''Make sure fpath is actually a path instead of just a string. DEPRICATED: USE from_path SFMC.'''
    #    #self.fpath = Path(self.fpath)
    #    if not isinstance(self.fpath, Path):
    #        raise TypeError(f'The provided path must be of type Path. Use '
    #            f'.from_path or another SFMC to automatically convert.')

    #@classmethod
    #def new(cls, fname: str, stdout: typing.Optional[typing.Tuple[bytes]] = None) -> typing.Self:
    #    return cls(
    #        fpath = Path(fname),
    #        #stdout = '\n'.join([s.decode() for s in stdout]) if stdout is not None else None,
    #        stdout = stdout,
    #    )

    def get_info(self) -> VideoInfo:
        '''Get the video information for this video file.'''
        return VideoInfo.from_video_file(self, do_check=True)

    #################################### for globbing ####################################

    @classmethod
    def from_path(cls,
        fpath: str | Path,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and (not fp.exists() or not fp.is_file()):
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(fp)

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
    
    ############################# method extensions #############################
    @property
    def ffmpeg(self) -> FFMPEGTools:
        return FFMPEGTools(vf=self)
    

    ############################# file operations #############################
    def copy(self, new_fpath: Path, overwrite: bool = False) -> VideoFile:
        '''Copy the file to a new location.'''
        new_fpath = Path(new_fpath)
        if new_fpath.exists() and not overwrite:
            raise FileExistsError(f'The file {new_fpath} already exists. User overwrite=True to overwrite it.')
        new_fpath.write_bytes(self.fpath.read_bytes())
        return VideoFile.from_path(new_fpath)



XCoord = int
YCoord = int
Height = int
Width = int


@dataclasses.dataclass
class FFMPEGTools:
    vf: VideoFile

    ######################## Video Manipulation Methods ########################
    def compress(self, 
        output_fname: Path, 
        vcodec: str = 'libx264', 
        crf: int = 30, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> NewVideoResult:
        '''Compress a video to the specified format and return a videofile of the output file.'''
        output_fname = Path(output_fname)

        if not overwrite and output_fname.exists():
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
        
        result = self.run(
            ffmpeg_command = (
                ffmpeg
                .input(str(self.vf.fpath))
                .output(str(output_fname), vcodec=vcodec, crf=crf, **output_kwargs)
            ),
            overwrite_output=overwrite,
        )

        return NewVideoResult.check_file_exists(fpath=output_fname, stdout=result)

    def splice(self, 
        output_fname: Path, 
        start_time: datetime.timedelta, 
        end_time: datetime.timedelta, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> NewVideoResult:
        '''Splice video given a start time and end time.'''
        output_fname = Path(output_fname)
        if output_fname.exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

        #duration = duration_sec if duration_sec is not None else (end_sec - start_sec)
        stdout = self.run(
            ffmpeg_command = (
                ffmpeg
                .input(self.vf.fpath, ss=start_time.total_seconds())
                .output(str(output_fname), t=(end_time-start_time).total_seconds(), **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        return NewVideoResult.check_file_exists(fpath=output_fname, stdout=stdout)

    def crop(self, 
        output_fname: Path, 
        topleft_point: typing.Tuple[XCoord, YCoord],
        size: typing.Tuple[Width,Height],
        overwrite: bool = False, 
        **output_kwargs
    ) -> NewVideoResult:
        '''Crop the video where the top-left of the frame is at 
        Args:
            topleft_point: (start_x,start_y)
            size: (width,height)
        '''
        output_fname = Path(output_fname)
        if output_fname.exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

        stdout = self.run(
            ffmpeg_command = (
                ffmpeg
                .input(str(self.vf.fpath))
                .crop(*topleft_point, *size)
                .output(str(output_fname), **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        return NewVideoResult.check_file_exists(fpath=output_fname, stdout=stdout)

    def make_thumb(self, 
        output_fname: str, 
        time_point: float = 0.5, 
        height: int = -1, 
        width: int = -1, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> NewThumbResult:
        '''Make a thumbnail from this video.
        Args:
            time_point is the proportion of the video at which to take the thumb (e.g. 0.5 means at half way through.)
        Notes:
            copied from here:
                https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
        '''
        ofp = Path(output_fname)
        if ofp.exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
        
        try:
            probe = self.vf.probe(check_for_errors=True)
            ss = int(probe.duration * time_point)
        except (TypeError, NoDurationError):
            ss = .01  # default to 1 second if duration is not available

        stdout = self.run(
            ffmpeg_command = (
                ffmpeg
                .input(self.vf.fpath, ss=ss)
                .filter('scale', width, height)
                .output(str(ofp), vframes=1, **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        return NewThumbResult(ofp, stdout)

    @staticmethod
    def run(ffmpeg_command, overwrite_output: bool) -> str:
        '''Run the provided ffmpeg command.'''
        if overwrite_output:
            ffmpeg_command = ffmpeg_command.overwrite_output()
        
        try:
            # actually execute the command
            stdout = ffmpeg_command.run(capture_stdout=True, capture_stderr=True)

        except ffmpeg.Error as e:
            raise FFMPEGError.from_ffmpeg_error(e, 
                f'There was an error executing the ffmpeg command: {ffmpeg_command}.') from e
        else:
            try:
                return '\n'.join([s.decode() for s in stdout])
            except Exception as e:
                return stdout



@dataclasses.dataclass
class NewVideoResult:
    vf: VideoFile
    stdout: str

    @classmethod
    def check_file_exists(cls, fpath: Path, stdout: str) -> NewVideoResult:
        '''Check that the file exists and return a NewVideoResult.'''
        fpath = Path(fpath)
        if not fpath.exists():
            raise FileNotFoundError(f'The video file "{fpath}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return cls(vf=VideoFile.from_path(fpath), stdout=stdout)

@dataclasses.dataclass
class NewThumbResult:
    fp: Path
    stdout: str

