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


from .mediadir_index_collection import MediaDirIndexCollection, MediaDirIndexDoc
from .video_index_collection import VideoIndexCollection, VideoIndexDoc

@dataclasses.dataclass
class MediaIndexDirInfo:
    '''Contains index data about a directory, it's subdirectories, and video files.'''
    dir: MediaDirIndexDoc
    subdirs: List[MediaDirIndexDoc]
    videos: List[VideoIndexDoc]


@dataclasses.dataclass(repr=False)
class MediaIndexDB:
    dirs: MediaDirIndexCollection
    videos: VideoIndexCollection

    @classmethod
    async def from_client(cls, 
        client: pymongo.AsyncMongoClient, 
        dirs_index_name: str = 'media_dir_index', 
        video_index_name: str = 'video_file_index'
    ) -> typing.Self:
        '''Create a MediaIndex from a MongoDB database.'''
        o = cls(
            dirs=MediaDirIndexCollection.from_client(client, collection_name=dirs_index_name),
            videos=await VideoIndexCollection.from_client(client, collection_name=video_index_name)
        )
        await o.create_indexes() # Ensure indexes are created before use
        return o
    
    async def create_indexes(self) -> None:
        '''Create necessary indexes on the collections.'''
        await self.dirs.create_indexes()
        await self.videos.create_indexes()

    async def update_directory_index(self, path: pathlib.Path, verbose: bool = False) -> None:
        '''Scan a single directory and update the index.'''
        mdir = MediaDir.from_path(path)
        await self.dirs.rescan_recursive(mdir, verbose=verbose)
        await self.videos.scan_recursive(mdir, verbose=verbose)

    async def clear_directory_index(self, path_prefix: pathlib.Path) -> None:
        '''Delete all index documents for directories and videos under the given path prefix.'''
        await self.dirs.delete_by_path_prefix(path_prefix)

    async def rescan_recursive(self, root_mdir: MediaDir, verbose: bool = False) -> None:
        '''Rescan all directories in the collection and update their index documents.'''
        await self.dirs.rescan_recursive(root_mdir, verbose=verbose)
        await self.videos.scan_recursive(root_mdir, verbose=verbose)

    async def find_media_dir(self, path: pathlib.Path) -> Optional[MediaDirIndexDoc]:
        '''Find a MediaDirIndexDoc by its path.'''
        root_dir = await self.dirs.find_by_path(path)
        root_dir.subpaths

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(dirs={self.dirs}, videos={self.videos})"




