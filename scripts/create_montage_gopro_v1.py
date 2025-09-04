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


if __name__ == '__main__':
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from video files in a directory using the high-level FFMPEG interface.",
        epilog="Example: ./create_montage_v2.py ./my_videos 5 my_montage.mp4 --random_seed 42 --clip_ratio 30"
    )
    parser.add_argument("video_directory", help="Directory containing the video files.")
    parser.add_argument('--start_vid', type=int, help='Start video number.')
    parser.add_argument('--end_vid', type=int, help='End video number.')
    parser.add_argument("--clip_ratio", type=float, help="Ratio of video time to number of clips (seconds per clip). For example, 30 would mean one clip for every 30 seconds of source video.")
    parser.add_argument("--clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", type=Path, help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("-c", "--num_cores", type=int, default=15, help="Number of CPU cores to use (default: 15).")
    parser.add_argument("-s", "--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    parser.add_argument("-v", "--verbose", action='store_true', help="Enable verbose output.")
    parser.add_argument("--width", type=int, default=1920, help="Width of the output video (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Height of the output video (default: 1080).")
    parser.add_argument("--fps", type=int, default=60, help="Frames per second of the output video (default: 30).")
    args = parser.parse_args()
    
    mdir = mediatools.scan_directory(
        root_path=args.video_directory,
        use_absolute=True,
        video_ext=('.mp4', '.mov', '.avi', '.mkv', '.webm'),
    )

    def check_include(p: Path, min: int, max: int) -> bool:
        '''Check if the video file is within the specified range.'''
        p = Path(p)
        if p.is_file() and p.name.startswith('GX'):
            #print(f'\t{p}')
            #print(f'\t{p.stem}')
            name = p.stem[2:]
            #print(f'\t{name}')
            if '_' in name:
                name = name.split("_")[0]
            number = int(name)
            if number >= min and number <= max:
                return True
        return False
    
    use_vid_paths = list()
    for vf in sorted(mdir.all_video_files(), key=lambda x: x.fpath):
        if check_include(vf.fpath, args.start_vid, args.end_vid):
            use_vid_paths.append(vf.fpath)
    if args.verbose: print(f'found {len(use_vid_paths)} video files in range {args.start_vid} to {args.end_vid}')
    #use_vids = [vf.fpath for vf in mdir.all_video_files() if check_include(vf.fpath, args.start_vid, args.end_vid)]

    mediatools.ffmpeg.create_montage(
        video_files=use_vid_paths,
        clip_ratio=args.clip_ratio,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed,
        num_cores=args.num_cores,
        verbose=args.verbose,
        height=args.height,
        width=args.width,
        fps=args.fps,
    )
    






