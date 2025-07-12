
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


from .infobase import InfoBase
from ..util import format_memory, format_time

from .siteconfig import SiteConfig
from .util import parse_url, fname_to_title, fname_to_id

from ..video import VideoFile, ProbeInfo, ProbeError, NoDurationError, NoResolutionError

@dataclasses.dataclass
class VidInfo(InfoBase):
    '''Info about a single video.'''
    vf: VideoFile
    probe: ProbeInfo
    config: SiteConfig

    @classmethod
    def from_fpath(cls, vpath: pathlib.Path, config: SiteConfig) -> VidInfo:
        '''Get video information by probing video file.'''
        probe = VideoFile.from_path(vpath).probe()
        probe.video # will error if there is no video stream

        return cls(
            vf = VideoFile(vpath),
            probe = probe, 
            config = config,
        )
    
    @property
    def fpath(self) -> pathlib.Path:
        return self.vf.fpath
    
    def aspect(self) -> float:
        return self.probe.video.aspect_ratio
        #if self.probe.video.aspect_ratio is not None or self.probe.video.aspect_ratio != 0:
        #    return self.probe.video.aspect_ratio
        #return self.probe.video.width / self.probe.video.height
        
    def has_thumb(self) -> bool:
        return self.thumb_path_abs().is_file()

    def make_thumb(self):
        '''Actually make thumbnail.'''
        tfp = self.thumb_path_abs()
        if not tfp.is_file(): # NOTE: delete this if trying to force write
            tfp.parent.mkdir(exist_ok=True, parents=True)
            return self.vf.ffmpeg.make_thumb(str(tfp))
            #return pydevin.make_thumb_ffmpeg(str(self.fpath), str(tfp))
    
    def thumb_path_rel(self) -> pathlib.Path:
        '''Thumb path relative to base path.'''
        fp = self.thumb_path_abs().relative_to(self.config.base_path)
        return fp

    def thumb_path_abs(self) -> pathlib.Path:
        '''Absolute thumb path.'''
        rel_path = self.get_rel_path().with_suffix(self.config.thumb_extension)
        #print(f'=============')
        #print(rel_path)
        thumb_fname = str(rel_path).replace('/', '.')
        #print(thumb_fname)
        #print(self.config.thumb_base_path.joinpath(thumb_fname))
        return self.config.thumb_base_path.joinpath(thumb_fname)
    
    def check_is_valid(self) -> bool:
        '''Check if the video file is valid.'''
        try:
            self.probe.check_for_errors()
        except (ProbeError, NoDurationError, NoResolutionError):
            return False
        return True
    
    @property
    def is_clip(self) -> bool:
        '''Check whether this video is a clip (short video) based on the configuration.'''
        try:
            return self.probe.duration <= self.config.clip_duration
        except NoDurationError:
            return False
    
    def info_dict(self) -> typing.Dict[str, str|int|bool]:
        return {
            'vid_web': self.vid_web,
            'vid_title': self.vid_title,
            'thumb_web': parse_url('/'+str(self.thumb_path_rel())),
            'vid_size': self.file_size(),
            'vid_size_str': format_memory(self.file_size()),
            
            # from ffmpeg probe
            'is_clip': self.is_clip,
            'do_autoplay': 'autoplay loop muted' if self.is_clip and self.config.do_clip_autoplay else '',
            'duration': self.probe.duration,
            'duration_str': format_time(self.probe.duration),
            'res_str': f'{self.probe.video.width}x{self.probe.video.height}',
            'aspect': self.probe.video.aspect_ratio,
            'idx': fname_to_id(self.fpath.stem)
        }
    
    @property
    def vid_title(self) -> str:
        return fname_to_title(self.fpath.stem)

    @property
    def vid_web(self) -> str:
        return parse_url(self.fpath.name)
