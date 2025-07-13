

from __future__ import annotations
import jinja2
import typing
import pathlib
import dataclasses
import pprint
import subprocess
import os
import tqdm
import ffmpeg
import sys
import html
import urllib.parse
from PIL import Image


from ..util import format_memory, fname_to_title, fname_to_id

if typing.TYPE_CHECKING:
    from .image_file import ImageFile

@dataclasses.dataclass
class ImageInfo:
    '''Info about a single video.'''
    ifile: ImageFile
    res: typing.Tuple[int, int]
    stat: os.stat_result

    @classmethod
    def from_image_file(cls, ifile: ImageFile) -> typing.Self:
        '''Get video information by probing video file.'''
        stat = ifile.fpath.stat()   
        im = Image.open(str(ifile.fpath))
        width, height = im.size
     
        return cls(
            ifile = ifile,
            res=(width, height),
            stat = stat,
        )
    
    def size_str(self) -> str:
        '''Get the size of the video file in bytes.'''
        return format_memory(self.stat.st_size)
    
    def aspect_ratio(self) -> float:
        return self.res[0]/self.res[1]

    def title(self) -> str:
        '''Get the title of the video file.'''
        return fname_to_title(self.ifile.fpath.stem)
    
    def id(self) -> str:
        '''Get the ID of the video file.'''
        return fname_to_id(self.ifile.fpath.stem)
    
    @property
    def size(self) -> int:
        '''Get the size of the video file in bytes.'''
        return self.stat.st_size
    
    @property
    def fpath(self) -> pathlib.Path:
        '''Get the file path of the video file.'''
        return self.ifile.fpath
    
