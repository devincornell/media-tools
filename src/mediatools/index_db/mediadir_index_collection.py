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

Height = int
Width = int
FileName = str

class MediaDirIndexNotFoundError(Exception):
    '''Raised when a media directory index document is not found in the database.'''
    pass

@dataclasses.dataclass
class MediaDirIndexCollection:
    '''Interface for working with the media_dir_index collection.'''
    _collection: AsyncCollection
    collection_name: str

    @classmethod
    def from_client(cls, client: pymongo.AsyncMongoClient, collection_name: str = "media_dir_index") -> typing.Self:
        '''Create a MediaDirIndexCollection from a MongoDB database.'''
        return cls.from_collection(collection=client[collection_name])

    @classmethod
    def from_collection(cls, collection: AsyncCollection) -> typing.Self:
        '''Create a MediaDirIndexCollection from a MongoDB collection.'''
        return cls(_collection=collection, collection_name=collection.name)

    async def create_indexes(self):
        '''Create a unique index on path_str to speed up prefix searches and upserts.'''
        await self._collection.create_index("path_str", unique=True)

    async def rescan_recursive(self, root_mdir: MediaDir, verbose: bool = False) -> None:
        '''Rescan all directories in the collection and update their index documents.'''
        await self.delete_by_path_prefix(root_mdir.path)
        return await self.scan_and_upsert_recursive(root_mdir, verbose=verbose)

    async def scan_and_upsert_recursive(self, mdir: MediaDir, verbose: bool = False) -> None:
        '''Scan a media directory and upsert the index document to the database.'''
        dirs = list(mdir.all_dirs())
        if verbose:
            dirs = tqdm.tqdm(dirs, desc="Scanning directories", ncols=100)
        for md in dirs:
            await self.scan_and_upsert(md)

    async def scan_and_upsert(self, mdir: MediaDir) -> None:
        '''Scan a media directory and upsert the index document to the database.'''
        index_doc = MediaDirIndexDoc.from_media_dir_scan(mdir)
        await self.upsert_directory(index_doc)

    async def upsert_directory(self, doc: MediaDirIndexDoc):
        """Update existing record by path_str or insert a new one."""
        await self._collection.replace_one(
            filter={"path_str": doc.path_str},
            replacement=doc.model_dump(), # Pydantic v2 dict conversion
            upsert=True
        )

    async def count(self, path_prefix: str | pathlib.Path | None = None) -> int:
        '''Return the number of documents in the collection. If path_prefix is provided, only counts documents where path_str starts with the given prefix.'''
        if path_prefix is None:
            return await self._collection.count_documents({})
        regex = re.compile(f"^{re.escape(str(path_prefix))}")
        return await self._collection.count_documents({"path_str": regex})

    async def find_first(self) -> Optional[MediaDirIndexDoc]:
        '''Get the first document in the collection.'''
        doc = await self._collection.find_one()
        if doc:
            return MediaDirIndexDoc.model_validate(doc) # Pydantic v2 model validation
        return None
    
    async def find_by_path(self, path: pathlib.Path) -> Optional[MediaDirIndexDoc]:
        '''Find a MediaDirIndexDoc by its path.'''
        doc = await self._collection.find_one({"path_str": str(path)})
        if doc:
            return MediaDirIndexDoc.model_validate(doc) # Pydantic v2 model validation
        raise MediaDirIndexNotFoundError(f'Media directory index not found for path: {path}')

    async def find_by_path_prefix(self, prefix: str | pathlib.Path) -> list[MediaDirIndexDoc]:
        '''Find all documents where path_str starts with the given prefix.'''
        prefix_str = str(prefix)
        
        # Use re.escape to handle paths with special regex characters
        # The '^' anchor ensures we only match the start of the string
        regex = re.compile(f"^{re.escape(prefix_str)}")
        
        cursor = self._collection.find({"path_str": regex})
        
        # Validate each document returned by the cursor
        return [MediaDirIndexDoc.model_validate(doc) async for doc in cursor]
    
    async def delete_by_path_prefix(self, prefix: str | pathlib.Path) -> int:
        '''Delete all documents where path_str starts with the given prefix. Returns the count of deleted documents.'''
        prefix_str = str(prefix)
        regex = re.compile(f"^{re.escape(prefix_str)}")
        result = await self._collection.delete_many({"path_str": regex})
        return result.deleted_count

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
            subpaths={str(sd.path.relative_to(mdir.path)):str(sd.path) for sd in mdir.subdirs.values()},
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
        
    def __repr__(self) -> str:
        return f"<MediaDirIndexDoc path={self.path_str} videos={len(self.video_files)} images={len(self.image_files)} other_files={len(self.other_files)}>"
