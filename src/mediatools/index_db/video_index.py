from __future__ import annotations
import dataclasses
from typing import List, Optional
from datetime import datetime
import typing
from pydantic import Field, BaseModel

import pymongo
import pymongo.errors
from pymongo.asynchronous.collection import AsyncCollection
import asyncio

import os
import typing
import tqdm
import random
import pydantic
import pathlib
from pathlib import Path
import re

from mediatools.video import video_file

from ..video import VideoFile, VideoMeta

from ..video.ffmpeg import ProbeInfo, ProbeError
from ..util import format_memory, format_time, fname_to_title, fname_to_id

from ..file_stat_result import FileStatResult

from .util import index_hash_func

class VideoFileNotFoundError(Exception):
    '''Raised when a video file is not found in the database.'''
    pass

class HashProjection(BaseModel):
    file_hash: str

@dataclasses.dataclass
class VideoIndexCollection:
    '''Interface for working with the video_file_index collection.'''
    _collection: AsyncCollection

    @classmethod
    def from_collection(cls, collection: AsyncCollection) -> typing.Self:
        '''Create a VideoIndexCollection from a MongoDB collection.'''
        return cls(_collection=collection)

    async def create_indexes(self) -> None:
        '''Create necessary indexes on the collection.'''
        await self._collection.create_index('file_hash', unique=True)
        await self._collection.create_index("path")

    async def find_by_hash(self, file_hash: str) -> VideoIndexDoc:
        '''Find a VideoIndexDoc by its file_hash.'''
        doc = await self._collection.find_one({'file_hash': file_hash})
        if doc is None:
            raise VideoFileNotFoundError(f'Video file with hash not found: {file_hash}')
        return VideoIndexDoc(**doc)

    async def find_all_by_root_path(self, root_path: pathlib.Path) -> list[VideoIndexDoc]:
        '''Find all VideoIndexDocs where the path starts with the given root_path.'''
        cursor = self._collection.find({'path_str': {'$regex': f'^{re.escape(str(root_path))}'}})
        docs = []
        async for doc in cursor:
            docs.append(VideoIndexDoc(**doc))
        return docs
    
    async def update_path(self, file_hash: str, new_path: pathlib.Path|str) -> None:
        '''Update the path of a VideoIndexDoc identified by its file_hash.'''
        result = await self._collection.update_one(
            {'file_hash': file_hash},
            {'$set': {'path_str': str(new_path)}}
        )
        if result.matched_count == 0:
            raise VideoFileNotFoundError(f'Video file with hash not found for update: {file_hash}')

    async def insert(self, video_index_doc: VideoIndexDoc) -> None:
        '''Insert a VideoIndexDoc into the collection.'''
        await self._collection.insert_one(video_index_doc.model_dump())

class VideoIndexDoc(pydantic.BaseModel):
    path_str: str
    file_hash: str  # Unique index on hash of first MB
    probe: ProbeInfo
    stat: FileStatResult
    meta: dict[str, pydantic.JsonValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_path_scan(cls, path: str) -> typing.Self:
        """Create a VideoIndexDoc from a file path."""
        video_file = VideoFile.from_path(path)
        file_hash = index_hash_func(video_file.path)
        return cls.from_video_file_scan(video_file, file_hash=file_hash)

    @classmethod
    def from_video_file_scan(cls, video_file: VideoFile, file_hash: str) -> typing.Self:
        """Create a VideoIndexDoc from a VideoFile instance."""
        meta = video_file.read_meta()
        return cls(
            file_hash=file_hash,
            path_str=str(video_file.path),
            probe=meta.probe,
            stat=meta.stat,
            meta=meta.meta,
        )
        
    @property
    def tags(self) -> dict[str, str|int|float|bool|None]:
        '''Return the tags from the meta field, or an empty list if not present.'''
        return self.probe.tags
    