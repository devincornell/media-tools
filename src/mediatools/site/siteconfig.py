
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





@dataclasses.dataclass
class SiteConfig:
    base_path: pathlib.Path
    thumb_base_path: pathlib.Path
    template: str
    page_fname: str
    vid_extensions: tuple[str, ...]
    img_extensions: tuple[str, ...]
    thumb_extension: str
    video_width: int
    clip_width: int
    ideal_aspect: float
    clip_duration: int
    do_clip_autoplay: bool


