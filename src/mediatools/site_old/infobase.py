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

from .util import *

class InfoBase:
    @classmethod
    def from_fpath(self, *args, **kwargs):
        raise NotImplementedError(f'This method should have been implemented by subclass.')
    
    def get_rel_path(self) -> pathlib.Path:
        '''Path relative to the original base path.'''
        return self.fpath.relative_to(self.config.base_path)
    
    def file_size(self) -> int:
        return self.fpath.stat().st_size



