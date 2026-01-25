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

#import sys
#sys.path.append('../src')
#sys.path.append('src')
#import mediatools
#import util
from ..mediadir import MediaDir
from .media_dir_index import MediaDirIndex
from .video_file_index import VideoFileIndex




@dataclasses.dataclass
class MediaSiteIndexDB:
    '''Interface for working with media site index collections.'''
    db_name: str
    url: str = "mongodb://localhost:27017"
    video_index: typing.Type[VideoFileIndex] = VideoFileIndex
    dir_index: typing.Type[MediaDirIndex] = MediaDirIndex

    async def init(self) -> None:
        await init_beanie_models(self.url, self.db_name)

    async def insert_from_media_dirs(self, mdir: MediaDir, verbose: bool = False) -> None:
        '''Insert media directories and video files from a MediaDir instance into the database.
        '''
        await self.video_index.insert_video_files(mdir.all_videos(), verbose=verbose)
        await self.dir_index.insert_media_dirs(mdirs=mdir.all_dirs(), verbose=verbose)

    async def find_all_dirs(self) -> list[MediaDirIndex]:
        '''Find all media directory indexes in the database.'''
        return await self.dir_index.find_all().to_list()



async def init_beanie_models(url: str, db_name: str) -> None:
    """Initialize Beanie with all document models for the specified database."""
    client = await get_database_client(url=url)
        
    await init_beanie(
        database=client[db_name],
        document_models=[VideoFileIndex, MediaDirIndex],  # Add more models here as you create them
    )

async def close_database_connection():
    """Close the MongoDB connection. Call this on app shutdown."""
    global _client
    if _client:
        _client.close()
        _client = None

# Store client as module-level variable for reuse
_client: Optional[pymongo.AsyncMongoClient] = None

async def get_database_client(url: str) -> pymongo.AsyncMongoClient:
    """Get or create the MongoDB client singleton."""
    global _client
    if _client is None:
        _client = pymongo.AsyncMongoClient(url)
    return _client

