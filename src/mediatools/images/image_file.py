from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
#import pathlib
from pathlib import Path
import pydantic

from .image import Image
from ..file_base import FileBase
from .image_meta import ImageMeta

@dataclasses.dataclass(frozen=True, repr=True, slots=True)
class ImageFile(FileBase):
    '''Represents an image file.'''
    path: Path
    meta: dict[str, pydantic.JsonValue] = dataclasses.field(default_factory=dict)

    def read(self) -> Image:
        '''Read the image into memory.'''
        return Image.from_file(self.path)

    def read_meta(self) -> ImageMeta:
        '''Get the image information for this image file.'''
        return ImageMeta.from_image_file(self)
    