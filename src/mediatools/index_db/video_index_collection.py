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

from ..video import VideoFile, VideoMeta
from ..mediadir import MediaDir
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
    collection_name: str

    @classmethod
    async def from_client(cls, client: pymongo.AsyncMongoClient, collection_name: str = 'video_file_index') -> typing.Self:
        '''Create a VideoIndexCollection from a MongoDB database.'''
        return cls.from_collection(collection=client[collection_name])

    @classmethod
    def from_collection(cls, collection: AsyncCollection) -> typing.Self:
        '''Create a VideoIndexCollection from a MongoDB collection.'''
        return cls(_collection=collection, collection_name=collection.name)

    async def create_indexes(self) -> None:
        '''Create necessary indexes on the collection.'''
        await self._collection.create_index('file_hash', unique=True)
        await self._collection.create_index("path")

    async def check_exists(self, file_hash: str) -> bool:
        '''Check if a video file with the given hash already exists in the collection.'''
        # limit=1 ensures the scan stops the moment a match is found
        count = await self._collection.count_documents({'file_hash': file_hash}, limit=1)
        return count > 0
    
    async def find_created_at_by_hash(self, file_hash: str) -> datetime:
        '''Find the creation time of a VideoIndexDoc by its file_hash.'''
        doc = await self._collection.find_one({'file_hash': file_hash}, projection={'created_at': 1, '_id': 0})
        return datetime.fromisoformat(doc['created_at'])

    async def find_by_hash(self, file_hash: str) -> VideoIndexDoc:
        '''Find a VideoIndexDoc by its file_hash.'''
        doc = await self._collection.find_one({'file_hash': file_hash})
        if doc is None:
            raise VideoFileNotFoundError(f'Video file with hash not found: {file_hash}')
        return VideoIndexDoc.model_validate(doc) # Pydantic v2 model validation
    
    async def find_created_at_projection(self, path_prefix: pathlib.Path|str = '/') -> list[VideoIndexCreationTimeProjection]:
        '''Find the creation time of all VideoIndexDocs where the path starts with the given root_path.'''
        cursor = self._collection.find(
            {'path_str': {'$regex': f'^{re.escape(str(path_prefix))}'}}, 
            projection=VideoIndexCreationTimeProjection.projection()
        )
        results = []
        async for doc in cursor:
            results.append(VideoIndexCreationTimeProjection.from_proj_dict(doc)) # Pydantic v2 model validation
        return results

    async def find_by_prefix(self, root_path: pathlib.Path) -> list[VideoIndexDoc]:
        '''Find all VideoIndexDocs where the path starts with the given root_path.'''
        cursor = self._collection.find({'path_str': {'$regex': f'^{re.escape(str(root_path))}'}})
        docs = []
        async for doc in cursor:
            docs.append(VideoIndexDoc.model_validate(doc)) # Pydantic v2 model validation
        return docs
    
    async def find_first(self) -> Optional[VideoIndexDoc]:
        '''Get the first document in the collection.'''
        doc = await self._collection.find_one()
        if doc:
            return VideoIndexDoc.model_validate(doc) # Pydantic v2 model validation
        return None
    
    async def update_path(self, file_hash: str, new_path: pathlib.Path|str) -> None:
        '''Update the path of a VideoIndexDoc identified by its file_hash.'''
        result = await self._collection.update_one(
            {'file_hash': file_hash},
            {'$set': {'path_str': str(new_path)}}
        )
        if result.matched_count == 0:
            raise VideoFileNotFoundError(f'Video file with hash not found for update: {file_hash}')
    
    async def scan_recursive(self, mdir: MediaDir, verbose: bool = False) -> None:
        '''Recursively insert VideoIndexDocs for all video files in the given MediaDir.'''
        video_files = list(mdir.all_videos())
        if verbose:
            video_files = tqdm.tqdm(video_files, desc="Indexing videos", ncols=100)
        for vf in video_files:
            file_hash = index_hash_func(vf.path)
            if not await self.check_exists(file_hash):
                try:
                    video_doc = VideoIndexDoc.from_video_file_scan(vf, file_hash=file_hash)
                except ProbeError as e:
                    if verbose:
                        print(f"\nError probing video file {vf.path}: {e}")
                    continue
                else:
                    await self.insert(video_doc)
    
    async def insert(self, video_index_doc: VideoIndexDoc) -> None:
        '''Insert a VideoIndexDoc into the collection.'''
        await self._collection.insert_one(video_index_doc.model_dump())


class VideoIndexDoc(pydantic.BaseModel):
    path_str: str
    file_hash: str  # Unique index on hash of first MB
    probe: ProbeInfo
    stat: FileStatResult
    meta: dict[str, pydantic.JsonValue] = Field(default_factory=dict)
    thumb_path: str|None = None
    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_path_scan(cls, path: str, thumb_path: str|None = None) -> typing.Self:
        """Create a VideoIndexDoc from a file path."""
        video_file = VideoFile.from_path(path)
        file_hash = index_hash_func(video_file.path)
        return cls.from_video_file_scan(video_file, file_hash=file_hash, thumb_path=thumb_path)

    @classmethod
    def from_video_file_scan(cls, video_file: VideoFile, file_hash: str, thumb_path: str|None = None) -> typing.Self:
        """Create a VideoIndexDoc from a VideoFile instance."""
        meta = video_file.read_meta()
        return cls(
            file_hash=file_hash,
            path_str=str(video_file.path),
            probe=meta.probe,
            stat=meta.stat,
            meta=meta.meta,
            thumb_path=thumb_path
        )
        
    @property
    def tags(self) -> dict[str, str|int|float|bool|None]:
        '''Return the tags from the meta field, or an empty list if not present.'''
        return self.probe.tags
    

class VideoIndexCreationTimeProjection(BaseModel):
    file_hash: str
    path_str: str
    created_at_str: str

    @classmethod
    def from_proj_dict(cls, doc: dict) -> typing.Self:
        '''Create a VideoIndexCreationTimeProjection from a MongoDB document dict.'''
        return cls(
            file_hash=doc['file_hash'],
            path_str=doc['path_str'],
            created_at_str=doc['probe']['tags']['creation_time']
        )

    @staticmethod
    def projection() -> dict[str, int]:
        '''Return a MongoDB projection dict for this model.'''
        return {
            "file_hash": 1,
            "path_str": 1,
            "probe.tags.creation_time": 1,
            "_id": 0
        }
    
    @property
    def created_at(self) -> datetime:
        '''Parse the created_at_str into a datetime object.'''
        return datetime.fromisoformat(self.created_at_str)
    
    @property
    def path(self) -> pathlib.Path:
        '''Return the path_str as a pathlib.Path object.'''
        return pathlib.Path(self.path_str)
    
    