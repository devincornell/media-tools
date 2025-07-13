from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path


from .image import Image
from .image_info import ImageInfo

DEFAULT_IMAGE_FILE_EXTENSIONS = ('jpg', 'JPG', 'jpeg', 'JPEG', 'png', 'PNG', 'bmp', 'BMP', 'gif', 'GIF', 'tiff', 'TIFF', 'tif', 'TIF')

@dataclasses.dataclass(frozen=True)
class ImageFile:
    '''Represents an image file.'''
    fpath: Path

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

    def get_info(self) -> ImageInfo:
        '''Get the image information for this image file.'''
        return ImageInfo.from_image_file(self)