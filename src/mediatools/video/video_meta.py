
from __future__ import annotations
import jinja2
import typing
import pathlib
import dataclasses
import pprint
import subprocess
import os
from pathlib import Path

import pydantic

from ..file_stat_result import FileStatResult
from ..util import format_memory, format_time, fname_to_title, fname_to_id

from .ffmpeg import ProbeInfo

if typing.TYPE_CHECKING:
    from .video_file import VideoFile

class VideoMeta(pydantic.BaseModel):
    '''Container for video probe and os.stat_result.'''
    path: Path
    probe: ProbeInfo
    stat: FileStatResult
    meta: dict[str, pydantic.JsonValue] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_video_file(cls, vfile: VideoFile, do_check: bool = True) -> typing.Self:
        '''Get video information by probing video file.'''
        stat = FileStatResult.read_from_path(vfile.path)
        probe = vfile.probe()
        
        if do_check:
            probe.check_for_errors()
        
        return cls(
            path = vfile.path,
            meta = vfile.meta,
            probe = probe,
            stat = stat,
        )
    
    def duration_str(self) -> str:
        '''Get the duration of the video file as a string.'''
        return format_time(self.probe.duration)
    
    def resolution_str(self) -> str:
        '''Get the resolution of the video file as a string.'''
        return f'{self.probe.video.width}x{self.probe.video.height}'
    
    def aspect_ratio(self) -> int:
        '''Get the aspect ratio of the video file as a string.'''
        return self.probe.video.aspect_ratio
    
    def title(self) -> str:
        '''Get the title of the video file.'''
        return fname_to_title(self.path.stem)

    def id(self) -> str:
        '''Get the ID of the video file.'''
        return fname_to_id(self.path.stem)
    