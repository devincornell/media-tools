#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import shutil
import glob
import random

def create_montage(video_directory, clip_duration, output_filename, random_seed=0, width=1920, height=1080, fps=30):
    """
    Creates a video montage from a directory of video files using FFmpeg.

    This function finds all video files in a specified directory, extracts a clip of a given
    duration from a random point in each video, and then concatenates them into a single
    montage file. The video and audio are standardized to ensure compatibility.

    Args:
        video_directory (str): The path to the directory containing the video files.
        clip_duration (float): The duration (in seconds) of the clip to extract from each video.
        output_filename (str): The path and name of the output montage file.
        random_seed (int, optional): The seed for the random number generator to ensure
            reproducibility. Defaults to 0.
        width (int, optional): The width of the output video. Defaults to 1920.
        height (int, optional): The height of the output video. Defaults to 1080.
        fps (int, optional): The frames per second of the output video. Defaults to 30.

    Returns:
        bool: True if the montage was created successfully, False otherwise.
    """
    
    # --- Helper Functions ---

    def find_video_files(directory):
        """Finds all video files with supported extensions in a directory."""
        supported_extensions = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.flv")
        video_files = []
        for ext in supported_extensions:
            video_files.extend(glob.glob(os.path.join(directory, ext)))
        return video_files

    def get_video_duration(video_path):
        """Gets the duration of a video in seconds using ffprobe."""
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(result.stdout)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0

    def run_ffmpeg_command(command, cwd=None):
        """Runs an FFmpeg command, returning True on success."""
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=cwd)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    # --- Main Function Logic ---

    random.seed(random_seed)

    if not os.path.isdir(video_directory):
        print(f"Error: Directory '{video_directory}' not found.", file=sys.stderr)
        return False

    if clip_duration <= 0:
        print("Error: Clip duration must be a positive number.", file=sys.stderr)
        return False

    video_files = find_video_files(video_directory)
    if not video_files:
        print(f"No video files found in '{video_directory}'.", file=sys.stderr)
        return False

    tmp_dir = os.path.abspath("tmp_montage_files")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    try:
        print(f"--- Creating montage: {output_filename} (seed: {random_seed}) ---")
        print("Processing video files...")
        processed_clips = []
        for i, f in enumerate(video_files):
            print(f"  - Processing '{os.path.basename(f)}'...")
            duration = get_video_duration(f)
            if duration <= clip_duration:
                start_time = 0
            else:
                start_time = random.uniform(0, duration - clip_duration)

            processed_clip_path = os.path.join(tmp_dir, f"processed_clip_{i}.mp4")
            
            cmd = [
                "ffmpeg",
                "-ss", str(start_time),
                "-i", os.path.abspath(f),
                "-t", str(clip_duration),
                "-y",
                "-r", str(fps),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                processed_clip_path
            ]
            if run_ffmpeg_command(cmd):
                processed_clips.append(processed_clip_path)
            else:
                print(f"  -> Skipping '{os.path.basename(f)}' due to processing error.")

        if not processed_clips:
            print("No valid clips were processed. Montage creation failed.", file=sys.stderr)
            return False

        # Build the complex filter graph for concatenation
        filter_complex = ""
        for i in range(len(processed_clips)):
            filter_complex += f"[{i}:v:0][{i}:a:0]"
        filter_complex += f"concat=n={len(processed_clips)}:v=1:a=1[outv][outa]"

        concat_cmd = ["ffmpeg"]
        for clip_path in processed_clips:
            concat_cmd.extend(["-i", clip_path])
        
        concat_cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-y",
            os.path.abspath(output_filename)
        ])
        
        if run_ffmpeg_command(concat_cmd):
            print(f"\nMontage created successfully: '{output_filename}'")
            return True
        else:
            print(f"\nFailed to create montage: '{output_filename}'", file=sys.stderr)
            return False

    finally:
        print("Cleaning up temporary files...")
        shutil.rmtree(tmp_dir)

if __name__ == '__main__':
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from a directory of video files using FFmpeg.",
        epilog="Example: ./montage_utils.py ./my_videos 5 my_montage.mp4 --random_seed 42"
    )
    parser.add_argument("video_directory", help="Directory containing the video files.")
    parser.add_argument("clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    
    args = parser.parse_args()
    
    create_montage(
        video_directory=args.video_directory,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed
    )
