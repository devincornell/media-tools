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
from mediatools.video import VideoFiles, VideoFile, VideoInfo
from mediatools.video.ffmpeg import FFMPEG, FFMPEGResult
import mediatools



def create_montage(
    video_files: typing.List[Path], 
    output_filename: str, 
    clip_ratio: float, # one clip for every 30 seconds (10x shorter)
    clip_duration: float, 
    random_seed: int = 0, 
    width: int = 1920, 
    height: int = 1080, 
    fps: int = 30, 
    num_cores: int = 16,
    verbose: bool = False,
) -> mediatools.ffmpeg.FFMPEGResult:
    """
    Creates a video montage from a list of video files using the high-level FFMPEG interface.

    This function takes a list of video file paths, extracts clips from each video 
    proportional to its length, and then concatenates them into a single montage file. 
    The video and audio are standardized to ensure compatibility.

    Args:
        video_files (typing.List[Path]): List of pathlib Path objects pointing to video files.
        clip_duration (float): The duration (in seconds) of each clip to extract from each video.
        output_filename (str): The path and name of the output montage file.
        random_seed (int, optional): The seed for the random number generator to ensure reproducibility. Defaults to 0.
        width (int, optional): The width of the output video. Defaults to 1920.
        height (int, optional): The height of the output video. Defaults to 1080.
        fps (int, optional): The frames per second of the output video. Defaults to 30.
        clip_ratio (float, optional): Ratio of video time to number of clips (seconds per clip, default: 30).

    Returns:
        bool: True if the montage was created successfully, False otherwise.
    """
    clip_infos = get_random_clips(
        video_paths=video_files,
        clip_duration=clip_duration,
        random_seed=random_seed,
        clip_ratio=clip_ratio
    )
    print(f'identified {len(clip_infos)} clips. now processing')
    with tempfile.TemporaryDirectory() as tmp_dir:
        #for clip_info in tqdm.tqdm(clip_infos):
        clip_packaged_data = [(clip_info, tmp_dir, clip_duration, width, height, fps, verbose) for clip_info in clip_infos]
        with multiprocessing.Pool(num_cores) as p:
            clip_filenames = p.starmap(extract_clip, clip_packaged_data)
        clip_filenames = [f for f in clip_filenames if f is not None]

        print(f'merging {len(clip_filenames)} clips')
        result = concatenate_clips_demux(clip_filenames, output_filename, tmp_file_path=Path(tmp_dir)/'input_file_list.txt')

    return result


def extract_clip(
    clip_info: dict[str,typing.Any], 
    tmp_dir: Path|str, 
    clip_duration: float, 
    width: int, 
    height: int, 
    fps: int,
    verbose: bool = False,
) -> str|None:
    processed_clip_path = os.path.join(tmp_dir, f"clip_{clip_info['index']}.mp4")
    ffmpeg_cmd = mediatools.ffmpeg.FFMPEG(
        input_files=[clip_info['fpath']],
        output_file=processed_clip_path,
        overwrite_output=True,
        ss=str(clip_info['start_time']),
        duration=str(clip_duration),
        framerate=fps,
        vf=f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        vcodec="h264_nvenc",
        acodec="aac",
        audio_bitrate="192k",
        loglevel="error",
        input_args=[
            ('hwaccel', 'cuda'),
        ],
    )
    try:
        #print(f"Starting'{clip_info['fpath']}' clip {clip_info['index']}.")
        ffmpeg_cmd.run()
        mediatools.VideoFile.from_path(processed_clip_path).probe()  # Ensure the clip was processed correctly
    except mediatools.ffmpeg.FFMPEGExecutionError as e:
        print(f"\nFailed to extract '{clip_info['fpath']}' clip {clip_info['index']} due to processing error.")
        if verbose: print(f"{e}")
        return None
    else:
        print('finished', processed_clip_path)

    return processed_clip_path
        


def get_random_clips(
    video_paths: typing.List[Path], 
    clip_duration: float, 
    random_seed: int = 0, 
    clip_ratio: float = 30 # one clip for every 30 seconds (10x shorter)
) -> bool:
    '''Extract random clips from the given video files.'''

    random.seed(random_seed)
    video_files: list[VideoFile] = [VideoFile.from_path(path) for path in video_paths]

    if not all([vf.fpath.exists() for vf in video_files]):
        raise ValueError("Error: One or more video files do not exist.")

    if clip_duration <= 0:
        raise ValueError("Error: Clip duration must be a positive number.")
    
    clip_infos: list[dict[str,typing.Any]] = []
    clip_index = 0
    for video_file in video_files:
        
        try:
            duration = video_file.probe().duration
        except mediatools.ffmpeg.FFMPEGExecutionError as e:
            continue
        
        if duration == 0:
            continue
            
        if duration < clip_duration:
            num_clips = 1
        else:
            num_clips = max(1, int(duration / clip_ratio))
            
        
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
            
            clip_infos.append({
                'index': clip_index,
                'fpath': str(video_file.fpath),
                'start_time': start_time,
                'duration': clip_duration,
            })

            clip_index += 1
    return clip_infos



