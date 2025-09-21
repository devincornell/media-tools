#!/usr/bin/env python3
import typing
import argparse
import os
import subprocess
import sys
import shutil
import glob
import random

def create_montage(
    video_directory: str, 
    clip_duration: float, 
    output_filename: str, 
    random_seed: int = 0, 
    width: int = 1920, 
    height:int=1080, 
    fps:int=30, 
    clip_ratio:float=30,
    supported_extensions: typing.Iterable[str] = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.flv")
) -> None:
    """
    Creates a video montage from a directory of video files using FFmpeg.

    This function finds all video files in a specified directory, extracts clips from each video proportional to its length, and then concatenates them into a single montage file. The video and audio are standardized to ensure compatibility.

    Args:
        video_directory (str): The path to the directory containing the video files.
        clip_duration (float): The duration (in seconds) of each clip to extract from each video.
        output_filename (str): The path and name of the output montage file.
        random_seed (int, optional): The seed for the random number generator to ensure reproducibility. Defaults to 0.
        width (int, optional): The width of the output video. Defaults to 1920.
        height (int, optional): The height of the output video. Defaults to 1080.
        fps (int, optional): The frames per second of the output video. Defaults to 30.
        clip_ratio (float, optional): Ratio of video duration to number of clips (seconds per clip). Defaults to 30.

    Returns:
        bool: True if the montage was created successfully, False otherwise.
    """
    
    # --- Helper Functions ---
    supported_extensions = set(supported_extensions)
    def find_video_files(directory):
        """Finds all video files with supported extensions in a directory."""
        #supported_extensions = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.flv")
        video_files = []
        for ext in supported_extensions:
            video_files.extend(glob.glob(os.path.join(directory, ext)))
        return list(sorted(video_files))

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
        """Runs an FFmpeg command, returning True on success. Prints stderr on failure."""
        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=cwd, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"\n[ffmpeg error] Command failed: {' '.join(command)}")
            if hasattr(e, 'stderr') and e.stderr:
                print(f"[ffmpeg stderr]:\n{e.stderr}")
            elif isinstance(e, subprocess.CalledProcessError) and e.output:
                print(f"[ffmpeg output]:\n{e.output}")
            else:
                print("[ffmpeg error]: No stderr output captured.")
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
        clip_index = 0
        max_clips = 20  # Limit for debugging
        for i, f in enumerate(video_files):
            if len(processed_clips) >= max_clips:
                print(f"Reached max_clips ({max_clips}), stopping further processing.")
                break
            print(f"  - Processing '{os.path.basename(f)}'...")
            duration = get_video_duration(f)
            if duration < clip_duration:
                num_clips = 1
            else:
                num_clips = max(1, int(duration / clip_ratio))
            print(f"    Extracting {num_clips} clip(s) from {duration:.2f}s video.")
            possible_starts = max(1, int((duration - clip_duration) // clip_duration))
            starts = []
            for n in range(num_clips):
                if duration <= clip_duration:
                    start_time = 0
                else:
                    # Try to avoid overlapping clips
                    min_start = 0
                    max_start = duration - clip_duration
                    if num_clips > 1:
                        # Evenly distribute start times
                        start_time = min_start + (max_start - min_start) * n / (num_clips)
                        # Add some randomness
                        jitter = (max_start - min_start) / (num_clips * 4)
                        start_time += random.uniform(-jitter, jitter)
                        start_time = max(min_start, min(max_start, start_time))
                    else:
                        start_time = random.uniform(min_start, max_start)
                processed_clip_path = os.path.join(tmp_dir, f"processed_clip_{clip_index}.mp4")
                cmd = [
                    "ffmpeg",
                    # "-hwaccel", "cuda",  # Removed to avoid issues with unsupported codecs
                    "-ss", str(start_time),
                    "-i", os.path.abspath(f),
                    "-t", str(clip_duration),
                    "-y",
                    "-r", str(fps),
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                    #"-c:v", "libx264",
                    "-c:v", "h264_nvenc",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    processed_clip_path
                ]
                if run_ffmpeg_command(cmd):
                    processed_clips.append(processed_clip_path)
                else:
                    print(f"  -> Skipping '{os.path.basename(f)}' clip {n+1} due to processing error.")
                clip_index += 1

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
            # Run the concat command again to print stderr for debugging
            try:
                result = subprocess.run(concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
            except subprocess.CalledProcessError as e:
                print("[ffmpeg concat stderr]:\n" + (e.stderr or "<no stderr output>"))
            return False

    finally:
        print("Cleaning up temporary files...")
        shutil.rmtree(tmp_dir)

if __name__ == '__main__':
    # This block allows the script to be run directly from the command line for testing.
    parser = argparse.ArgumentParser(
        description="Create a video montage from a directory of video files using FFmpeg.",
        epilog="Example: ./create_montage.py ./my_videos 5 my_montage.mp4 --random_seed 42 --clip_ratio 30"
    )
    parser.add_argument("video_directory", help="Directory containing the video files.")
    parser.add_argument("clip_duration", type=float, help="Duration of each clip in seconds.")
    parser.add_argument("output_filename", help="Name for the final output file (e.g., montage.mp4).")
    parser.add_argument("--random_seed", type=int, default=0, help="Random seed for selecting clips (default: 0).")
    parser.add_argument("--clip_ratio", type=float, default=30, help="Ratio of video time to number of clips (seconds per clip, default: 30).")
    args = parser.parse_args()
    create_montage(
        video_directory=args.video_directory,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed,
        clip_ratio=args.clip_ratio
    )
