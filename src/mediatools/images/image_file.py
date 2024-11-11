from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path

import mediatools.util
from .image import Image


DEFAULT_IMAGE_FILE_EXTENSIONS = ('jpg', 'JPG', 'jpeg', 'JPEG', 'png', 'PNG', 'bmp', 'BMP', 'gif', 'GIF', 'tiff', 'TIFF', 'tif', 'TIF')

@dataclasses.dataclass(frozen=True)
class ImageFile:
    '''Represents an image file.'''
    fpath: Path

    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
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
        extensions: typing.Tuple[str, ...] = DEFAULT_IMAGE_FILE_EXTENSIONS,
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
        fpath: Path,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and not fp.exists():
            raise FileNotFoundError(f'The image file "{fp}" was not found.')
        return cls(fpath=fp)

    def read(self) -> Image:
        '''Read the image into memory.'''
        return Image.from_file(self.fpath)

