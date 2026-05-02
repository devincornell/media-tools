import collections
import functools
import typing
import argparse
import os
import sys
import shutil
import random
from pathlib import Path
import subprocess
import tempfile
import tqdm
import multiprocessing
import pathlib
import multiprocessing
import hashlib
import sys
import asyncio
import pymongo
import pydantic_settings

import mediatools
from util import get_hash_hex, parallel_starmap, parallel_map

class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    site_root_path: Path
    site_thumb_path: Path
    site_mongodb_url: str
    site_database_name: str


def make_thumbs(
    mdir: mediatools.MediaDir, 
    thumbs_path: pathlib.Path,
    cores: int = 1,
    check_probe: bool = False,
) -> None:
    thumbs_path = Path(thumbs_path)
    thumbs_path.mkdir(parents=False, exist_ok=True)

    vfiles = mdir.all_videos()
    vfiles = random.sample(vfiles, len(vfiles))
    print(f'Found {len(vfiles)} video files in {mdir.path}. Scanning for thumbnails...')

    thumbs_to_create = []
    for vf in tqdm.tqdm(vfiles, ncols=80):
        if check_probe:
            try:
                probe_info = vf.probe()
            except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
                print(f'\nError: {vf.path} could not be probed. Skipping.')
                continue

        thumb_fname = get_thumb_path(vf.path, thumbs_path)

        if not thumb_fname.exists() or thumb_fname.stat().st_size == 0:
            #samp = max(1, int(probe_info.duration/10))
            thumbs_to_create.append( (vf.path, thumb_fname) )

    parallel_starmap(
        make_animated_thumb,
        thumbs_to_create,
        num_processes=cores,
        use_tqdm=True,
    )


def make_animated_thumb(
    input_fname: pathlib.Path|str, 
    output_fname: pathlib.Path|str, 
    fps: int = 3, 
    target_period: int = 10, 
    width: int = 400, 
    height: int = -1, 
    overwrite: bool = True
) -> None:
    '''Creates an animated thumbnail (GIF) from a video file.'''
    try:
        mediatools.ffmpeg.make_animated_thumb(
            input_fname=input_fname,
            output_fname=output_fname,
            fps=fps,
            target_period=target_period,
            width=width,
            height=height,
            overwrite=overwrite,
        )
    except mediatools.ffmpeg.FFMPEGExecutionError as e:
        print(f'\nERROR: FFMPEG failed to create thumbnail for {input_fname}: {e}')



def get_thumb_path(vid_path_abs: Path|str, thumbs_path: Path|str) -> Path:
    return Path(thumbs_path) / Path(mediatools.index_hash_func(vid_path_abs) + '.gif')


def scan_media_dir(
    mdir: mediatools.MediaDir, 
    convert_to_mp4: bool,
    delete_empty_videos: bool,
    delete_unprobable_videos: bool,
    delete_duplicates: bool,
    safety: bool = True,
) -> None:
    
    if delete_empty_videos:
        for vf in tqdm.tqdm(mdir.all_video_files(), ncols=80):
            if vf.path.exists() and vf.path.stat().st_size == 0:
                print(f'\nDeleting empty video file: {vf.path}')
                if not safety: vf.path.unlink(missing_ok=True)

    if delete_unprobable_videos:
        mediatools.parallel_map(
            functools.partial(probe_or_delete, safety=safety),
            mdir.all_video_files(),
            num_processes=multiprocessing.cpu_count(),
            use_tqdm=True,
        )

    if delete_duplicates:
        mediatools.parallel_map(
            functools.partial(delete_duplicates_thisdir, safety=safety),
            mdir.all_dirs(),
            num_processes=multiprocessing.cpu_count(),
            use_tqdm=True,
        )
    
    if convert_to_mp4:
        for vf in tqdm.tqdm(mdir.all_video_files(), ncols=80):
            if vf.path.exists() and not str(vf.path).endswith('.mp4'):
                try:
                    new_fp = vf.path.with_suffix('.mp4')
                    if new_fp.exists():
                        print(f'\nSkipping conversion for {vf.path}; {new_fp} already exists.')
                        continue
                    print(f'\nConverting {vf.path} to {new_fp}')
                    mediatools.FFMPEG(
                        inputs=[mediatools.ffinput(vf.path)],
                        outputs=[mediatools.ffoutput(new_fp,y=True)]
                    ).run()
                except mediatools.ffmpeg.FFMPEGExecutionError as e:
                    print(f'ERROR: Could not convert {vf.path}: {e}')


