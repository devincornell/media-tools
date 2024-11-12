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

class ImageFiles(typing.List[ImageFile]):
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