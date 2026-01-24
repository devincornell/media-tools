from __future__ import annotations
import dataclasses
from typing import List, Optional
from datetime import datetime
import typing
#from beanie import Document, Indexed, Link
import beanie
import beanie.exceptions
from pydantic import Field, BaseModel
import pymongo
import pymongo.errors
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
import typing
import tqdm
import random
import pydantic
import pathlib
from beanie.operators import Set
from pathlib import Path

from ..video import VideoFile
from ..video.ffmpeg import ProbeInfo, ProbeError
from .util import get_hash_firstmb_hex
from ..util import format_memory, format_time, fname_to_title, fname_to_id
from .file_stat_info import FileStatInfo


class HashProjection(BaseModel):
    hash_firstmb: str



class VideoFileIndex(beanie.Document):
    class Settings:
        name = "video_file_index"  # The collection name in MongoDB
    path: str
    hash_firstmb: beanie.Indexed(str, unique=True)  # Unique index on hash of first MB
    probe: ProbeInfo# = None
    stat: FileStatInfo# = None
    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_path(cls, path: str) -> typing.Self:
        """Create a VideoFileIndex from a file path."""
        video_file = VideoFile.from_path(path)
        return cls.from_video_file(video_file)

    @classmethod
    def from_video_file(cls, video_file: VideoFile) -> typing.Self:
        """Create a VideoFileIndex from a VideoFile instance."""
        return cls(
            hash_firstmb=get_hash_firstmb_hex(video_file.path),
            path=str(video_file.path),
            probe=video_file.probe(),
            stat=FileStatInfo.from_file_stat(os.stat(video_file.path))
        )

    @classmethod
    async def find_by_hash(cls, hash_firstmb: str) -> Optional[typing.Self]:
        """Find a VideoFileIndex by its hash_firstmb."""
        return await cls.find_one(cls.hash_firstmb == hash_firstmb)
    
    @classmethod
    async def insert_video_files(cls, video_files: list[VideoFile], verbose: bool = False) -> None:
        '''Insert multiple VideoFile instances into the database. Typically you could use MediaDir.all_videos() to 
            get the list of VideoFile instances.
        '''
        exist_hashes = await cls.find_all().project(HashProjection).to_list()
        exist_hashes = {et.hash_firstmb for et in exist_hashes}
        if verbose: print(f'Existing hashes in DB: {len(exist_hashes)}')

        for vf in tqdm.tqdm(video_files):
            if get_hash_firstmb_hex(vf.path) not in exist_hashes:
                try:
                    vfd = cls.from_video_file(vf)
                    await vfd.insert()
                    exist_hashes.add(vfd.hash_firstmb)
                except ProbeError as e:
                    if verbose: print(f'\nError probing file {vf.path}: {e}\n')

    def template_dict(self) -> dict[str,str|int|float|None]:
        '''Get a dictionary of template variables for this video file.'''
        if self.probe.tags is not None and 'creation_time' in self.probe.tags:
            created_ts_str = self.probe.tags['creation_time']
            created_ts = datetime.fromisoformat(created_ts_str)
            created_str = created_ts.strftime('%Y-%m-%d %H:%M:%S')
        else:
            created_ts = None
            created_str = None

        return {
            'hash_firstmb': self.hash_firstmb,
            'path': self.path,

            'id': fname_to_id(pathlib.Path(self.path).stem),
            'title': fname_to_title(pathlib.Path(self.path).stem),
            
            'size': self.stat.size,
            'size_str': format_memory(self.stat.size),
            
            'duration': self.probe.duration,
            'duration_str': format_time(self.probe.duration),
            
            'created_ts': created_ts.timestamp() if created_ts is not None else None,
            'created_str': created_str,

            'resolution_str': f'{self.probe.video.width}x{self.probe.video.height}',
            'width': self.probe.video.width,
            'height': self.probe.video.height,
            'aspect': self.probe.video.aspect_ratio,
        }
