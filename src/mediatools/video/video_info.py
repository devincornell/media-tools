
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


from ..util import format_memory, format_time, fname_to_title, fname_to_id

if typing.TYPE_CHECKING:
    from .video_file import VideoFile
    from .probe_info import ProbeInfo



@dataclasses.dataclass#(repr=False)
class VideoInfo:
    '''Info about a single video.'''
    vfile: VideoFile
    probe: ProbeInfo
    stat: os.stat_result

    @classmethod
    def from_video_file(cls, vfile: VideoFile, do_check: bool = True) -> typing.Self:
        '''Get video information by probing video file.'''
        stat = vfile.fpath.stat()
        probe = vfile.probe()
        
        if do_check:
            probe.check_for_errors()
        
        return cls(
            vfile = vfile,
            probe = probe,
            stat = stat,
        )
    
    def duration_str(self) -> str:
        '''Get the duration of the video file as a string.'''
        return format_time(self.probe.duration)

    def size_str(self) -> str:
        '''Get the size of the video file in bytes.'''
        return format_memory(self.stat.st_size)
    
    def resolution_str(self) -> str:
        '''Get the resolution of the video file as a string.'''
        return f'{self.probe.video.width}x{self.probe.video.height}'
    
    def aspect_ratio(self) -> int:
        '''Get the aspect ratio of the video file as a string.'''
        return self.probe.video.aspect_ratio
    
    def title(self) -> str:
        '''Get the title of the video file.'''
        return fname_to_title(self.vfile.fpath.stem)

    def id(self) -> str:
        '''Get the ID of the video file.'''
        return fname_to_id(self.vfile.fpath.stem)
    
    @property
    def size(self) -> int:
        '''Get the size of the video file in bytes.'''
        return self.stat.st_size
    
    @property
    def fpath(self) -> pathlib.Path:
        '''Get the file path of the video file.'''
        return self.vfile.fpath
