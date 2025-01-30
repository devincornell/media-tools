from __future__ import annotations
import typing

import dataclasses
import pathlib

from .baseinfo import BaseInfo
from .siteconfig import SiteConfig
from ..video import VideoFile, ProbeInfo
from ..util import multi_extension_glob

@dataclasses.dataclass
class VidInfo(BaseInfo):
    '''Info about a single video.'''
    vf: VideoFile
    config: SiteConfig
    probe: ProbeInfo

    @classmethod
    def scan_directory(
        cls, 
        path: pathlib.Path, 
        config: SiteConfig, 
    ) -> list[typing.Self]:
        '''Scan directory for video files and return list of info objects.'''
        return [cls.from_path(fp, config) for fp in multi_extension_glob(path, config.vid_extensions)]

    @classmethod
    def from_path(cls, vpath: pathlib.Path, config: SiteConfig) -> typing.Self:
        '''Get video information by probing video file.'''
        vpath = pathlib.Path(vpath)

        vf = VideoFile.from_path(vpath)
        return cls(
            vf = vf,
            config = SiteConfig,
            probe = vf.probe(),
        )
