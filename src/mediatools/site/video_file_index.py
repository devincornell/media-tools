from __future__ import annotations
import dataclasses
from typing import List, Optional
from datetime import datetime
import typing
from pydantic import Field, BaseModel
import pymongo
import pymongo.errors
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

import beanie
import beanie.exceptions
#from beanie import Document, Indexed, Link
from beanie import init_beanie
from beanie.odm.queries.find import FindMany

import os
import typing
import tqdm
import random
import pydantic
import pathlib
from beanie.operators import Set
from pathlib import Path
import re

from ..video import VideoFile, VideoMeta

from ..video.ffmpeg import ProbeInfo, ProbeError
from ..util import format_memory, format_time, fname_to_title, fname_to_id, get_hash_firstlast_hex

from ..file_stat_result import FileStatResult


class VideoFileNotFoundError(Exception):
    '''Raised when a video file is not found in the database.'''
    pass

class HashProjection(BaseModel):
    hash_firstlast1kb: str

class VideoFileIndex(beanie.Document):
    class Settings:
        name = "video_file_index"  # The collection name in MongoDB
    path: str
    hash_firstlast1kb: beanie.Indexed(str, unique=True)  # Unique index on hash of first MB
    probe: ProbeInfo
    stat: FileStatResult
    meta: dict[str, pydantic.JsonValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_path(cls, path: str) -> typing.Self:
        """Create a VideoFileIndex from a file path."""
        video_file = VideoFile.from_path(path)
        return cls.from_video_file(video_file)

    @classmethod
    def from_video_file(cls, video_file: VideoFile, hash_firstlast1kb: str|None = None) -> typing.Self:
        """Create a VideoFileIndex from a VideoFile instance."""
        meta = video_file.read_meta()
        return cls(
            hash_firstlast1kb=hash_firstlast1kb or get_hash_firstlast_hex(video_file.path, chunk_size=1024),
            path=str(video_file.path),
            probe=meta.probe,
            stat=meta.stat,
            meta=meta.meta,
        )
    
    @classmethod
    async def find_or_add_from_path(cls, path: pathlib.Path) -> typing.Self:
        """Find a VideoFileIndex by path, or add it if it doesn't exist and return it."""
        path = Path(path).resolve()
        if not path.exists():
            raise FileNotFoundError(f'File not found: {path}')
        
        vf = VideoFile.from_path(path)
        hash_hex = get_hash_firstlast_hex(vf.path)
        try:
            vfi = await cls.find_by_hash(hash_hex)
            return vfi
        except VideoFileNotFoundError:
            new_vfi = cls.from_video_file(vf, hash_firstlast1kb=hash_hex)
            await new_vfi.insert()
            return new_vfi

    @classmethod
    async def find_by_hash(cls, hash_firstlast1kb: str) -> typing.Self:
        """Find a VideoFileIndex by its hash_firstlast1kb."""
        vfi = await cls.find_one(cls.hash_firstlast1kb == hash_firstlast1kb)
        if vfi is None:
            raise VideoFileNotFoundError(f'Video file with hash not found: {hash_firstlast1kb}')
        return vfi
    
    @classmethod
    async def find_all_by_root_path(cls, root_path: pathlib.Path) -> FindMany[typing.Self]:
        """Find all VideoFileIndex documents under a given root path."""
        return await cls.find(cls.path==re.compile(f"^{re.escape(str(root_path))}"))
        
    @classmethod
    async def insert_video_files(cls, video_files: list[VideoFile], verbose: bool = False) -> None:
        '''Insert multiple VideoFile instances into the database. Typically you could use MediaDir.all_videos() to 
            get the list of VideoFile instances.
        '''
        exist_hashes = await cls.find_all().project(HashProjection).to_list()
        exist_hashes = {et.hash_firstlast1kb for et in exist_hashes}
        if verbose: print(f'Existing hashes in DB: {len(exist_hashes)}')

        for vf in tqdm.tqdm(video_files):
            hash_firstlast1kb = get_hash_firstlast_hex(vf.path, chunk_size=1024)
            if hash_firstlast1kb not in exist_hashes:
                try:
                    vfd = cls.from_video_file(vf, hash_firstlast1kb=hash_firstlast1kb)
                    await vfd.insert()
                    exist_hashes.add(vfd.hash_firstlast1kb)
                except ProbeError as e:
                    if verbose: print(f'\nError probing file {vf.path}: {e}\n')

    def template_dict(self) -> dict[str,str|int|float|None]:
        '''Get a dictionary of template variables for this video file.'''
        if self.meta.probe.tags is not None and 'creation_time' in self.meta.probe.tags:
            created_ts_str = self.meta.probe.tags['creation_time']
            created_ts = datetime.fromisoformat(created_ts_str)
            created_str = created_ts.strftime('%Y-%m-%d %H:%M:%S')
        else:
            created_ts = None
            created_str = None

        return {
            'hash_firstlast1kb': self.hash_firstlast1kb,
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
