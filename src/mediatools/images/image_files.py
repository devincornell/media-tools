from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path


from ..util import multi_extension_glob
from .image import Image
from .image_file import ImageFile

DEFAULT_IMAGE_FILE_EXTENSIONS = ('jpg', 'JPG', 'jpeg', 'JPEG', 'png', 'PNG', 'bmp', 'BMP', 'gif', 'GIF', 'tiff', 'TIFF', 'tif', 'TIF')

class ImageFiles(list[ImageFile]):
    '''Collection of image files.'''

    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
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
        return cls([ImageFile(fp) for fp in paths])

    @classmethod
    def from_glob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
        base_name_pattern: str = '*',
    ) -> typing.Self:
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
        return cls([ImageFile(fp) for fp in paths])


    def read_all(self) -> typing.Generator[Image]:
        '''Read the images into memory as a generator.'''
        for img in self:
            yield img.read()
    
    def to_dict(self) -> ImageFilesDict:
        '''Convert to ImageFilesDict.'''
        return ImageFilesDict({imf.path: imf for imf in self})


class ImageFilesDict(dict[Path, ImageFile]):
    '''Collection of image files.'''

    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
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
        return cls({fp: ImageFile(fp) for fp in paths})

    @classmethod
    def from_glob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
        base_name_pattern: str = '*',
    ) -> typing.Self:
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
        return cls({fp: ImageFile(fp) for fp in paths})

    def read_all(self) -> typing.Generator[Image]:
        '''Read the images into memory as a generator.'''
        for img in self.values():
            yield img.read()

    @classmethod
    def from_jsonable(cls, image_infos: list[dict]) -> typing.Self:
        '''Create ImageFilesDict from serializable dict.'''
        return cls({(imf := ImageFile.from_dict(vd)).path.name: imf for vd in image_infos})

    def to_jsonable(self) -> list[dict]:
        '''Convert to serializable dict.'''
        return [v.to_dict() for v in self.values()]

    @classmethod
    def from_image_files(cls, image_files: typing.Iterable[ImageFile]) -> typing.Self:
        '''Create ImageFilesDict from ImageFiles list.'''
        return cls({imf.path: imf for imf in image_files})

    def to_list(self) -> ImageFiles:
        '''Convert to ImageFiles list.'''
        return ImageFiles(self.values())