def concatenate_clips_demux(clips: list[Path|str], output_filename: Path|str, tmp_file_path: Path|str) -> mediatools.ffmpeg.FFMPEGResult:
    '''Concatenate video clips using demuxing (fast and lossless).'''
    if not clips:
        raise ValueError("No clips to concatenate.")

    # Create a temporary file list for ffmpeg
    #with tempfile.NamedTemporaryFile(delete=False, dir=tmp_dir) as f:
    #tmp_file_path = Path('input_file_list.txt')
    with tmp_file_path.open('w') as f:
        f.write("\n".join([f"file '{c}'" for c in clips]))

    print(tmp_file_path.read_text())

    # Build the ffmpeg command
    ffmpeg_cmd = FFMPEG(
        input_files=[str(tmp_file_path)],
        output_file=output_filename,
        #overwrite_output=True,
        loglevel="error",
        input_args=[
            ('hwaccel', 'cuda'),
            ('f', 'concat'),
            ('safe', '0'),
        ],
        output_args=[
            ('c', 'copy'),
            #('f', 'mp4'),
        ],
    )

    return ffmpeg_cmd.run()




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
    args = parser.parse_args()
    
    # Find video files in the specified directory
    try:
        video_paths = VideoFiles.from_glob(
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
    
    create_montage(
        video_files=video_paths,
        clip_ratio=args.clip_ratio,
        clip_duration=args.clip_duration,
        output_filename=args.output_filename,
        random_seed=args.random_seed,
        num_cores=args.num_cores,
        verbose=args.verbose,
    )
    









def concatenate_clips_direct(clips, output_filename, tmp_dir):
    """Concatenate clips directly using concat demuxer for small numbers of clips."""
    # Create a concat file listing all the clips
    concat_file_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(concat_file_path, 'w') as f:
        for clip_path in clips:
            # Use relative path from the concat file location
            relative_path = os.path.relpath(clip_path, tmp_dir)
            f.write(f"file '{relative_path}'\n")
    
    print(f"Created concat file: {concat_file_path}")
    
    # Create concatenation command using concat demuxer
    concat_cmd = FFMPEG(
        input_files=[concat_file_path],
        output_file=os.path.abspath(output_filename),
        overwrite_output=True,
        vcodec="libx264",
        acodec="aac",
        loglevel="error",
        input_args=[('f', 'concat')]
    )
    
    print(f"Running direct concatenation with {len(clips)} input files...")
    
    # Run the command from the tmp_dir so relative paths work
    if run_ffmpeg_command(concat_cmd, cwd=tmp_dir):
        print(f"\nMontage created successfully: '{output_filename}'")
        return True
    else:
        print(f"\nFailed to create montage: '{output_filename}'", file=sys.stderr)
        return False


def concatenate_clips_recursive(clips, output_filename, tmp_dir, chunk_size: int = 30):
    """Concatenate clips using recursive chunking strategy for large numbers of clips."""
      # Process clips in chunks of 10
    
    if len(clips) <= chunk_size:
        # Base case: use direct concatenation
        return concatenate_clips_direct(clips, output_filename, tmp_dir)
    
    print(f"Processing {len(clips)} clips in chunks of {chunk_size}...")
    
    # Split clips into chunks
    chunks = [clips[i:i + chunk_size] for i in range(0, len(clips), chunk_size)]
    print(f"Created {len(chunks)} chunks")
    
    # Process each chunk to create intermediate montages
    intermediate_montages = []
    for i, chunk in enumerate(chunks):
        chunk_output = os.path.join(tmp_dir, f"chunk_{i}.mp4")
        print(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} clips)...")
        
        if concatenate_clips_direct(chunk, chunk_output, tmp_dir):
            intermediate_montages.append(chunk_output)
        else:
            print(f"Failed to process chunk {i+1}, skipping...")
    
    if not intermediate_montages:
        print("No chunks were processed successfully. Montage creation failed.", file=sys.stderr)
        return False
    
    if len(intermediate_montages) == 1:
        # Only one chunk, just rename it to the final output
        import shutil
        shutil.move(intermediate_montages[0], output_filename)
        print(f"\nMontage created successfully: '{output_filename}'")
        return True
    
    # Recursively combine intermediate montages
    print(f"Combining {len(intermediate_montages)} intermediate montages...")
    return concatenate_clips_recursive(intermediate_montages, output_filename, tmp_dir)

def whatever():
    # Use recursive chunking strategy for efficient concatenation
    if len(processed_clips) <= 10:
        # For small numbers of clips, use direct concatenation
        print(f"Using direct concatenation for {len(processed_clips)} clips...")
        return concatenate_clips_direct(processed_clips, output_filename, tmp_dir)
    else:
        # For larger numbers, use recursive chunking
        print(f"Using recursive chunking strategy for {len(processed_clips)} clips...")
        return concatenate_clips_recursive(processed_clips, output_filename, tmp_dir)


def whatever2(cmd: FFMPEG, cwd: str = None) -> bool:
    with tempfile.TemporaryDirectory() as tmp_dir:

        # Use the high-level FFMPEG interface
        ffmpeg_cmd = FFMPEG(
            input_files=[str(video_file.fpath)],
            output_file=processed_clip_path,
            overwrite_output=True,
            ss=str(start_time),
            duration=str(clip_duration),
            framerate=fps,
            vf=f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            vcodec="h264_nvenc",
            acodec="aac",
            audio_bitrate="192k",
            loglevel="error"
        )
        try:
            ffmpeg_cmd.run()
        except mediatools.ffmpeg.FFMPEGExecutionError as e:
            print(f"  -> Skipping '{video_file.fpath.name}' clip {n+1} due to processing error.")
            #continue

