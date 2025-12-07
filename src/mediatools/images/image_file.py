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
    path: Path
    meta: dict[str, dict|str|int|float|bool|list|None] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_path(cls, 
        path: Path,
        check_exists: bool = True,
        meta: dict[typing.Hashable, typing.Any] = None,
    ) -> typing.Self:
        fp = Path(path)
        if check_exists and not fp.exists():
            raise FileNotFoundError(f'The image file "{fp}" was not found.')
        return cls(path=fp, meta=meta or {})

    def read(self) -> Image:
        '''Read the image into memory.'''
        return Image.from_file(self.path)

    def get_info(self) -> ImageInfo:
        '''Get the image information for this image file.'''
        return ImageInfo.from_image_file(self)
    
    def to_dict(self) -> dict[str, typing.Any]:
        '''Convert to dictionary representation.'''
        return {
            'path': str(self.path),
            'meta': self.meta,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> typing.Self:
        '''Create an ImageFile instance from a dictionary representation.'''
        return cls(
            path=Path(data.get('path', data.get('fpath'))),  # support both for backward compatibility
            meta=data.get('meta', {}),
        )