from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path


from .image import Image
from .image_info import ImageInfo
from ..file_base import FileBase, JSONable

@dataclasses.dataclass(frozen=True, repr=True, slots=True)
class ImageFile(FileBase):
    '''Represents an image file.'''
    path: Path
    meta: dict[str, JSONable] = dataclasses.field(default_factory=dict)

    def read(self) -> Image:
        '''Read the image into memory.'''
        return Image.from_file(self.path)

    def get_info(self) -> ImageInfo:
        '''Get the image information for this image file.'''
        return ImageInfo.from_image_file(self)
    