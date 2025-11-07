#!/usr/bin/env python3
"""
Create a video montage from a directory of video files using the high-level FFMPEG interface.

This script re-implements the montage creation functionality using the mediatools.video
interface instead of direct subprocess calls to ffmpeg.
"""

import typing
import os
import sys
import random
from pathlib import Path
import tempfile
import tqdm
import multiprocessing

from .ffmpeg import (FFMPEG, FFMPEGResult, FFInput, FFOutput, stream_filter)
from .probe import probe
from .errors import FFMPEGExecutionError

def create_montage(
    video_files: typing.List[Path], 
    output_filename: str, 
    clip_ratio: float, # 30 would be one clip for every 30 seconds (10x shorter)
    clip_duration: float, 
    random_seed: int = 0, 
    width: int = 1920, 
    height: int = 1080, 
    fps: int = 30, 
    num_cores: int = 16,
    verbose: bool = False,
) -> FFMPEGResult:
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
        FFMPEGResult: The result of the concatenate FFMPEG command.
    """
    clip_infos = get_random_clips(
        video_paths=video_files,
        clip_duration=clip_duration,
        random_seed=random_seed,
        clip_ratio=clip_ratio
    )
    if verbose: print(f'identified {len(clip_infos)} clips. now processing')
    with tempfile.TemporaryDirectory() as tmp_dir:
        #for clip_info in tqdm.tqdm(clip_infos):
        clip_packaged_data = [(clip_info, tmp_dir, clip_duration, width, height, fps, verbose) for clip_info in clip_infos]
        with multiprocessing.Pool(num_cores) as p:
            clip_iter = p.imap_unordered(extract_clip, clip_packaged_data)
            if verbose:
                clip_iter = tqdm.tqdm(clip_iter, total=len(clip_packaged_data))
            
            clip_filenames = []
            for result in clip_iter:
                if result is not None:
                    clip_filenames.append(result)

        clip_filenames = [f for f in clip_filenames if f is not None]

        if verbose: print(f'merging {len(clip_filenames)} clips')
        result = concatenate_clips_demux(
            list(sorted(clip_filenames)), 
            output_filename, 
            tmp_file_path=Path(tmp_dir)/'input_file_list.txt',
        )

    return result


#def extract_clip(
#    clip_info: dict[str,typing.Any], 
#    tmp_dir: Path|str, 
#    clip_duration: float, 
#    width: int, 
#    height: int, 
#    fps: int,
#    verbose: bool = False,
#) -> str|None:
def extract_clip(args) -> str|None:
    clip_info: dict[str,typing.Any] = args[0]
    tmp_dir: Path|str = args[1]
    clip_duration: float = args[2]
    width: int = args[3]
    height: int = args[4]
    fps: int = args[5]
    verbose: bool = args[6]

    processed_clip_path = os.path.join(tmp_dir, f"clip_{clip_info['index']}.mp4")
    #ffmpeg_cmd = FFMPEG(
    #    input_files=[clip_info['fpath']],
    #    output_file=processed_clip_path,
    #    overwrite_output=True,
    #    ss=str(clip_info['start_time']),
    #    duration=str(clip_duration),
    #    framerate=fps,
    #    vf=f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
    #    #vcodec="h264_nvenc",
    #    acodec="aac",  # Ensure audio codec is included
    #    audio_bitrate="192k",  # Set audio bitrate
    #    loglevel="error",
    #    input_args=[
    #        ('hwaccel', 'cuda'),
    #    ],
    #    command_flags=['nostdin'],
    #    output_args=[
    #        ('map', "0:v:0"),
    #        ('map', "0:a:0"),
    #    ],
    #)
    vf = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    cmd = FFMPEG(
        inputs = [FFInput(clip_info['fpath'], ss=str(clip_info['start_time']), t=str(clip_duration))],#, hwaccel='cuda'
        outputs = [FFOutput(processed_clip_path, maps=['0:v:0', '0:a:0'], overwrite=True, vf=vf, framerate=fps, vcodec='h264', acodec='aac', audio_bitrate='192k')],#vcodec='h264_nvenc', 
        loglevel = 'error',
        other_flags=['nostdin'],
    )
    try:
        cmd.run()
        probe(processed_clip_path)  # Ensure the clip was processed correctly
    except FFMPEGExecutionError as e:
        if verbose: print(f"\nFailed to extract '{clip_info['fpath']}' clip {clip_info['index']} due to processing error.")
        if verbose: print(f"{e}")
        return None
    else:
        if verbose: print('\nfinished', processed_clip_path)

    return processed_clip_path
        


def get_random_clips(
    video_paths: typing.List[Path], 
    clip_duration: float, 
    random_seed: int = 0, 
    clip_ratio: float = 30 # one clip for every 30 seconds (10x shorter)
) -> bool:
    '''Extract random clips from the given video files.'''

    random.seed(random_seed)
    video_paths: list[Path] = [Path(path) for path in video_paths]

    if not all([vf.exists() for vf in video_paths]):
        raise ValueError("Error: One or more video files do not exist.")

    if clip_duration <= 0:
        raise ValueError("Error: Clip duration must be a positive number.")
    
    clip_infos: list[dict[str,typing.Any]] = []
    clip_index = 0
    for video_path in sorted(video_paths):

        try:
            duration = probe(video_path).duration
        except FFMPEGExecutionError as e:
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
                'fpath': str(video_path),
                'start_time': start_time,
                'duration': clip_duration,
            })

            clip_index += 1
    return clip_infos



def concatenate_clips_demux(clips: list[Path|str], output_filename: Path|str, tmp_file_path: Path|str) -> FFMPEGResult:
    '''Concatenate video clips using demuxing (fast and lossless).'''
    if not clips:
        raise ValueError("No clips to concatenate.")

    # Create a temporary file list for ffmpeg
    with tmp_file_path.open('w') as f:
        f.write("\n".join([f"file '{c}'" for c in clips]))

    # Build the ffmpeg command
    #ffmpeg_cmd = FFMPEG(
    #    input_files=[str(tmp_file_path)],
    #    output_file=output_filename,
    #    overwrite_output=True,
    #    loglevel="error",
    #    input_args=[
    #        ('hwaccel', 'cuda'),
    #        ('f', 'concat'),
    #        ('safe', '0'),
    #    ],
    #    output_args=[
    #        ('c', 'copy'),  # Copy both video and audio streams
    #        ('f', 'mp4'),  # Ensure output format is MP4
    #    ],
    #)
    cmd = FFMPEG(
        loglevel = 'error',
        inputs = [FFInput(str(tmp_file_path), f='concat', safe='0')],
        outputs = [FFOutput(str(output_filename), vcodec='copy', acodec='copy', overwrite=True)],
    )

    return cmd.run()

