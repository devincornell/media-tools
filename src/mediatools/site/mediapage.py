from __future__ import annotations
import typing
import pathlib
import dataclasses

#from .siteconfig import SiteConfig
from .siteconfig import SiteConfig
from .vidinfo import VidInfo
from .imginfo import ImgInfo
from ..util import format_memory, format_time, multi_extension_glob
 
#from ..vtools import ProbeError, FFMPEGCommandError


@dataclasses.dataclass
class MediaPage:
    local_path: pathlib.Path
    config: SiteConfig
    videos: list[VidInfo]
    images: list[ImgInfo]
    subfolders: list[pathlib.Path]

    @classmethod
    def scan_directory(cls, path: pathlib.Path, config: SiteConfig) -> VidInfo:
        '''Scan a directory to collect information about the media files and subfolders.'''
        
        return cls(
            local_path = path,
            config = config,
            videos = VidInfo.scan_directory(path, config),
            images = ImgInfo.scan_directory(path, config),
            subfolders = [p for p in path.iterdir() if p.is_dir()],
        )
