import dataclasses
from typing import List, Optional
from datetime import datetime
import typing
#from beanie import Document, Indexed, Link
import beanie
import beanie.exceptions
import fastapi
from pydantic import Field, BaseModel
import pymongo
import pymongo.errors
import asyncio
from beanie import init_beanie
import os
import typing
import tqdm
import random
import pydantic
import pathlib
from beanie.operators import Set
from pathlib import Path
import contextlib

#import sys
#sys.path.append('../src')
#sys.path.append('src')
#import mediatools
#import util
from ...mediadir import MediaDir
from .media_dir_index import MediaDirIndex
from .video_file_index import VideoFileIndex




@dataclasses.dataclass
class MediaSiteIndexDB:
    '''Interface for working with media site index collections.'''
    db_name: str
    url: str = "mongodb://localhost:27017"
    video_index: typing.Type[VideoFileIndex] = VideoFileIndex
    dir_index: typing.Type[MediaDirIndex] = MediaDirIndex

    async def init(self) -> pymongo.AsyncMongoClient:
        '''DEPRICATED. Use .lifespan() instead. Initialize the database connection and Beanie models.'''
        return await self._init_beanie_models()

    @contextlib.asynccontextmanager
    async def lifespan(self, app: fastapi.FastAPI|None = None):
        '''Lifespan context manager to initialize and close the database connection. For use with or outside FastAPI apps.'''
        client = await self._init_beanie_models()
        yield
        await client.close()

    async def _init_beanie_models(self) -> pymongo.AsyncMongoClient:
        '''Initialize Beanie with the specified MongoDB URL and database name.'''
        client = pymongo.AsyncMongoClient(self.url)
        await init_beanie(
            database=client[self.db_name],
            document_models=[VideoFileIndex, MediaDirIndex],  # Add more models here as you create them
        )
        return client

    async def insert_from_media_dir(self, mdir: MediaDir, verbose: bool = False) -> None:
        '''Insert media directories and video files recursively from a MediaDir instance into the database.
        '''
        await self.video_index.insert_video_files(mdir.all_videos(), verbose=verbose)
        await self.dir_index.upsert_media_dirs(mdirs=mdir.all_dirs(), verbose=verbose)

    async def find_all_dirs(self) -> list[MediaDirIndex]:
        '''Find all media directory indexes in the database.'''
        return await self.dir_index.find_all().to_list()
