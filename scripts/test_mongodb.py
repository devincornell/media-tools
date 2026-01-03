from typing import List, Optional
from datetime import datetime
import typing
from beanie import Document, Indexed
from pydantic import Field, BaseModel
import pymongo
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import os
import typing
import tqdm

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util

class ProjectHash(BaseModel):
    hash_firstmb: str


class FileStatInfo(BaseModel):
    """Commonly used attributes from a file stat call."""
    size: int = Field(..., description="Size of the file in bytes")
    
    # Timestamps
    modified_at: datetime = Field(..., )
    accessed_at: datetime = Field(...)
    created_at: datetime = Field(...)
    
    # System identifiers
    mode: int = Field(..., description="File protection mode")
    inode: int = Field(..., description="Inode number")

    @classmethod
    def from_file_stat(cls, stat: os.stat_result) -> typing.Self:        
        return cls(
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            accessed_at=datetime.fromtimestamp(stat.st_atime),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            mode=stat.st_mode,
            inode=stat.st_ino,
        )

class VideoFileDoc(Document):
    path: str
    hash_firstmb: Indexed(str, unique=True)  # Unique index on hash of first MB
    probe: mediatools.ffmpeg.ProbeInfo = None
    stat: FileStatInfo = None
    created_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "video_files"  # The collection name in MongoDB

    @classmethod
    def from_video_file(cls, video_file: mediatools.video.VideoFile) -> "VideoFileDoc":
        """Create a VideoFileDoc from a VideoFile instance."""
        return cls(
            hash_firstmb=util.get_hash_firstmb_hex(video_file.path),
            path=str(video_file.path),
            probe=video_file.probe(),
            stat=FileStatInfo.from_file_stat(os.stat(video_file.path))
        )

async def init_db():
    # 1. Create the Motor (async) client
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    
    # 2. Initialize Beanie with the database and your document models
    await init_beanie(
        database=client.dwhost,
        document_models=[VideoFileDoc]
    )

async def main():
    await init_db()

    mdir = mediatools.scan_directory('/mnt/HDDStorage/sys/dwhelper/')
    print(len(mdir.all_videos()))

    exist_hashes = await VideoFileDoc.find_all().project(ProjectHash).to_list()
    exist_hashes = {et.hash_firstmb for et in exist_hashes}
    print(f'Existing hashes in DB: {len(exist_hashes)}')

    for vf in tqdm.tqdm(mdir.all_videos()):
        if util.get_hash_firstmb_hex(vf.path) not in exist_hashes:
            try:
                vfd = VideoFileDoc.from_video_file(vf)
                await vfd.insert()
                exist_hashes.add(vfd.hash_firstmb)
            except mediatools.ffmpeg.ProbeError as e:
                print(f'\nError probing file {vf.path}: {e}\n')

if __name__ == "__main__":
    asyncio.run(main())
