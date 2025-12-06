#!/usr/bin/env python3
"""
Create a video montage from a directory of video files using the high-level FFMPEG interface.

This script re-implements the montage creation functionality using the mediatools.video
interface instead of direct subprocess calls to ffmpeg.
"""

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

import sys
sys.path.append('../src/')
import mediatools

def create_montage_recursive(
    mdir: mediatools.MediaDir,
    clip_ratio: float,
    clip_duration: float,
    output_filename: Path|str,
    random_seed: int,
    num_cores: int,
    verbose: bool,
    height: int,
    width: int,
    fps: int,
    overwrite: bool = True,
    usecuda: bool = False,
    max_clips_per_video: int = 10,
    max_total_clips: int|None = 100000,
    shuffle_clips: bool = True,
    ignore_invalid_videos: bool = False,
    max_videos: int|None = None,
    skip_existing: bool = True,
) -> mediatools.ffmpeg.FFMPEGResult|None:
    '''Create montages recursively for each subdirectory in the media directory.'''
    for sd in mdir.subdirs:
        create_montage_recursive(
            mdir = sd,
            clip_ratio=clip_ratio,
            clip_duration=clip_duration,
            output_filename=output_filename,
            random_seed=random_seed,
            num_cores=num_cores,
            verbose=verbose,
            height=height,
            width=width,
            fps=fps,
            overwrite=overwrite,
            usecuda=usecuda,
            max_clips_per_video=max_clips_per_video,
            ignore_invalid_videos=ignore_invalid_videos,
        )

    output_path = mdir.fpath / output_filename
    if output_path.exists() and skip_existing:
        print(f"Skipping existing montage at {output_path}")
        return None

    video_paths = [fp for fp in mdir.all_video_paths() if fp.name != output_filename]
    if len(video_paths) == 0:
        return None
    if max_videos is not None and len(video_paths) > max_videos:
        video_paths = list(random.sample(video_paths, k=max_videos))

    print(f"making montage from {len(video_paths)} videos in {mdir.fpath}")

    return mediatools.ffmpeg.create_montage(
        video_files=video_paths,
        clip_ratio=clip_ratio,
        clip_duration=clip_duration,
        output_filename=output_path,
        random_seed=random_seed,
        num_cores=num_cores,
        verbose=verbose,
        height=height,
        width=width,
        fps=fps,
        max_total_clips=max_total_clips,
        shuffle_clips=shuffle_clips,
        overwrite=True,
    )



if __name__ == '__main__':
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from video files in a directory using the high-level FFMPEG interface.",
        epilog="Example: ./create_montage_v2.py ./my_videos 5 my_montage.mp4 --random_seed 42 --clip_ratio 30"
    )
    parser.add_argument("video_directory", help="Directory containing the video files.")
    parser.add_argument("clip_ratio", type=float, help="Ratio of video time to number of clips (seconds per clip). For example, 30 would mean one clip for every 30 seconds of source video.")
    parser.add_argument("clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", type=Path, help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("-c", "--num_cores", type=int, default=15, help="Number of CPU cores to use (default: 15).")
    parser.add_argument("-s", "--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    parser.add_argument("-v", "--verbose", action='store_true', help="Enable verbose output.")
    parser.add_argument("--max_total_clips", type=int, default=2500, help="Maximum total number of clips in the montage (default: 1000).")
    parser.add_argument("--no_shuffle", action='store_true', help="Shuffle clips before creating the montage.")
    parser.add_argument("--width", type=int, default=1920, help="Width of the output video (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Height of the output video (default: 1080).")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second of the output video (default: 30).")
    parser.add_argument("--usecuda", action='store_true', help="Use CUDA acceleration if available.")
    parser.add_argument("--max_clips_per_video", type=int, default=10, help="Maximum number of clips to extract from each video (default: 10).")
    parser.add_argument("-i", "--ignore_invalid_videos", action='store_true', help="Ignore invalid or non-video files instead of exiting with an error.")
    args = parser.parse_args()
    
    mdir = mediatools.scan_directory(
        root_path=args.video_directory,
        use_absolute=True,
        #video_ext=('.mp4', '.mov', '.avi', '.mkv', '.webm'),
    )

    create_montage_recursive(
        mdir=mdir,
        clip_ratio=args.clip_ratio,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed,
        num_cores=args.num_cores,
        verbose=args.verbose,
        height=args.height,
        width=args.width,
        fps=args.fps,
        overwrite=True,
        max_total_clips=args.max_total_clips,
        shuffle_clips=not args.no_shuffle,
        usecuda=args.usecuda,
        max_clips_per_video=args.max_clips_per_video,
        ignore_invalid_videos=args.ignore_invalid_videos,
        max_videos=50,
    )
    






