from __future__ import annotations
import jinja2
import typing
import pathlib
import dataclasses
import pprint
import subprocess
import os
import tqdm
import sys
import html
import urllib.parse
from PIL import Image
import pydantic
from pathlib import Path

from ..file_stat_result import FileStatResult
#from ..util import format_memory, fname_to_title, fname_to_id

if typing.TYPE_CHECKING:
    from .image_file import ImageFile

class ImageMeta(pydantic.BaseModel):
    '''Info about a single image.'''
    path: Path
    res: typing.Tuple[int, int]
    stat: FileStatResult
    meta: dict[str, pydantic.JsonValue] = pydantic.Field(default_factory=dict)

    @classmethod
    def from_image_file(cls, ifile: ImageFile) -> typing.Self:
        '''Get video information by probing video file.'''
        stat = FileStatResult.read_from_path(ifile.path)
        im = Image.open(str(ifile.path))
        width, height = im.size
     
        return cls(
            path = ifile.path,
            meta = ifile.meta,
            res=(width, height),
            stat = stat,
        )

    @classmethod
    def from_path(cls, path: pathlib.Path) -> typing.Self:
        '''Get image information by probing image file.'''
        stat = FileStatResult.read_from_path(path)
        im = Image.open(str(path))
        width, height = im.size
        return cls(
            path = path,
            meta = {},
            res=(width, height),
            stat = stat,
        )
        
    def aspect_ratio(self) -> float:
        return self.res[0]/self.res[1]

    def title(self) -> str:
        '''Get the title of the image file.'''
        return fname_to_title(self.path.stem)
    
    def id(self) -> str:
        '''Get the ID of the image file.'''
        return fname_to_id(self.path.stem)
        