def probe_or_delete(vf: mediatools.VideoFile, safety: bool = True) -> None:
    '''Probes a video file, deleting it if unprobable.'''
    if vf.path.exists():
        try:
            probe_info = vf.probe()
        except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
            print(f'\nDeleting unprobable video file (probe error): {vf.path}')
            if not safety: vf.path.unlink(missing_ok=True)


async def reindex(root_path: Path, mongodb_url: str, database_name: str) -> None:
    '''Rescan and update the media index database for the given root path.'''
    async with pymongo.AsyncMongoClient(mongodb_url, serverSelectionTimeoutMS=2000) as client:
        mindex = await mediatools.MediaIndexDB.from_client(client[database_name])
        await mindex.update_directory_index(root_path, verbose=True)
        print(f'Dirs indexed:   {await mindex.dirs.count(root_path)}')
        print(f'Videos indexed: {await mindex.videos.count(root_path)}')


def delete_duplicates_thisdir(mdir: mediatools.MediaDir, safety: bool = True) -> None:
    '''Deletes duplicate video files in the given media directory.'''
    hash_to_paths: dict[str, set[pathlib.Path]] = collections.defaultdict(set)
    for vf in mdir.videos:
        if vf.path.exists():
            try:
                h = get_hash_hex(vf.path, chunk_size=1024*1024)
            except Exception as e:
                print(f'\nError hashing file {vf.path}: {e}')
            hash_to_paths[h].add(vf.path)

    for h, paths in hash_to_paths.items():
        if len(paths) > 1:
            print(f'\nFound {len(paths)} duplicate videos with hash {h}:'+"\n\t" + "\n\t".join(str(p.name) for p in paths))
            use_path = list(sorted(paths, key=lambda p: len(str(p))))[-1]
            for dup_path in list(paths):
                if dup_path != use_path:
                    print(f'\nDeleting duplicate video file: {dup_path}')
                    if not safety: dup_path.unlink(missing_ok=True)


if __name__ == '__main__':
    
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Scan videos in the directory and clean them up.",
        epilog="Example: ./create_montage_v2.py ./my_videos 5 my_montage.mp4 --random_seed 42 --clip_ratio 30"
    )
    parser.add_argument("root_directory", nargs='?', default=None, help="Directory containing the video files (default: site_root_path from .env).")
    parser.add_argument("-r", "--reindex", action='store_true', help="Rescan and update the media index database.")
    parser.add_argument("-t", "--make-thumbs", action='store_true', help="Generate thumbnails for the videos.")
    parser.add_argument("-p", "--thumbs-path", type=str, default=None, help="Directory to save thumbnails (default: site_thumb_path from .env).")
    parser.add_argument("-c", "--num_cores", type=int, default=1, help="Number of CPU cores to use for thumbnail generation (default: 1).")
    parser.add_argument("-m", "--convert-to-mp4", action='store_true', help="Convert non-MP4 videos to MP4 format.")
    parser.add_argument("-e", "--delete-empty-videos", action='store_true', help="Delete empty video files.")
    parser.add_argument("-u", "--delete-unprobable-videos", action='store_true', help="Delete unprobable video files that cannot be probed.")
    parser.add_argument("-d", "--delete-duplicates", action='store_true', help="Delete duplicate video files based on hash.")
    parser.add_argument("-s", "--no-safety", action='store_true', help="Disable safety checks (actually delete files).")
    args = parser.parse_args()

    # Load base settings from .env / environment variables
    settings = Settings()

    # Override with any explicitly provided CLI args
    if args.root_directory is not None:
        settings = settings.model_copy(update={'site_root_path': Path(args.root_directory)})
    if args.thumbs_path is not None:
        settings = settings.model_copy(update={'site_thumb_path': Path(args.thumbs_path)})

    root_path = settings.site_root_path
    thumbs_path = settings.site_thumb_path

    if args.thumbs_path is not None and not args.make_thumbs:
        raise ValueError('If --thumbs-path is set, --make-thumbs must also be set.')

    if not root_path.is_dir():
        raise ValueError(f'Error: root_directory {root_path} is not a valid directory.')

    mdir = mediatools.scan_directory(root_path)
    print(mdir.path)
    print(f'{len(mdir.all_dirs())=}')
    print(f'{len(mdir.all_video_files())=}')

    if args.reindex:
        asyncio.run(reindex(root_path, settings.site_mongodb_url, settings.site_database_name))
    
    scan_media_dir(
        mdir=mdir,
        convert_to_mp4=args.convert_to_mp4,
        delete_empty_videos=args.delete_empty_videos,
        delete_unprobable_videos=args.delete_unprobable_videos,
        delete_duplicates=args.delete_duplicates,
        safety=not args.no_safety,
    )

    if args.make_thumbs:
        make_thumbs(mdir=mdir, thumbs_path=thumbs_path, cores=args.num_cores)






