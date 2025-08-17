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
    parser.add_argument("clip_ratio", type=float, help="Ratio of video time to number of clips (seconds per clip). For example, 30 would mean one clip for every 30 seconds of source video.")
    parser.add_argument("clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", type=Path, help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("-c", "--num_cores", type=int, default=15, help="Number of CPU cores to use (default: 15).")
    parser.add_argument("-s", "--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    parser.add_argument("-v", "--verbose", action='store_true', help="Enable verbose output.")
    parser.add_argument("--width", type=int, default=1920, help="Width of the output video (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Height of the output video (default: 1080).")
    args = parser.parse_args()
    
    # Find video files in the specified directory
    try:
        video_paths = mediatools.VideoFiles.from_glob(
            root=args.video_directory,
            extensions=("mp4", "mov", "avi", "mkv", "flv", "webm")
        )
        if not video_paths:
            print(f"No video files found in '{args.video_directory}'.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error finding video files: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Convert VideoFile objects to Path objects for the function
    video_paths = [vf.fpath for vf in video_paths]
    
    mediatools.ffmpeg.create_montage(
        video_files=video_paths,
        clip_ratio=args.clip_ratio,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed,
        num_cores=args.num_cores,
        verbose=args.verbose,
        height=args.height,
        width=args.width,
    )
    






