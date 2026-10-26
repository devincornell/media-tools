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


from .core.command import (FFMPEG, FFMPEGResult, FFInput, FFOutput, ffinput, ffoutput)
from .core.probe import probe
from .core.errors import FFMPEGExecutionError

def create_montage(
    video_files: typing.List[Path], 
    output_filename: str, 
    clip_ratio: float|None = None, # seconds of source per clip; 90 with 2s clips is ~45x shorter
    clip_duration: float = 2.0,
    random_seed: int = 0, 
    width: int = 1920, 
    height: int = 1080, 
    fps: int = 30, 
    num_cores: int|None = None,
    use_cuda: bool = False,
    verbose: bool = False,
    max_clips_per_video: int|None = None,
    max_total_clips: int|None = None,
    shuffle_clips: bool = False,
    overwrite: bool = False,
    tmp_dir: Path|str|None = None,
    target_duration: float|None = None,
) -> FFMPEGResult:
    """
    Creates a video montage by randomly sampling clips from videos.

    Give either `target_duration` (desired montage length in seconds; clips are shared out
    in proportion to each video's length) or `clip_ratio` (one clip per that many seconds of source).

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
        target_duration=target_duration,
    )

    if shuffle_clips:
        random.seed(random_seed)
        random.shuffle(clip_infos)

    if max_total_clips is not None and len(clip_infos) > max_total_clips:
        clip_infos = clip_infos[:max_total_clips]

    return create_compilation(
        clip_infos = clip_infos,
        output_filename = output_filename,
        width = width,
        height= height,
        fps = fps,
        num_cores = num_cores,
        use_cuda = use_cuda,
        verbose = verbose,
        overwrite = overwrite,
        tmp_dir = tmp_dir,
    )




def get_random_clips(
    video_paths: typing.List[Path], 
    clip_duration: float, 
    random_seed: int = 0, 
    clip_ratio: float|None = None,
    max_clips_per_video: int|None = None,
    target_duration: float|None = None,
) -> list[ClipInfo]:
    '''Extract random clips from the given video files.'''

    if (clip_ratio is None) == (target_duration is None):
        raise ValueError("Specify exactly one of clip_ratio or target_duration.")

    random.seed(random_seed)
    video_paths: list[Path] = [Path(path) for path in video_paths]

    if not all([vf.exists() for vf in video_paths]):
        raise ValueError("Error: One or more video files do not exist.")

    if clip_duration <= 0:
        raise ValueError("Error: Clip duration must be a positive number.")

    durations: list[tuple[Path, float]] = []
    for video_path in sorted(video_paths):
        try:
            duration = probe(video_path).duration
        except FFMPEGExecutionError as e:
            continue
        if duration:
            durations.append((video_path, duration))

    if target_duration is not None:
        counts = _allocate_clip_counts(
            [d for _, d in durations], round(target_duration / clip_duration), clip_duration, max_clips_per_video,
        )
    else:
        counts = []
        for _, duration in durations:
            if duration < clip_duration:
                n = 1
            else:
                n = max(1, int(duration / clip_ratio))
                if max_clips_per_video is not None:
                    n = min(n, max_clips_per_video)
            counts.append(n)

    all_clip_infos: list[ClipInfo] = []
    for (video_path, duration), num_clips in zip(durations, counts):
        if num_clips == 0:
            continue

        vid_clip_infos: list[ClipInfo] = []
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
            
            vid_clip_infos.append(ClipInfo(
                start_time = start_time,
                duration = clip_duration,
                path = str(video_path),
            ))
        
        all_clip_infos.extend(list(sorted(vid_clip_infos, key=lambda x: x.start_time)))

    return all_clip_infos


def _allocate_clip_counts(
    durations: list[float], total_clips: int, clip_duration: float, max_per_video: int|None,
) -> list[int]:
    '''Share `total_clips` across videos in proportion to length (largest remainder), capped by what each video can hold.'''
    total_len = sum(durations)
    if total_len <= 0 or total_clips <= 0:
        return [0] * len(durations)
    caps = [max(1, int(d / clip_duration)) for d in durations]
    if max_per_video is not None:
        caps = [min(c, max_per_video) for c in caps]
    quotas = [total_clips * d / total_len for d in durations]
    counts = [min(int(q), c) for q, c in zip(quotas, caps)]
    remaining = total_clips - sum(counts)
    by_remainder = sorted(range(len(durations)), key=lambda i: quotas[i] - int(quotas[i]), reverse=True)
    for i in by_remainder:
        if remaining <= 0:
            break
        if counts[i] < caps[i]:
            counts[i] += 1
            remaining -= 1
    return counts





def create_compilation(
    clip_infos: typing.List[ClipInfo|tuple[Path, float, float]],
    output_filename: str, 
    width: int = 1920, 
    height: int = 1080, 
    fps: int = 30, 
    num_cores: int|None = None,
    use_cuda: bool = False,
    overwrite: bool = False,
    verbose: bool = False,
    fail_on_error: bool = False,
    tmp_dir: Path|str|None = None,
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
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp_dir:
        clips = extract_clips(
            clip_infos = [ci if isinstance(ci, ClipInfo) else ClipInfo(path=ci[0], start_time=ci[1], duration=ci[2]) for ci in clip_infos],
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
            use_cuda=use_cuda,
            overwrite=overwrite,
        )

        return result




def concatenate_clips_demux(
    clips: list[Path|str], 
    output_filename: Path|str, 
    tmp_file_path: Path|str = '_concat_demux_list.txt',
    use_cuda: bool = False,
    overwrite: bool = False,
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
            outputs = [ffoutput(str(output_filename), c_v='copy', c_a='copy', y=overwrite)],
            loglevel = 'error',
        )

        result = cmd.run()

    return result


@dataclasses.dataclass
class ClipInfo:
    path: Path
    start_time: float
    duration: float

    def __post_init__(self):
        self.path = Path(self.path)

    def check_valid(self) -> bool:
        return self.path.exists() and probe(self.path).duration >= self.start_time + self.duration


def extract_clips(
    clip_infos: typing.List[ClipInfo], 
    clip_dir: Path|str, 
    width: int, 
    height: int, 
    fps: int,
    num_cores: int|None = None,
    fail_on_error: bool = False,
    verbose: bool = False,
    use_cuda: bool = False,
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
    clip_packaged_data = [(ci, Path(clip_dir)/f"clip_{i:05}.mp4", width, height, fps, verbose, use_cuda) for i, ci in enumerate(clip_infos)]
    # Each x264 encode is itself multithreaded and memory-hungry at high resolutions, so don't default to one per core.
    num_cores = num_cores or max(1, (os.cpu_count() or 4) // 4)
    threads = max(1, (os.cpu_count() or num_cores) // num_cores)
    clip_packaged_data = [(*d, threads) for d in clip_packaged_data]
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
                    
    return list(sorted(clip_filenames, key=lambda x: str(x[1])))


def extract_clip_wrap(args) -> str|None:
    '''Accept packaged arguments from imap_unordered and pass to extract_clip.'''
    clip_info: ClipInfo = args[0]
    clip_path: Path|str = args[1]
    width: int = args[2]
    height: int = args[3]
    fps: int = args[4]
    verbose: bool = args[5]
    use_cuda: bool = args[6]
    threads: int = args[7]
    return extract_clip_process(
        clip_info=clip_info,
        clip_path = clip_path,
        width = width,
        height = height,
        fps = fps,
        verbose = verbose,
        use_cuda = use_cuda,
        threads = threads,
    )

def extract_clip_process(
    clip_info: ClipInfo, 
    clip_path: Path|str, 
    width: int, 
    height: int, 
    fps: int,
    use_cuda: bool = False,
    verbose: bool = False,
    threads: int|None = None,
) -> tuple[Path,Path|None]:
    '''Extract a single clip from a video file, returning the path to the processed clip.'''
    processed_clip_path = clip_path
    cmd = FFMPEG(
        inputs = [
            ffinput(
                clip_info.path, 
                ss=str(clip_info.start_time), 
                t=str(clip_info.duration),
                hwaccel = 'cuda' if use_cuda else None,
            )
        ],
        outputs = [
            ffoutput(
                processed_clip_path, 
                #maps=['0:v:0', '0:a:0'], 
                y=True, 
                v_f=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1', 
                framerate=fps, 
                c_v='h264_nvenc' if use_cuda else 'h264', 
                c_a='aac', 
                b_a='192k', 
                ar='48000',
                pix_fmt='yuv420p',
                preset='veryfast',
                crf=23,
                threads=threads,
            )
        ],
        loglevel = 'error',
        other_flags=['nostdin'],
    )
    #verbose = True
    try:
        cmd.run()
        probe(processed_clip_path)  # Ensure the clip was processed correctly
    except FFMPEGExecutionError as e:
        if verbose: print(f"\nFailed to extract '{clip_info.path}' clip {clip_path} due to processing error.")
        if verbose: print(f"{e}")
        processed_clip_path = None
    else:
        #if verbose: print('\nfinished', processed_clip_path)
        pass
    return clip_info.path, processed_clip_path
    
