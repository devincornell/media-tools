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


import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util

class HashProjection(BaseModel):
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

class VideoInfo(beanie.Document):
    class Settings:
        name = "videofile_info"  # The collection name in MongoDB
    path: str
    hash_firstmb: beanie.Indexed(str, unique=True)  # Unique index on hash of first MB
    probe: mediatools.ffmpeg.ProbeInfo = None
    stat: FileStatInfo = None
    created_at: datetime = Field(default_factory=datetime.now)


    @classmethod
    def from_path(cls, path: str) -> typing.Self:
        """Create a VideoInfo from a file path."""
        video_file = mediatools.video.VideoFile.from_path(path)
        return cls.from_video_file(video_file)

    @classmethod
    def from_video_file(cls, video_file: mediatools.video.VideoFile) -> typing.Self:
        """Create a VideoInfo from a VideoFile instance."""
        return cls(
            hash_firstmb=util.get_hash_firstmb_hex(video_file.path),
            path=str(video_file.path),
            probe=video_file.probe(),
            stat=FileStatInfo.from_file_stat(os.stat(video_file.path))
        )

    @classmethod
    async def find_by_hash(cls, hash_firstmb: str) -> Optional[typing.Self]:
        """Find a VideoInfo by its hash_firstmb."""
        return await cls.find_one(cls.hash_firstmb == hash_firstmb)
    
    @classmethod
    async def insert_video_files(cls, video_files: list[mediatools.video.VideoFile], verbose: bool = False) -> None:
        '''Insert multiple VideoFile instances into the database. Typically you could use MediaDir.all_videos() to 
            get the list of VideoFile instances.
        '''
        exist_hashes = await cls.find_all().project(HashProjection).to_list()
        exist_hashes = {et.hash_firstmb for et in exist_hashes}
        if verbose: print(f'Existing hashes in DB: {len(exist_hashes)}')

        for vf in tqdm.tqdm(video_files):
            if util.get_hash_firstmb_hex(vf.path) not in exist_hashes:
                try:
                    vfd = cls.from_video_file(vf)
                    await vfd.insert()
                    exist_hashes.add(vfd.hash_firstmb)
                except mediatools.ffmpeg.ProbeError as e:
                    if verbose: print(f'\nError probing file {vf.path}: {e}\n')

class IndexVideoFile(pydantic.BaseModel):
    name: str
    hash_firstmb: str

class IndexImageFile(pydantic.BaseModel):
    name: str

class IndexOtherFile(pydantic.BaseModel):
    name: str

class MediaDirIndex(beanie.Document):
    class Settings:
        name = "mediadir_index"  # The collection name in MongoDB
    path_rel: beanie.Indexed(str, unique=True)
    path_abs: beanie.Indexed(str, unique=True)
    subpaths_rel: List[str]
    video_files: List[IndexVideoFile]
    image_files: List[IndexImageFile]
    other_files: List[IndexOtherFile]

    @classmethod
    def from_media_dir(cls, mdir: mediatools.MediaDir, root_path: pathlib.Path) -> typing.Self:
        '''Create a MediaDirIndex from a MediaDir instance. The root_path is used to compute relative paths.'''
        return cls(
            path_rel=str(mdir.path.relative_to(root_path)),
            path_abs=str(mdir.path),
            subpaths_rel=[str(sd.path.relative_to(mdir.path)) for sd in mdir.subdirs.values()],
            video_files=[IndexVideoFile(name=vf.path.name, hash_firstmb=util.get_hash_firstmb_hex(vf.path)) for vf in mdir.videos],
            image_files=[IndexImageFile(name=imf.path.name) for imf in mdir.images],
            other_files=[IndexOtherFile(name=of.path.name) for of in mdir.other_files],
        )
    
    @classmethod
    async def insert_media_dirs(cls, mdirs: list[mediatools.MediaDir], root_path: pathlib.Path, verbose: bool = False) -> None:
        '''Insert multiple MediaDir instances into the database. Typically you could use MediaDir.scan_directory() to 
            get the list of MediaDir instances.
        '''
        for mdir in mdirs:
            if verbose:
                print(f'Scanning dir: {mdir.path}')
            mdi = MediaDirIndex.from_media_dir(mdir, root_path)
            from beanie.operators import Set
            await cls.find_one(cls.path_rel == mdi.path_rel).upsert(
                Set(mdi.model_dump()),
                on_insert=mdi
            )
            if verbose:
                print(f'Inserted/updated dir: {mdir.path}')

    async def get_video_infos(self) -> List[VideoInfo]:
        '''Get the VideoInfo documents for the video files in this media directory index.
        '''
        vid_infos = []
        for ivf in self.video_files:
            vi = await VideoInfo.find_by_hash(ivf.hash_firstmb)
            vid_infos.append(vi)
        return vid_infos

    async def get_subdir_indexes(self) -> List[typing.Self]:
        '''Get the MediaDirIndex documents for the subdirectories of this media directory index.
        '''
        subdir_indexes = []
        for sp_rel in self.subpaths_rel:
            mdi = await MediaDirIndex.find_one(MediaDirIndex.path_rel == sp_rel)
            if mdi:
                subdir_indexes.append(mdi)
        return subdir_indexes

async def init_db(db_name: str) -> None:
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await init_beanie(
        database=client[db_name],
        document_models=[VideoInfo, MediaDirIndex]
    )

async def main():
    await init_db("dwhost")

    if False:
        mdir = mediatools.scan_directory('/mnt/HDDStorage/sys/dwhelper/')
        print(len(mdir.all_videos()))
        await VideoInfo.insert_video_files(mdir.all_videos(), verbose=True)

    if False:
        all_vfs = mediatools.scan_directory('/mnt/HDDStorage/sys/dwhelper/').all_videos()
        random.shuffle(all_vfs)
        video_files = [(vf,util.get_hash_firstmb_hex(vf.path)) for vf in all_vfs[:1000]]

        start = datetime.now()
        for vf, h in tqdm.tqdm(video_files):
            vfd = await VideoInfo.find_by_hash(h)
        print(f'Query took: {datetime.now()-start}')
        start = datetime.now()
        for vf,h in tqdm.tqdm(video_files):
            vfd = VideoInfo.from_path(vfd.path)
        print(f'Loading VideoFile took: {datetime.now()-start}')
        #print(vfd)

    if True:
        await MediaDirIndex.delete_all()
        root_path = pathlib.Path('/mnt/HDDStorage/sys/dwhelper/pros/rilynn_rae')
        all_dirs = mediatools.scan_directory(root_path).all_dirs()
        await MediaDirIndex.insert_media_dirs(all_dirs, root_path, verbose=True)

        all_index_dirs = await MediaDirIndex.find_all().to_list()
        for mdi in all_index_dirs:
            print(f'Dir: {mdi.path_rel}, Videos: {len(mdi.video_files)}')
            video_infos = await mdi.get_video_infos()
            for vi in video_infos:
                if vi is not None:
                    print(f'  Video: {pathlib.Path(vi.path).name}, Size: {vi.stat.size}')
            #print(sum([vi.stat.size for vi in video_infos if vi is not None]))

            subdir_indexes = await mdi.get_subdir_indexes()
            for sdi in subdir_indexes:
                print(f'  Subdir: {sdi.path_rel}, Videos: {len(sdi.video_files)}')

if __name__ == "__main__":
    asyncio.run(main())
