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

from .probe_info import ProbeInfo
#from .result import FFRunResult

from .errors import FFMPEGCommandError#ProblemCompressingVideo, ProblemMakingThumb, ProblemSplicingVideo, ProblemCroppingVideo

def clean_stdout(out: str) -> str:
    return ' '.join(out.split('\n'))

DEFAULT_VIDEO_FILE_EXTENSIONS = ('mp4','mov','avi','mkv', 'webm', 'flv', 'ts')

class VideoFileDoesNotExistError(Exception):
    fpath: Path
    _msg_template: str = 'This video file does not exist: {fp}'

    @classmethod
    def from_fpath(cls, fpath: Path) -> typing.Self:
        o = cls(cls._msg_template.format(fp=str(fpath)))
        o.fpath = fpath
        return o

@dataclasses.dataclass(repr=False)
class VideoFile:
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


    #################################### for globbing ####################################
    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_VIDEO_FILE_EXTENSIONS,
        base_name_pattern: str = '*',
    ) -> typing.List[typing.Self]:
        '''Get sorted list of video files from a given directory recursively.
        Args:
            root: root path from which to search for videos.
            extensions: list of file extensions to search for.
            filter_invalid: include only video files that could be successfully probed.
        '''
        paths = mediatools.util.multi_extension_glob(
            glob_func=Path(root).rglob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return [cls(fp) for fp in paths]

    @classmethod
    def from_glob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_VIDEO_FILE_EXTENSIONS,
        base_name_pattern: str = '*',
    ) -> typing.List[typing.Self]:
        '''Get sorted list of video files from a given directory recursively.
        Args:
            root: root path from which to search for videos.
            extensions: list of file extensions to search for.
            filter_invalid: include only video files that could be successfully probed.
        '''
        paths = mediatools.util.multi_extension_glob(
            glob_func=Path(root).glob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return [cls(fp) for fp in paths]


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

    def probe(self) -> ProbeInfo:
        '''Probe the file in question.'''
        return ProbeInfo.read_from_file(str(self.fpath))
    
    ############################# method extensions #############################
    @property
    def ffmpeg(self) -> FFMPEGTools:
        return FFMPEGTools(vf=self)
    



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
        topleft_point: typing.Tuple[int,int],
        size: typing.Tuple[int,int],
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
    ) -> tuple[Path, str]:
        '''Make a thumbnail from this video.
        Args:
            time_point is the proportion of the video at which to take the thumb (e.g. 0.5 means at half way through.)
        Notes:
            copied from here:
                https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
        '''
        if Path(output_fname).exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
        
        probe = self.vf.probe()
        stdout = self.run(
            ffmpeg_command = (
                ffmpeg
                .input(self.vf.fpath, ss=int(probe.duration * time_point))
                .filter('scale', width, height)
                .output(output_fname, vframes=1, **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        return Path(output_fname), stdout

    @staticmethod
    def run(ffmpeg_command, overwrite_output: bool) -> str:
        '''Run the provided ffmpeg command.'''
        if overwrite_output:
            ffmpeg_command = ffmpeg_command.overwrite_output()
        
        try:
            # actually execute the command
            stdout = ffmpeg_command.run(capture_stdout=True, capture_stderr=True)

        except ffmpeg.Error as e:
            raise FFMPEGCommandError.from_stderr(e.stderr, 
                f'There was an error executing the ffmpeg command: {ffmpeg_command}.') from e
        else:
            return '\n'.join([s.decode() for s in stdout])
        