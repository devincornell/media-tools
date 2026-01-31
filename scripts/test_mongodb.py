import pathlib
import asyncio
from datetime import datetime
import re
import sys
import collections

import tqdm

sys.path.append('../src')
sys.path.append('src')
import mediatools
#import util

#from mediatools.site import MediaDirIndexDB, MediaDirIndex, IndexVideoFile, IndexImageFile, IndexOtherFile, VideoInfo, init_db



async def main():
    #await init_db("dwhost")
    db = mediatools.MediaSiteIndexDB(db_name="dwhost", url='mongodb://localhost:32768/?directConnection=true')
    #await db.init()
    print('initialized database')

    async with db.lifespan():
        if True:
            # add files to the database
            root_path = pathlib.Path('/mnt/HDDStorage/')
            mdir = mediatools.scan_directory(root_path)
        if False:
            hash_fnames = collections.defaultdict(set)
            for vf in tqdm.tqdm(mdir.all_video_files(), ncols=80):
                #h = util.get_hash_hex(vf.path, chunk_size=4096, max_chunks=1000)
                h = mediatools.util.get_hash_firstlast_hex(vf.path)
                hash_fnames[h].add(vf.path)

            for h, fnames in sorted(hash_fnames.items(), key=lambda item: len(item[1]), reverse=False):
                if len(fnames) > 1:
                    print(f'Hash {h} occurs {len(fnames)} times:')
                    for fn in fnames:
                        print(f'  {fn}')
            print(len(hash_fnames))

        if True:
            await db.insert_from_media_dir(mdir, verbose=True)
            #vfis = await db.video_index.find(db.video_index.path==re.compile(f"^{re.escape(str(root_path))}")).to_list()
            di = await db.dir_index.fetch_by_abs_path('/mnt/HDDStorage/sys/dwhelper/creators/_Greatest')
            subdir_indexes = await di.fetch_subdir_indexes()
            for sdi in subdir_indexes:
                print(f'Subdir: {sdi.path_abs}, Videos: {len(sdi.video_files)}')
            #subdir_indexes = await di.fetch_subdir_indexes()
            #print(f'Found {len(vfis)} video files in database under {root_path}')
        
        if False:
            for vf in tqdm.tqdm(mdir.all_video_files(), ncols=80):
                #print(f'Video file: {vf.path}')
                try:
                    vfi = await db.video_index.find_or_add_from_path(vf.path)
                except mediatools.ffmpeg.ProbeError as e:
                    pass


    if False:
        all_vfs = mediatools.scan_directory('/mnt/HDDStorage/sys/dwhelper/').all_videos()
        random.shuffle(all_vfs)
        video_files = [(vf,mediatools.util.get_hash_firstmb_hex(vf.path)) for vf in all_vfs[:1000]]

        start = datetime.now()
        for vf, h in tqdm.tqdm(video_files):
            vfd = await VideoInfo.find_by_hash(h)
        print(f'Query took: {datetime.now()-start}')
        start = datetime.now()
        for vf,h in tqdm.tqdm(video_files):
            vfd = VideoInfo.from_path(vfd.path)
        print(f'Loading VideoFile took: {datetime.now()-start}')
        #print(vfd)

    if False:
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

    if False:
        all_dirs = await db.find_all_dirs()
        for dir in all_dirs:
            print(f'==== Dir: {dir.path_abs}, Videos: {len(dir.video_files)} ====')
            for vf in dir.video_files.values():
                print(vf.hash_firstlast1kb[:10], vf, vf.name)

if __name__ == "__main__":
    asyncio.run(main())
