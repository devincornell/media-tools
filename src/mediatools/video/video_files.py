from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path


from ..util import multi_extension_glob
#from .image import Image
#from .image_file import ImageFile
from .video_file import VideoFile

DEFAULT_VIDEO_FILE_EXTENSIONS = ('mp4','mov','avi','mkv', 'webm', 'flv', 'ts')

class VideoFiles(list[VideoFile]):
    '''Collection of image files.'''

    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_VIDEO_FILE_EXTENSIONS,
        base_name_pattern: str = '*',
    ) -> typing.Self:
        '''Get sorted list of video files from a given directory recursively.
        Args:
            root: root path from which to search for videos.
            extensions: list of file extensions to search for.
            filter_invalid: include only video files that could be successfully probed.
        '''
        paths = multi_extension_glob(
            glob_func=Path(root).rglob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return cls([VideoFile(fp) for fp in paths])

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
        paths = multi_extension_glob(
            glob_func=Path(root).glob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return cls([VideoFile(fp) for fp in paths])
    
    def to_dict(self) -> VideoFilesDict:
        '''Convert to VideoFilesDict.'''
        return VideoFilesDict({vf.path: vf for vf in self})

class VideoFilesDict(dict[Path, VideoFile]):
    '''Collection of image files.'''

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
        paths = multi_extension_glob(
            glob_func=Path(root).rglob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return cls({fp: VideoFile(fp) for fp in paths})

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
        paths = multi_extension_glob(
            glob_func=Path(root).glob, # type: ignore
            extensions=extensions, 
            base_name_pattern=base_name_pattern,
        )
        return cls({fp: VideoFile(fp) for fp in paths})

    @classmethod
    def from_video_files(cls, video_files: typing.Iterable[VideoFile]) -> typing.Self:
        '''Create VideoFilesDict from VideoFiles list.'''
        return cls({vf.path: vf for vf in video_files})
    
    @classmethod
    def from_jsonable(cls, vid_infos: list[dict]) -> typing.Self:
        '''Create VideoFilesDict from serializable dict.'''
        return cls({(vf := VideoFile.from_dict(vd)).path.name: vf for vd in vid_infos})

    def to_jsonable(self) -> list[dict]:
        '''Convert to serializable dict.'''
        return [v.to_dict() for v in self.values()]

    def to_list(self) -> VideoFiles:
        '''Convert to VideoFiles list.'''
        return VideoFiles(self.values())
