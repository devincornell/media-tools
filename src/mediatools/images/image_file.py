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
    meta: dict[str, dict|str|int|float|bool|list|None] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_path(cls, 
        fpath: Path,
        check_exists: bool = True,
        meta: dict[typing.Hashable, typing.Any] = None,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and not fp.exists():
            raise FileNotFoundError(f'The image file "{fp}" was not found.')
        return cls(fpath=fp, meta=meta or {})

    def read(self) -> Image:
        '''Read the image into memory.'''
        return Image.from_file(self.fpath)

    def get_info(self) -> ImageInfo:
        '''Get the image information for this image file.'''
        return ImageInfo.from_image_file(self)
    
    def to_dict(self) -> dict[str, typing.Any]:
        '''Convert to dictionary representation.'''
        return {
            'fpath': str(self.fpath),
            'meta': self.meta,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> typing.Self:
        '''Create an ImageFile instance from a dictionary representation.'''
        return cls(
            fpath=Path(data['fpath']),
            meta=data.get('meta', {}),
        )