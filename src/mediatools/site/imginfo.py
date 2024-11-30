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

from .infobase import InfoBase
from .siteconfig import SiteConfig
from .util import *

@dataclasses.dataclass
class ImgInfo(InfoBase):
    fpath: pathlib.Path
    res: typing.Tuple[int, int]
    config: SiteConfig

    @classmethod
    def from_fpath(cls, fpath: pathlib.Path, config: SiteConfig) -> ImgInfo:
        if not fpath.is_file():
            raise ValueError(f'The provided image is not a file: {fpath}')
        
        im = Image.open(str(fpath))
        width, height = im.size

        return cls(fpath, res=(width, height), config=config)
    
    def info_dict(self) -> typing.Dict[str, str]:
        return {
            'path': parse_url(self.fpath.name),
            'title': fname_to_title(self.fpath.stem),
            'aspect': self.aspect(),
        }

    def aspect(self) -> float:
        return self.res[0]/self.res[1]
    
    def path_rel(self) -> pathlib.Path:
        '''Thumb path relative to base path.'''
        fp = self.fpath.relative_to(self.config.base_path)
        return fp
