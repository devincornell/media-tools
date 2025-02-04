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

from ..images import ImageFile
from .baseinfo import BaseInfo
from .siteconfig import SiteConfig
from .util import fname_to_title, parse_url
from ..util import multi_extension_glob

Width = int
Height = int

@dataclasses.dataclass
class ImgInfo(BaseInfo):
    imf: ImageFile
    config: SiteConfig
    res: typing.Tuple[Width, Height]
    size: int

    @classmethod
    def scan_directory(
        cls, 
        path: pathlib.Path, 
        config: SiteConfig, 
    ) -> list[typing.Self]:
        '''Scan directory for video files and return list of info objects.'''
        return [cls.from_path(fp, config) for fp in multi_extension_glob(path.glob, config.img_extensions)]

    @classmethod
    def from_path(cls, path: pathlib.Path, config: SiteConfig) -> typing.Self:
        '''Create ImgInfo object from file path.'''
        path = pathlib.Path(path)
        imf = ImageFile.from_path(path)
        h,w,z = imf.read().shape
        return cls(
            imf = imf, 
            config = config,
            res=(w,h),
            size = path.stat().st_size,
        )
    
    def info_dict(self) -> typing.Dict[str, str|int]:
        return {
            'path': parse_url(self.fpath.name),
            'title': fname_to_title(self.fpath.stem),
            'aspect': self.aspect(),
        }

    def aspect(self) -> float:
        return self.res[0]/self.res[1]
    
    def path_rel(self) -> pathlib.Path:
        '''Thumb path relative to base path.'''
        fp = self.fpath.relative_to(self.config.root_path)
        return fp
