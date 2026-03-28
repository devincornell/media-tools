import dataclasses
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

Height = int
Width = int
FileName = str

@dataclasses.dataclass
class MediaDirIndexCollection:
    '''Interface for working with the media_dir_index collection.'''
    _collection: AsyncCollection

    @classmethod
    def from_collection(cls, collection: AsyncCollection) -> typing.Self:
        '''Create a MediaDirIndexCollection from a MongoDB collection.'''
        return cls(_collection=collection)

class IndexMediaFile(pydantic.BaseModel):
    '''Base class for indexed media files.'''
    path_str: str
    stat: FileStatResult

    def path_rel(self, relative_to: pathlib.Path) -> pathlib.Path:
        '''Get the relative file path of the indexed media file.'''
        return self.path.relative_to(pathlib.Path(relative_to))

    @property
    def name(self) -> str:
        '''Get the name of the indexed media file.'''
        return self.path.name
    
    @property
    def path(self) -> pathlib.Path:
        '''Get the absolute file path of the indexed media file.'''
        return pathlib.Path(self.path_str)
    
    

class IndexVideoFile(IndexMediaFile):
    '''Contains video name and hash for indexing purposes. Actual metadata stored in VideoFileIndex collection.'''
    file_hash: str
    
    @classmethod
    def from_path_scan(cls, path: pathlib.Path, file_hash: str) -> typing.Self:
        '''Create an IndexVideoFile from a file path.'''
        return cls(
            path_str=str(path),
            stat=FileStatResult.read_from_path(path),
            file_hash=file_hash
        )
    @classmethod
    def from_video_file_scan(cls, video_file: VideoFile, file_hash: str) -> typing.Self:
        '''Create an IndexVideoFile from a VideoFile instance.'''
        return cls(
            path_str=str(video_file.path),
            stat=FileStatResult.read_from_path(video_file.path),
            file_hash=file_hash
        )

class IndexImageFile(IndexMediaFile):
    '''Contains image name and stat metadata for tracking.'''
    res: typing.Tuple[int, int]

    @classmethod
    def from_path_scan(cls, path: pathlib.Path) -> typing.Self:
        '''Create an IndexImageFile from a file path.'''
        meta = ImageMeta.from_path(path)
        return cls(
            path_str=str(path),
            stat = FileStatResult.read_from_path(path),
            res=meta.res,
        )
    
    @classmethod
    def from_image_file_scan(cls, ifile: ImageFile) -> typing.Self:
        '''Create an IndexImageFile from an ImageFile instance.'''
        meta = ifile.read_meta()
        return cls(
            path_str=str(ifile.path),
            stat = FileStatResult.read_from_path(ifile.path),
            res=meta.res,
        )

class IndexOtherFile(IndexMediaFile):
    '''Contains non-media file for indexing purposes.'''

    @classmethod
    def from_path_scan(cls, path: pathlib.Path) -> typing.Self:
        '''Create an IndexOtherFile from a file path.'''
        return cls(
            path_str=str(path),
            stat=FileStatResult.read_from_path(path),
        )


class MediaDirIndexDoc(pydantic.BaseModel):
    path_str: str
    subpaths: dict[str, str]
    video_files: dict[FileName, IndexVideoFile]
    image_files: dict[FileName, IndexImageFile]
    other_files: dict[FileName, IndexOtherFile]
        
    @classmethod
    def from_media_dir_scan(cls, mdir: MediaDir) -> typing.Self:
        '''Scan the mediadir files to create a new instance.'''

        image_files: dict[str, IndexImageFile] = dict()
        for imf in mdir.images:
            try:
                index_imf = IndexImageFile.from_image_file_scan(imf)
                image_files[imf.path.name] = index_imf
            except PIL.UnidentifiedImageError:
                continue
            
        return cls(
            path_str=str(mdir.path),
            subpaths={sd.path.name:str(sd.path.relative_to(mdir.path)) for sd in mdir.subdirs.values()},
            video_files={vf.path.name: IndexVideoFile.from_video_file_scan(vf, index_hash_func(vf.path)) for vf in mdir.videos},
            image_files=image_files,
            other_files={of.path.name: IndexOtherFile.from_path_scan(of.path) for of in mdir.other_files},
        )
    
    @property
    def parent(self) -> pathlib.Path:
        '''Get the absolute path of the parent directory of the media directory index.'''
        return self.path.parent

    @property
    def path(self) -> pathlib.Path:
        '''Get the absolute path of the media directory index.'''
        return pathlib.Path(self.path_str)
        

