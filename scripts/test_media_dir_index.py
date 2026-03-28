import typing
import pathlib
import asyncio
from datetime import datetime
import re
import sys
import collections
from pathlib import Path
import dataclasses
import pymongo
import tqdm

sys.path.append('../src')
sys.path.append('src')
import mediatools
#import util

from pymongo import AsyncMongoClient

import contextlib



async def main():
    # 1. Configuration
    mongo_uri = "mongodb://127.0.0.1:27017/?directConnection=true"
    db_name = "media_archive"
    # Change this to the actual directory you want to scan
    library_path = Path("/mnt/HugeHDD/gopro/gopro_raw_organized/") 
    

    # 2. Setup Database Connection
    async with AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=2000) as client:
        mdir_index = mediatools.MediaDirIndexCollection.from_db(client[db_name])
        video_index = mediatools.VideoIndexCollection.from_db(client[db_name])
        print(type(await mdir_index.find_first()))
        print(await video_index.find_first())
        print(f'Connected to MongoDB at {mongo_uri}')
        
        # Initialize your custom collection interface

        # 3. Load and Scan the Media Directory
        print(f"--- Starting scan of {library_path} ---")
        mdir = mediatools.MediaDir.from_path(library_path)

        
        print(f"Scanning media directory: {library_path}")
        await mdir_index.scan_and_upsert_recursive(mdir, verbose=True)
        for vf in tqdm.tqdm(mdir.all_videos(), desc="Indexing videos", ncols=100):
            video_doc = mediatools.VideoIndexDoc.from_video_file_scan(vf, mediatools.index_hash_func(vf.path))
            await video_index.insert(video_doc)




        md_inds = await mdir_index.find_by_path_prefix('/mnt/HugeHDD/gopro/gopro_raw_organized/2025-11-28')
        for md_ind in md_inds:
            print(md_ind.path_str)
            print(f"  {len(md_ind.video_files)} videos, {len(md_ind.image_files)} images")
            for vi in md_ind.video_files.values():
                print(f"    Video: {vi.path.name}, {vi.stat.modified_at}, {vi.stat.size_str()}")

        # This triggers your classmethod logic to build the Pydantic model
        #index_doc = mediatools.MediaDirIndexDoc.from_media_dir_scan(mdir)
        
        # 4. Save to MongoDB
        #print(f"Found {len(index_doc.video_files)} videos and {len(index_doc.image_files)} images.")
        #print("Uploading index to database...")
        #await media_indices.upsert_directory(index_doc)
        
        print("Success! Directory index is up to date.")


if __name__ == "__main__":
    # The entry point for the asyncio event loop
    asyncio.run(main())