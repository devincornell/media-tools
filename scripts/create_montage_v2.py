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
import logging

import sys
sys.path.append('../src/')
import mediatools

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


if __name__ == '__main__':
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from multiple video files using the high-level FFMPEG interface.",
        epilog="Examples:\n  ./create_montage_v2.py my_videos/gx*.mp4 30 5.0 montage.mp4\n  ./create_montage_v2.py video1.mp4 video2.mp4 video3.mp4 30 5.0 montage.mp4"
    )
    parser.add_argument("video_files", nargs='+', type=Path, help="Video files to include in the montage. Supports shell glob expansion (e.g., my_videos/*.mp4).")
    parser.add_argument("clip_ratio", type=float, help="Ratio of video time to number of clips (seconds per clip). For example, 30 would mean one clip for every 30 seconds of source video.")
    parser.add_argument("clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", type=Path, help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("-c", "--num_cores", type=int, default=15, help="Number of CPU cores to use (default: 15).")
    parser.add_argument("-s", "--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    parser.add_argument("-v", "--verbose", action='store_true', help="Enable verbose output.")
    parser.add_argument("--width", type=int, default=1920, help="Width of the output video (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Height of the output video (default: 1080).")
    parser.add_argument("--usecuda", action='store_true', help="Use CUDA acceleration if available.")
    parser.add_argument("--max_clips_per_video", type=int, default=10, help="Maximum number of clips to extract from each video (default: 10).")
    parser.add_argument("-i", "--ignore_invalid_videos", action='store_true', help="Ignore invalid or non-video files instead of exiting with an error.")
    args = parser.parse_args()
    
    video_paths = list()
    for vps in args.video_files:
        if (vp := Path(vps)).exists():
            try:
                mediatools.ffmpeg.probe(vp)
            except mediatools.ffmpeg.FFMPEGExecutionError:
                if args.verbose: 
                    logging.warning(f"Warning: The file is not a valid video format and will be skipped: {vp}")
                if not args.ignore_invalid_videos:
                    raise ValueError(f"Video file is not valid: {vp}")
            else:
                video_paths.append(str(vp))
        else:
            if args.verbose: 
                logging.warning(f"Warning: The file does not exist and will be skipped: {vp}")
            if not args.ignore_invalid_videos:
                raise FileNotFoundError(f"Video path does not exist: {vp}")

    if len(video_paths) > 0:
        if args.verbose:
            logging.info(f"Found {len(video_paths)} valid video files for montage creation.")
    else:
        raise FileNotFoundError(f"No valid video files found from the provided arguments.")

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
        use_cuda=args.usecuda,
        max_clips_per_video=args.max_clips_per_video,
    )
    






