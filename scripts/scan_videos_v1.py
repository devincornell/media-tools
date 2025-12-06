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

sys.path.append('../src/')
sys.path.append('src/')
import mediatools
from util import get_hash_hex



def scan_media_folders(
    mdir: mediatools.MediaDir, 
    root: pathlib.Path, 
    thumbs_path: pathlib.Path,
    sort_by_name: bool,
    max_clip_duration: float,
) -> tuple[dict[Path,dict[str,typing.Any]],dict[str,typing.Any]]:
    '''Scans media files by directory.'''



    print(f'entering {mdir.fpath}')
    
    for sdir in sorted(mdir.subdirs, key=lambda sd: sd.fpath):
        if len(sdir.all_media_files()) > 0 or len(sdir.subdirs) > 0:
            scan_media_folders(
                mdir=sdir, 
                root=root, 
                thumbs_path=thumbs_path, 
            )



def make_thumbs(
    mdir: mediatools.MediaDir, 
    thumbs_path: pathlib.Path,
    cores: int = 1,
) -> None:
    thumbs_path = Path(thumbs_path)
    thumbs_path.mkdir(parents=False, exist_ok=True)

    vfiles = mdir.all_video_files()
    vfiles = random.sample(vfiles, len(vfiles))
    print(f'Found {len(vfiles)} video files in {mdir.fpath}. Scanning for thumbnails...')

    #for vf in tqdm.tqdm(vfiles, "testing hash speed.", ncols=80):
    #    get_hash_hex(str(vf.fpath), chunk_size=1024, max_chunks=1)
    #return

    thumbs_to_create = []
    for vf in tqdm.tqdm(vfiles, ncols=80):
        try:
            probe_info = vf.probe()
        except (mediatools.ffmpeg.ProbeError, mediatools.ffmpeg.FFMPEGExecutionError) as e:
            print(f'\nError: {vf.fpath} could not be probed. Skipping.')
            continue

        rel_path = vf.fpath.relative_to(mdir.fpath)
        #thumb_fname = get_thumb_path(rel_path, thumbs_path)
        thumb_fname = get_thumb_path2(vf.fpath, thumbs_path)
        if not thumb_fname.exists() or thumb_fname.stat().st_size == 0:
            #samp = max(1, int(probe_info.duration/10))
            thumbs_to_create.append( (vf.fpath, thumb_fname) )

    if cores > 1:
        with multiprocessing.Pool(processes=cores) as pool:
            list(tqdm.tqdm(
                pool.imap_unordered(
                    lambda args: make_animated_thumb(
                        input_fname=args[0],
                        output_fname=args[1],
                    ),
                    thumbs_to_create,
                ),
                total=len(thumbs_to_create),
                ncols=80,
            ))
    else:
        for input_fp, output_fp in tqdm.tqdm(thumbs_to_create, ncols=80):
            output_fp.parent.mkdir(parents=True, exist_ok=True)
            make_animated_thumb(
                input_fname=input_fp,
                output_fname=output_fp,
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


def get_thumb_path(vid_path_rel: Path|str, thumbs_path: Path|str) -> Path:
    return thumbs_path / str(Path(vid_path_rel).with_suffix('.gif')).replace('/', '.')

def get_thumb_path2(vid_path_abs: Path|str, thumbs_path: Path|str) -> Path:
    return Path(thumbs_path) / Path(get_hash_hex(vid_path_abs, max_chunks=1) + '.gif')


def scan_media_dir(
    mdir: mediatools.MediaDir, 
    convert_to_mp4: bool = False,
) -> None:

    for subdir in mdir.subdirs:
        scan_media_dir(subdir, convert_to_mp4=convert_to_mp4)
    
    for vf in mdir.videos:
        if convert_to_mp4 and not str(vf.fpath).endswith('.mp4'):
            try:
                new_fp = vf.fpath.with_suffix('.mp4')
                if new_fp.exists():
                    print(f'Skipping conversion for {vf.fpath}; {new_fp} already exists.')
                    continue
                print(f'Converting {vf.fpath} to {new_fp}')
                mediatools.FFMPEG(
                    inputs=[mediatools.ffinput(vf.fpath)],
                    outputs=[mediatools.ffoutput(new_fp,y=True)]
                ).run()
            except mediatools.ffmpeg.FFMPEGExecutionError as e:
                print(f'ERROR: Could not convert {vf.fpath}: {e}')




def compress_videos(
    mdir: mediatools.MediaDir, 
    root: pathlib.Path, 
    thumbs_path: pathlib.Path,
) -> tuple[dict[Path,dict[str,typing.Any]],dict[str,typing.Any]]:

    vfiles = mdir.all_video_files()
    print(f'Found {len(vfiles)} video files in {mdir.fpath}')

    for vf in tqdm.tqdm(vfiles, ncols=80):
        rel_path = vf.fpath.relative_to(root)
        thumb_fname = thumbs_path / rel_path.with_suffix('.jpg')
        if not thumb_fname.exists():
            thumb_fname.parent.mkdir(parents=True, exist_ok=True)
            try:
                mediatools.FFMPEG(
                    input_files=[vf.fpath],
                    output_fname=thumb_fname,
                    time_point_sec=min(0.5, vf.duration.total_seconds()/2),
                    overwrite=False,
                    vframes=1,
                    q=2
                )
                print(f'Created thumbnail for {vf.fpath} at {thumb_fname}')
            except Exception as e:
                print(f'ERROR: Failed to create thumbnail for {vf.fpath}: {e}')
                continue


def get_new_filename(fp: pathlib.Path) -> pathlib.Path:
    return fp.with_name(fp.stem[:249] + "-c" + fp.suffix)

def bitrate_calculator(info: mediatools.ffmpeg.ProbeInfo) -> int:
    # 1920x1080: 2073600
    # 1280x720: 921600
    if info.video.pixels > 3000000: # ~80% of 2160p
        return 400000
    if info.video.pixels > 1573600: # ~75% of 1080p
        return 300000
    elif info.video.pixels > 751600: # ~75% of 720p
        return 200000
    else:
        return 100000


def compress_single_video(
    vf: mediatools.VideoFile,
    new_fpath: pathlib.Path,
    bitrate_cutoff: int,
    crf_increment: int = 5,
    verbose: bool = True,
    delete_errored_files: bool = False,
) -> bool:
    try:
        try_crf = 25
        while True:
            result = vf.ffmpeg.compress(
                output_fname = new_fpath,
                crf = try_crf,
                overwrite = True,
            )
            nvid = result.vf
            if verbose:
                print(f'\ttried crf: {try_crf}; {vf.probe().file_bitrate/1000:6.1f} kbps ({mediatools.format_memory(vf.probe().size)}) --> '
                    f'{nvid.probe().file_bitrate/1000:6.1f} kbps ({mediatools.format_memory(nvid.probe().size)})')
            if nvid.probe().file_bitrate < bitrate_cutoff:
                return True
            else:
                try_crf += crf_increment
                if verbose:
                    print(f'\t{nvid.probe().file_bitrate/1000:5.1f} kbps > target '
                        f'({bitrate_cutoff/1000:5.1f} kbps). increasing crf to {try_crf}')
    except mediatools.FFMPEGCommandError as e:
        new_fpath.unlink(missing_ok=True)
        if verbose:
            print(f'\n\terror encountered. {str(new_fpath)}')
        if delete_errored_files:
            vf.fpath.unlink(missing_ok=True)
            print(f'\n\tdeleting {str(vf.fpath)}')
        #raise e from e
    return True


if __name__ == '__main__':
    
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from video files in a directory using the high-level FFMPEG interface.",
        epilog="Example: ./create_montage_v2.py ./my_videos 5 my_montage.mp4 --random_seed 42 --clip_ratio 30"
    )
    parser.add_argument("root_directory", help="Directory containing the video files.")
    parser.add_argument("-t", "--make-thumbs", action='store_true', help="Generate thumbnails for the videos.")
    parser.add_argument("-p", "--thumbs_path", type=str, default=None, help="Directory to save thumbnails (default: <root_directory>/_thumbs).")
    parser.add_argument("-c", "--num_cores", type=int, default=1, help="Number of CPU cores to use for thumbnail generation (default: 1).")
    parser.add_argument("--convert", action='store_true', help="Convert non-MP4 videos to MP4 format.")
    #parser.add_argument("-c", "--num_cores", type=int, default=15, help="Number of CPU cores to use (default: 15).")
    #parser.add_argument("-s", "--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    #parser.add_argument("-v", "--verbose", action='store_true', help="Enable verbose output.")
    #parser.add_argument("--width", type=int, default=1920, help="Width of the output video (default: 1920).")
    #parser.add_argument("--height", type=int, default=1080, help="Height of the output video (default: 1080).")
    #parser.add_argument("--fps", type=int, default=60, help="Frames per second of the output video (default: 30).")
    args = parser.parse_args()
    
    mdir = mediatools.scan_directory(args.root_directory)
    print(args.root_directory)
    print(len(mdir.videos))
    print(len(mdir.subdirs))
    
    print(args)
    if args.make_thumbs:
        make_thumbs(
            mdir=mdir,
            thumbs_path=Path(args.root_directory) / '_thumbs' if args.thumbs_path is None else Path(args.thumbs_path),
            cores=args.num_cores,
        )
    else:
        print('--make-thumbs not set; skipping thumbnail generation.')

    if args.convert and False:
        scan_media_dir(mdir, convert_to_mp4=True)





