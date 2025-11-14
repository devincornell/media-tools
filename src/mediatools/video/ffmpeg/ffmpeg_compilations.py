#!/usr/bin/env python3
"""
Create a video montage from a directory of video files using the high-level FFMPEG interface.

This script re-implements the montage creation functionality using the mediatools.video
interface instead of direct subprocess calls to ffmpeg.
"""
from __future__ import annotations
import typing
import os
import sys
import random
from pathlib import Path
import tempfile
import tqdm
import multiprocessing
import dataclasses


from .ffmpeg import (FFMPEG, FFMPEGResult, FFInput, FFOutput, ffinput, ffoutput, stream_filter)
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
    num_cores: int|None = None,
    use_cuda: bool = True,
    verbose: bool = False,
    max_clips_per_video: int = 10,
) -> FFMPEGResult:
    """
    Creates a video montage by randomly sampling clips from videos according to clip_ratio.

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
        clip_ratio=clip_ratio,
        max_clips_per_video=max_clips_per_video,
    )

    return create_compilation(
        clip_infos = clip_infos,
        output_filename = output_filename,
        width = width,
        height= height,
        fps = fps,
        num_cores = num_cores,
        use_cuda = use_cuda,
        verbose = verbose,
    )




def get_random_clips(
    video_paths: typing.List[Path], 
    clip_duration: float, 
    random_seed: int = 0, 
    clip_ratio: float = 30, # one clip for every 30 seconds (10x shorter)
    max_clips_per_video: int = 10,
) -> list[ClipInfo]:
    '''Extract random clips from the given video files.'''

    random.seed(random_seed)
    video_paths: list[Path] = [Path(path) for path in video_paths]

    if not all([vf.exists() for vf in video_paths]):
        raise ValueError("Error: One or more video files do not exist.")

    if clip_duration <= 0:
        raise ValueError("Error: Clip duration must be a positive number.")
    
    clip_infos: list[dict[str,typing.Any]] = []
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
            num_clips = min(num_clips, max_clips_per_video)


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
            
            clip_infos.append(ClipInfo(
                start_time = start_time,
                duration = clip_duration,
                fpath = str(video_path),
            ))

    return clip_infos





def create_compilation(
    clip_infos: typing.List[ClipInfo|tuple[Path, float, float]],
    output_filename: str, 
    width: int = 1920, 
    height: int = 1080, 
    fps: int = 30, 
    num_cores: int|None = None,
    use_cuda: bool = True,
    verbose: bool = False,
    fail_on_error: bool = False,
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
    with tempfile.TemporaryDirectory() as tmp_dir:
        clips = extract_clips(
            clip_infos = [ci if isinstance(ci, ClipInfo) else ClipInfo(fpath=ci[0], start_time=ci[1], duration=ci[2]) for ci in clip_infos],
            clip_dir = tmp_dir,
            width = width,
            height= height,
            fps = fps,
            num_cores = num_cores,
            use_cuda = use_cuda,
            fail_on_error = fail_on_error,
            verbose = verbose,
        )

        result = concatenate_clips_demux(
            list([cp for fp,cp in clips if cp is not None]), 
            output_filename, 
            tmp_file_path=Path(tmp_dir)/'input_file_list.txt',
        )

        return result




def concatenate_clips_demux(
    clips: list[Path|str], 
    output_filename: Path|str, 
    tmp_file_path: Path|str = '_concat_demux_list.txt',
    use_cuda: bool = True,
) -> FFMPEGResult:
    '''Concatenate video clips using demuxing (fast and lossless), assuming they are of compatible types.
    
    '''
    if not clips:
        raise ValueError("No clips to concatenate.")

    tmp_file_path = Path(tmp_file_path)
    output_filename = Path(output_filename)

    # Create a temporary file list for ffmpeg
    if tmp_file_path.exists():
        raise FileExistsError(f"Temporary file {tmp_file_path} already exists - it's just a temporary name.")


    with tempfile.TemporaryFile(mode='w+t') as tmp_file:
        with tmp_file_path.open('w') as f:
            f.write("\n".join([f"file '{c}'" for c in clips]))

        cmd = FFMPEG(
            inputs = [ffinput(str(tmp_file_path), f='concat', safe=0, hwaccel='cuda' if use_cuda else None)],
            outputs = [ffoutput(str(output_filename), c_v='copy', c_a='copy', overwrite=True)],
            loglevel = 'error',
        )

        result = cmd.run()

    return result


@dataclasses.dataclass
class ClipInfo:
    fpath: Path
    start_time: float
    duration: float

    def __post_init__(self):
        self.fpath = Path(self.fpath)

    def check_valid(self) -> bool:
        return self.fpath.exists() and probe(self.fpath).duration >= self.start_time + self.duration


def extract_clips(
    clip_infos: typing.List[ClipInfo], 
    clip_dir: Path|str, 
    width: int, 
    height: int, 
    fps: int,
    num_cores: int|None = None,
    fail_on_error: bool = False,
    verbose: bool = False,
    use_cuda: bool = True,
) -> list[tuple[Path,Path]]:
    '''Extract clips from the given video files, returning a tuple of (video_path, clip_path).
    Args:
        clip_infos (typing.List[ClipInfo]): List of ClipInfo objects specifying clips to extract.
        clip_dir (Path|str): Directory to save extracted clips.
        clip_duration (float): Duration of each clip in seconds.
        width (int): Width of the output clips.
        height (int): Height of the output clips.
        fps (int): Frames per second of the output clips.
        num_cores (int|None, optional): Number of CPU cores to use for parallel processing. Defaults to None (uses all available cores).
        fail_on_error (bool, optional): Whether to raise an error if a clip extraction fails. Defaults to False.
        verbose (bool, optional): Whether to print verbose output. Defaults to False.
    '''
    clip_packaged_data = [(ci, Path(clip_dir)/f"clip_{i}.mp4", width, height, fps, verbose, use_cuda) for i, ci in enumerate(clip_infos)]
    with multiprocessing.Pool(num_cores) as p:
        clip_iter = p.imap_unordered(extract_clip_wrap, clip_packaged_data)
        if verbose:
            clip_iter = tqdm.tqdm(clip_iter, total=len(clip_packaged_data))
        
        clip_filenames = []
        for fp, cp in clip_iter:
            if cp is not None or not fail_on_error:
                clip_filenames.append((fp,cp))
            else:
                raise RuntimeError(f"Clip extraction from {fp} failed.")
        
    return list(sorted(clip_filenames, key=lambda x: x[1]))


def extract_clip_wrap(args) -> str|None:
    '''Accept packaged arguments from imap_unordered and pass to extract_clip.'''
    clip_info: ClipInfo = args[0]
    clip_path: Path|str = args[1]
    width: int = args[2]
    height: int = args[3]
    fps: int = args[4]
    verbose: bool = args[5]
    use_cuda: bool = args[6]
    return extract_clip_process(
        clip_info=clip_info,
        clip_path = clip_path,
        width = width,
        height = height,
        fps = fps,
        verbose = verbose,
        use_cuda = use_cuda,
    )

def extract_clip_process(
    clip_info: ClipInfo, 
    clip_path: Path|str, 
    width: int, 
    height: int, 
    fps: int,
    use_cuda: bool = True,
    verbose: bool = False,
) -> tuple[Path,Path|None]:
    '''Extract a single clip from a video file, returning the path to the processed clip.'''
    processed_clip_path = clip_path
    cmd = FFMPEG(
        inputs = [
            ffinput(
                clip_info.fpath, 
                ss=str(clip_info.start_time), 
                t=str(clip_info.duration),
                hwaccel = 'cuda' if use_cuda else None,
            )
        ],
        outputs = [
            ffoutput(
                processed_clip_path, 
                #maps=['0:v:0', '0:a:0'], 
                overwrite=True, 
                v_f=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1', 
                framerate=fps, 
                c_v='h264_nvenc' if use_cuda else 'h264', 
                c_a='aac', 
                b_a='192k', 
                ar='48000',
                pix_fmt='yuv420p',
                preset='veryfast',
                crf=23,
            )
        ],
        loglevel = 'error',
        other_flags=['nostdin'],
    )
    verbose = True
    try:
        cmd.run()
        probe(processed_clip_path)  # Ensure the clip was processed correctly
    except FFMPEGExecutionError as e:
        if verbose: print(f"\nFailed to extract '{clip_info.fpath}' clip {clip_path} due to processing error.")
        if verbose: print(f"{e}")
        processed_clip_path = None
    else:
        if verbose: print('\nfinished', processed_clip_path)

    return clip_info.fpath, processed_clip_path
    
