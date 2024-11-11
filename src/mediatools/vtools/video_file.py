from __future__ import annotations

import sys
import dataclasses
import typing
import pathlib
import ffmpeg
import tqdm

import datetime

from .probe_info import ProbeInfo
from .result import FFRunResult

from .errors import FFMPEGCommandError#ProblemCompressingVideo, ProblemMakingThumb, ProblemSplicingVideo, ProblemCroppingVideo

def clean_stdout(out: str) -> str:
    return ' '.join(out.split('\n'))

DEFAULT_VIDEO_FILE_EXTENSIONS = ('mp4','mov','avi','mkv', 'webm', 'flv', 'ts')

class VideoFileDoesNotExistError(Exception):
    fpath: pathlib.Path
    _msg_template: str = 'This video file does not exist: {fp}'

    @classmethod
    def from_fpath(cls, fpath: pathlib.Path) -> typing.Self:
        o = cls(cls._msg_template.format(fp=str(fpath)))
        o.fpath = fpath
        return o

@dataclasses.dataclass(repr=False)
class VideoFile:
    fpath: pathlib.Path
    
    def __post_init__(self):
        '''Make sure fpath is actually a path instead of just a string. DEPRICATED: USE from_path SFMC.'''
        #self.fpath = pathlib.Path(self.fpath)
        if not isinstance(self.fpath, pathlib.Path):
            raise TypeError(f'The provided path must be of type pathlib.Path. Use '
                f'.from_path or another SFMC to automatically convert.')

    #@classmethod
    #def new(cls, fname: str, stdout: typing.Optional[typing.Tuple[bytes]] = None) -> typing.Self:
    #    return cls(
    #        fpath = pathlib.Path(fname),
    #        #stdout = '\n'.join([s.decode() for s in stdout]) if stdout is not None else None,
    #        stdout = stdout,
    #    )

    #################################### constructors ####################################
    @classmethod
    def from_path(cls,
        fpath: str | pathlib.Path,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = pathlib.Path(fpath)
        if check_exists and (not fp.exists() or not fp.is_file()):
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(fp)

    #################################### for globbing ####################################
    @classmethod
    def from_rglob(cls, 
        root: str | pathlib.Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_VIDEO_FILE_EXTENSIONS,
        filter_invalid: bool = False,
        verbose: bool = False,
    ) -> typing.List[typing.Self]:
        '''Get sorted list of video files from a given directory recursively.
        Args:
            root: root path from which to search for videos.
            extensions: list of file extensions to search for.
            filter_invalid: include only video files that could be successfully probed.
        '''
        return cls._multi_extension_glob(
            glob_func=pathlib.Path(root).rglob, 
            extensions=extensions, 
            filter_invalid=filter_invalid,
            verbose=verbose,
        )
    
    @classmethod
    def from_glob(cls, 
        dir: str | pathlib.Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_VIDEO_FILE_EXTENSIONS,
        filter_invalid: bool = False,
        verbose: bool = False,
    ) -> typing.List[typing.Self]:
        '''Get sorted list of video files from a given directory.
        Args:
            dir: path in which to search for videos.
            extensions: list of file extensions to search for.
            filter_invalid: include only video files that could be successfully probed.
        '''
        return cls._multi_extension_glob(
            glob_func=pathlib.Path(dir).glob, 
            extensions=extensions, 
            filter_invalid=filter_invalid,
            verbose=verbose,
        )

    @classmethod
    def _multi_extension_glob(cls, 
        glob_func: typing.Callable[[str],pathlib.Path], 
        extensions: typing.Tuple[str, ...],
        filter_invalid: bool,
        verbose: bool,
    ) -> typing.List[typing.Self]:
        all_paths = list()
        for ext in extensions:
            pattern = f'*{ext}' if ext.startswith('.') else f'*.{ext}'
            all_paths += list(glob_func(pattern))
        path_iter = sorted(all_paths)
        
        if filter_invalid:
            if verbose:
                path_iter = tqdm.tqdm(path_iter, ncols=80)
            return [vf for fp in path_iter if (vf := cls.from_path(fp)).is_probable()]
        else:
            return [cls.from_path(fp) for fp in path_iter]

    ######################## dunder Methods ########################
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.fname}")'
    
    ######################## File Methods ########################
    def exists(self) -> bool:
        return self.fpath.exists()

    ######################## Video Manipulation Methods ########################
    def compress(self, 
        output_fname: str, 
        vcodec: str = 'libx264', 
        crf: int = 30, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> typing.Self:
        '''Compress a video to the specified format and return a videofile of the output file.'''
        if pathlib.Path(output_fname).exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
        
        result: FFRunResult = FFRunResult.run(
            ffmpeg_command = (
                ffmpeg
                .input(str(self.fname))
                .output(str(output_fname), vcodec=vcodec, crf=crf, **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        nvf = NewVideoFile.from_path(output_fname, result.stdout)
        if not nvf.exists():
            raise FileNotFoundError(f'The video file "{output_fname}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return nvf

    def splice(self, 
        output_fname: str, 
        start_time: datetime.timedelta, 
        end_time: datetime.timedelta, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> typing.Self:
        '''Splice video given a start time and end time.'''
        if pathlib.Path(output_fname).exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

        #duration = duration_sec if duration_sec is not None else (end_sec - start_sec)
        result: FFRunResult = FFRunResult.run(
            ffmpeg_command = (
                ffmpeg
                .input(self.fname, ss=start_time.total_seconds())
                .output(str(output_fname), t=(end_time-start_time).total_seconds(), **output_kwargs)
            ),
            overwrite_output=overwrite,
        )
        nvf = NewVideoFile.from_path(output_fname, result.stdout)
        if not nvf.exists():
            raise FileNotFoundError(f'The video file "{output_fname}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return nvf

    def crop(self, 
        output_fname: str, 
        topleft_point: typing.Tuple[int,int],
        size: typing.Tuple[int,int],
        overwrite: bool = False, 
        **output_kwargs
    ) -> typing.Self:
        '''Crop the video where the top-left of the frame is at 
        Args:
            topleft_point: (start_x,start_y)
            size: (width,height)
        '''
        if pathlib.Path(output_fname).exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

        result = FFRunResult.run(
            ffmpeg_command = (
                ffmpeg
                .input(str(self.fname))
                .crop(*topleft_point, *size)
                .output(str(output_fname), **output_kwargs)
            ),
            overwrite_output=overwrite,
        )

        nvf = NewVideoFile.from_path(output_fname, result.stdout)
        if not nvf.exists():
            raise FileNotFoundError(f'The video file "{output_fname}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return nvf

    def make_thumb(self, 
        output_fname: str, 
        time_point: float = 0.5, 
        height: int = -1, 
        width: int = -1, 
        overwrite: bool = False, 
        **output_kwargs
    ) -> FFRunResult:
        '''Make a thumbnail from this video.
        Args:
            time_point is the proportion of the video at which to take the thumb (e.g. 0.5 means at half way through.)
        Notes:
            copied from here:
                https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
        '''
        # copied directly from here: 
        # 
        
        #try:
        #    probe = ffmpeg.probe(self.fname)
        #except ffmpeg.Error:
        #    pass
        #else:
        #    try:
        #        time = float(probe['streams'][0]['duration']) // 2
        #        width = probe['streams'][0]['width']
        #        try:
        #            (
        #                ffmpeg
        #                .input(self.fname, ss=time)
        #                .filter('scale', width, -1)
        #                .output(out_filename, vframes=1, **kwargs)
        #                .overwrite_output()
        #                .run(capture_stdout=True, capture_stderr=True)
        #            )
        #        except ffmpeg.Error as e:
        #            print(e.stderr.decode(), file=sys.stderr)
        #            pass
#
        #    except KeyError:
        #        pass
        #time = float(probe['streams'][0]['duration']) // 2
        #width = probe['streams'][0]['width']
        if pathlib.Path(output_fname).exists() and not overwrite:
            raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
        
        probe = self.probe()
        return FFRunResult.run(
            ffmpeg_command = (
                ffmpeg
                .input(self.fname, ss=int(probe.duration * time_point))
                .filter('scale', width, height)
                .output(output_fname, vframes=1, **output_kwargs)
            ),
            overwrite_output=overwrite,
        )

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

    @property
    def fname(self) -> str:
        '''Get fpath as a string.'''
        return str(self.fpath)
    
    @property
    def path(self) -> pathlib.Path:
        return self.fpath



@dataclasses.dataclass(repr=False)
class NewVideoFile(VideoFile):
    stdout: str
    
    @classmethod
    def from_path(cls,
        fpath: str | pathlib.Path,
        stdout: str,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = pathlib.Path(fpath)
        if check_exists and not fp.exists():
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(
            fpath=fp,
            stdout = str(stdout),
        )

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(fname="{self.fname}")'
    

