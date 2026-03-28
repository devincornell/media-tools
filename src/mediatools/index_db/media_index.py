from __future__ import annotations
import dataclasses
import re
from typing import List, Optional
from datetime import datetime
import typing
import asyncio
import os
import typing
import tqdm
import random
import pydantic
import pathlib
from pathlib import Path
from PIL import Image
import PIL

import pymongo
import pymongo.errors
from pymongo.asynchronous.collection import AsyncCollection

from .util import index_hash_func
from ..mediadir import MediaDir

from ..file_stat_result import FileStatResult
from ..images import ImageMeta, ImageFile
from ..video import VideoFile, VideoMeta


from .media_dir_index import MediaDirIndexCollection, MediaDirIndexDoc
from .video_index import VideoIndexCollection, VideoIndexDoc

@dataclasses.dataclass
class MediaIndexDirInfo:
    '''Contains index data about a directory, it's subdirectories, and video files.'''
    dir: MediaDirIndexDoc
    subdirs: List[MediaDirIndexDoc]
    videos: List[VideoIndexDoc]


@dataclasses.dataclass
class MediaIndex:
    mdir_index: MediaDirIndexCollection
    video_index: VideoIndexCollection

    @classmethod
    async def from_client(cls, 
        client: pymongo.AsyncMongoClient, 
        mdir_index_name: str = 'media_dir_index', 
        video_index_name: str = 'video_file_index'
    ) -> typing.Self:
        '''Create a MediaIndex from a MongoDB database.'''
        o = cls(
            mdir_index=MediaDirIndexCollection.from_client(client, collection_name=mdir_index_name),
            video_index=await VideoIndexCollection.from_client(client, collection_name=video_index_name)
        )
        await o.create_indexes() # Ensure indexes are created before use
        return o
    
    async def create_indexes(self) -> None:
        '''Create necessary indexes on the collections.'''
        await self.mdir_index.create_indexes()
        await self.video_index.create_indexes()

    async def rescan_recursive(self, root_mdir: MediaDir, verbose: bool = False) -> None:
        '''Rescan all directories in the collection and update their index documents.'''
        await self.mdir_index.rescan_recursive(root_mdir, verbose=verbose)
        await self.video_index.scan_recursive(root_mdir, verbose=verbose)

    async def find_media_dir(self, path: pathlib.Path) -> Optional[MediaDirIndexDoc]:
        '''Find a MediaDirIndexDoc by its path.'''
        root_dir = await self.mdir_index.find_by_path(path)
        root_dir.subpaths




