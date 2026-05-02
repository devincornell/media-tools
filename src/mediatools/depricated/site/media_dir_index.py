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
from beanie import init_beanie
import os
import typing
import tqdm
import random
import pydantic
import pathlib
import beanie.operators
from pathlib import Path
from PIL import Image
import PIL


from ...util import format_memory, fname_to_title, fname_to_id, format_time
from ...mediadir import MediaDir

from ...util import get_hash_firstlast_hex
from ...file_stat_result import FileStatResult
from ...images import ImageMeta, ImageFile


from .video_file_index import VideoFileIndex

Height = int
Width = int
FileName = str


class IndexMediaFile(pydantic.BaseModel):
    '''Base class for indexed media files.'''
    path_abs_str: str

    @property
    def name(self) -> str:
        '''Get the name of the indexed media file.'''
        return pathlib.Path(self.path_abs_str).name
    
    @property
    def path_abs(self) -> pathlib.Path:
        '''Get the absolute file path of the indexed media file.'''
        return pathlib.Path(self.path_abs_str)
    
    def path_rel(self, relative_to: pathlib.Path) -> pathlib.Path:
        '''Get the relative file path of the indexed media file.'''
        return pathlib.Path(self.path_abs_str).relative_to(pathlib.Path(relative_to))
    

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
            path_abs_str=str(path),
            meta=ImageMeta.from_path(path),
        )
    
    @classmethod
    def from_image_file(cls, ifile: ImageFile) -> typing.Self:
        '''Create an IndexImageFile from an ImageFile instance.'''
        return cls(
            path_abs_str=str(ifile.path),
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
    path_abs_str: beanie.Indexed(str, unique=True)
    subpaths_rel: dict[str, str]
    video_files: dict[FileName, IndexVideoFile]
    image_files: dict[FileName, IndexImageFile]
    other_files: dict[FileName, IndexOtherFile]
    
    @classmethod
    async def upsert_media_dirs(cls, mdirs: list[MediaDir], verbose: bool = False) -> None:
        '''Insert multiple MediaDir instances into the database. Typically you could use MediaDir.scan_directory() to 
            get the list of MediaDir instances.
        '''
        if verbose:
            mdirs = tqdm.tqdm(mdirs, ncols=80)
        for mdir in mdirs:
            mdi = MediaDirIndex.from_media_dir(mdir)
            await cls.find_one(cls.path_abs_str == str(mdir.path)).upsert(
                beanie.operators.Set(mdi.model_dump()),
                on_insert=mdi
            )
    
    @classmethod
    def from_media_dir(cls, mdir: MediaDir) -> typing.Self:
        '''Create a MediaDirIndex from a MediaDir instance. The root_path is used to compute relative paths.'''

        image_files: dict[str, IndexImageFile] = dict()
        for imf in mdir.images:
            try:
                index_imf = IndexImageFile.from_image_file(imf)
                image_files[imf.path.name] = index_imf
            except PIL.UnidentifiedImageError:
                continue
            
        return cls(
            path_abs_str=str(mdir.path),
            subpaths_rel={sd.path.name:str(sd.path.relative_to(mdir.path)) for sd in mdir.subdirs.values()},
            video_files={vf.path.name: IndexVideoFile(
                path_abs_str=str(vf.path),
                hash_firstlast1kb=get_hash_firstlast_hex(vf.path, chunk_size=1024)
            ) for vf in mdir.videos},
            image_files=image_files,
            other_files={of.path.name: IndexOtherFile(
                path_abs_str=str(of.path)
            ) for of in mdir.other_files},
        )
    
    @property
    def parent_path(self) -> pathlib.Path:
        '''Get the absolute path of the parent directory of the media directory index.'''
        return self.path_abs.parent

    @property
    def path_abs(self) -> pathlib.Path:
        '''Get the absolute path of the media directory index.'''
        return pathlib.Path(self.path_abs_str)
        
    @classmethod
    async def fetch_by_abs_path(cls, path_abs: str|Path) -> Optional[typing.Self]:
        '''Get a MediaDirIndex document by its absolute path.
        '''
        di = await cls.find_one(cls.path_abs_str == str(path_abs))
        if di is None:
            raise ValueError(f'MediaDirIndex not found for path: {path_abs}')
        return di

    async def fetch_video_metas(self) -> List[tuple[IndexVideoFile, VideoFileIndex]]:
        '''Get the VideoMeta documents for the video files in this media directory index.
        '''
        vid_metas = []
        for ivf in self.video_files.values():
            vid_metas.append((ivf, await ivf.get_video_file_index()))
        return vid_metas

    async def fetch_subdir_indexes(self, error_on_missing: bool = True) -> List[typing.Self]:
        '''Get the MediaDirIndex documents for the subdirectories of this media directory index.
        '''
        subdir_indexes = []
        for subpath_name in self.subpaths_rel.keys():
            mdi = await self.__class__.fetch_by_abs_path(self.path_abs / subpath_name)
            if mdi:
                subdir_indexes.append(mdi)
            elif error_on_missing:
                raise ValueError(f'Subdirectory MediaDirIndex not found for path: {subpath_name}')
                
        return subdir_indexes
    
    async def fetch_parent_index(self) -> Optional[typing.Self]:
        '''Get the MediaDirIndex document for the parent directory of this media directory index.
        '''
        return await self.__class__.fetch_by_abs_path(self.parent_path)

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

