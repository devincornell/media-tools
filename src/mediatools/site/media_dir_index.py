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
from PIL import Image


from ..util import format_memory, fname_to_title, fname_to_id, format_time
from ..mediadir import MediaDir

from .video_file_index import VideoFileIndex
from ..util import get_hash_firstlast_hex
from ..file_stat_result import FileStatResult
from ..images import ImageMeta, ImageFile

Height = int
Width = int
FileName = str


class IndexMediaFile(pydantic.BaseModel):
    '''Base class for indexed media files.'''
    _path_abs: str

    @property
    def name(self) -> str:
        '''Get the name of the indexed media file.'''
        return pathlib.Path(self._path_abs).name
    
    @property
    def path_abs(self) -> pathlib.Path:
        '''Get the absolute file path of the indexed media file.'''
        return pathlib.Path(self._path_abs)
    
    def path_rel(self, relative_to: pathlib.Path) -> pathlib.Path:
        '''Get the relative file path of the indexed media file.'''
        return pathlib.Path(self._path_abs).relative_to(pathlib.Path(relative_to))
    

class IndexVideoFile(IndexMediaFile):
    '''Contains video name and hash for indexing purposes. Actual metadata stored in VideoFileIndex collection.'''
    hash_firstlast1kb: str

    async def get_video_file_index(self) -> VideoFileIndex:
        '''Get the VideoFileIndex document for this indexed video file.'''
        return await VideoFileIndex.find_by_hash(self.hash_firstlast1kb)

class IndexImageFile(IndexMediaFile):
    '''Contains image name and stat metadata for tracking.'''
    meta: ImageMeta

    @classmethod
    def from_path(cls, path: pathlib.Path) -> typing.Self:
        '''Create an IndexImageFile from a file path.'''
        return cls(
            _path_abs=str(path),
            meta=ImageMeta.from_path(path),
        )
    
    @classmethod
    def from_image_file(cls, ifile: ImageFile) -> typing.Self:
        '''Create an IndexImageFile from an ImageFile instance.'''
        return cls(
            _path_abs=str(ifile.path),
            meta=ifile.read_meta(),
        )
            
    def template_dict(self) -> dict[str, str|int|float]:
        '''Get a dictionary of template variables for this image file.'''
        return {
            'name': self.name,
            'width': self.meta.res[0],
            'height': self.meta.res[1],
            'aspect_ratio': self.meta.res[0]/self.meta.res[1],
            'size': self.meta.stat.size,
            'size_str': format_memory(self.meta.stat.size),
        }

class IndexOtherFile(IndexMediaFile):
    '''Contains non-media file for indexing purposes.'''
    pass

class MediaDirIndex(beanie.Document):
    class Settings:
        name = "media_dir_index"  # The collection name in MongoDB
    _path_abs: beanie.Indexed(str, unique=True)
    subpaths_rel: dict[str, str]
    video_files: dict[FileName, IndexVideoFile]
    image_files: dict[FileName, IndexImageFile]
    other_files: dict[FileName, IndexOtherFile]
    
    @classmethod
    async def insert_media_dirs(cls, mdirs: list[MediaDir], verbose: bool = False) -> None:
        '''Insert multiple MediaDir instances into the database. Typically you could use MediaDir.scan_directory() to 
            get the list of MediaDir instances.
        '''
        if verbose:
            mdirs = tqdm.tqdm(mdirs, ncols=80)
        for mdir in mdirs:
            mdi = MediaDirIndex.from_media_dir(mdir)
            await cls.find_one(cls._path_abs == mdi._path_abs).upsert(
                Set(mdi.model_dump()),
                on_insert=mdi
            )
    
    @classmethod
    def from_media_dir(cls, mdir: MediaDir) -> typing.Self:
        '''Create a MediaDirIndex from a MediaDir instance. The root_path is used to compute relative paths.'''
        return cls(
            _path_abs=str(mdir.path),
            subpaths_rel={sd.path.name:str(sd.path.relative_to(mdir.path)) for sd in mdir.subdirs.values()},
            video_files={vf.path.name: IndexVideoFile(
                _path_abs=str(vf.path),
                hash_firstlast1kb=get_hash_firstlast_hex(vf.path, chunk_size=1024)
            ) for vf in mdir.videos},
            image_files={imf.path.name: IndexImageFile.from_image_file(
                imf
            ) for imf in mdir.images},
            other_files={of.path.name: IndexOtherFile(
                _path_abs=str(of.path)
            ) for of in mdir.other_files},
        )
    
    @property
    def parent(self) -> pathlib.Path:
        '''Get the absolute path of the parent directory of the media directory index.'''
        return self.path_abs.parent

    @property
    def path_abs(self) -> pathlib.Path:
        '''Get the absolute path of the media directory index.'''
        return pathlib.Path(self._path_abs)
        
    @classmethod
    async def fetch_by_abs_path(cls, path_abs: str|Path) -> Optional[typing.Self]:
        '''Get a MediaDirIndex document by its absolute path.
        '''
        return await cls.find_one(cls._path_abs == str(path_abs))

    async def fetch_video_metas(self) -> List[VideoFileIndex]:
        '''Get the VideoMeta documents for the video files in this media directory index.
        '''
        vid_metas = []
        for ivf in self.video_files.values():
            vid_metas.append(await ivf.get_video_file_index())
        return vid_metas

    async def fetch_subdir_indexes(self) -> List[typing.Self]:
        '''Get the MediaDirIndex documents for the subdirectories of this media directory index.
        '''
        subdir_indexes = []
        for sp_rel in self.subpaths_rel.keys():
            mdi = await MediaDirIndex.fetch_by_rel_path(sp_rel)
            if mdi:
                subdir_indexes.append(mdi)
        return subdir_indexes
    
    async def fetch_parent_index(self) -> Optional[typing.Self]:
        '''Get the MediaDirIndex document for the parent directory of this media directory index.
        '''
        return await MediaDirIndex.fetch_by_abs_path(self.parent_abs)

    async def template_dict(self) -> dict[str, str|int|float|dict]:
        '''Get a dictionary of template variables for this media directory index.
        '''
        video_metas = await self.fetch_video_metas()
        return {
            'path_abs': self.path_abs,

            'videos': [vi.template_dict() for vi in video_metas],
            'num_videos': len(self.video_files),

            'images': [imf.template_dict() for imf in self.image_files.values()],
            'num_images': len(self.image_files),
            
            'num_other_files': len(self.other_files),
            'num_subdirs': len(self.subpaths_rel),
        }

