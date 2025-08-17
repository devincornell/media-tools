from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
import json
import datetime
from pathlib import Path

from .ffmpeg import FFMPEG, FFMPEGResult, run_ffmpeg_subprocess
from .errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError
from .probe_info import ProbeInfo

XCoord = int
YCoord = int
Height = int
Width = int


######################## Video Manipulation Methods ########################
def compress(
    input_fname: str|Path,
    output_fname: Path, 
    vcodec: str = 'libx264', 
    crf: int = 30, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Compress a video to the specified format and return a videofile of the output file.'''
    output_fname = Path(output_fname)

    if not overwrite and output_fname.exists():
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(output_fname),
        vcodec=vcodec,
        crf=crf,
        overwrite_output=overwrite,
        **output_kwargs
    )

    return command.run()

def splice(
    input_fname: str|Path,
    output_fname: Path, 
    start_time: datetime.timedelta, 
    end_time: datetime.timedelta, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Splice video given a start time and end time.'''
    output_fname = Path(output_fname)
    if output_fname.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(output_fname),
        ss=start_time.total_seconds(),
        duration=(end_time - start_time).total_seconds(),
        overwrite_output=overwrite,
        **output_kwargs
    )
    return command.run()


def crop(
    input_fname: str|Path,
    output_fname: Path, 
    topleft_point: typing.Tuple[XCoord, YCoord],
    size: typing.Tuple[Width,Height],
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Crop the video where the top-left of the frame is at 
    Args:
        topleft_point: (start_x,start_y)
        size: (width,height)
    '''
    output_fname = Path(output_fname)
    if output_fname.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')

    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(output_fname),
        vf=f'crop={size[0]}:{size[1]}:{topleft_point[0]}:{topleft_point[1]}',
        overwrite_output=overwrite,
        **output_kwargs
    )
    return command.run()


def make_thumb(
    input_fname: str|Path,
    output_fname: str, 
    time_point_sec: float = 0.5, 
    height: int = -1, 
    width: int = -1, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Make a thumbnail from this video.
    Notes:
        copied from here:
            https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
    '''
    ofp = Path(output_fname)
    if ofp.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(ofp),
        ss=time_point_sec,
        vf=f'scale={width}:{height}',
        overwrite_output=overwrite,
        command_args=[('vframes', '1')],
        **output_kwargs
    )
    return command.run()

def make_animated_thumb(
    input_fname: str|Path,
    output_fname: str, 
    framerate: int,
    sample_period: int,
    height: int = -1, 
    width: int = -1, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Make an animated thumbnail from this video by sampling frames evenly across its duration.
    Args:
        sample_period: the number of seconds between each frame sampled.
        framerate: the number of frames per second in the output gif.
        height: the height of the output gif.
        width: the width of the output gif.
        overwrite: whether to overwrite the output file if it exists.
    '''
    ofp = Path(output_fname)
    if ofp.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(ofp),
        vf=f"setpts=PTS/{sample_period},fps={framerate},scale={width}:{height}:-1",
        overwrite_output=overwrite,
        **output_kwargs
    )
    return command.run()



def make_animated_thumb_v2(
    input_fname: str|Path,
    output_fname: str, 
    framerate: int,
    sample_period: int,
    height: int = -1, 
    width: int = -1, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Make an animated thumbnail from this video by sampling frames evenly across its duration.
    Args:
        sample_period: the number of seconds between each frame sampled.
        framerate: the number of frames per second in the output gif.
        height: the height of the output gif.
        width: the width of the output gif.
        overwrite: whether to overwrite the output file if it exists.
    '''
    ofp = Path(output_fname)
    if ofp.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    #ffmpeg -i input.mp4 -vf "fps=10,scale=400:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" output.gif
    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(ofp),
        vf=f"fps={framerate},scale={width}:{height}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        overwrite_output=overwrite,
        **output_kwargs
    )
    return command.run()





def check_ffmpeg_available() -> bool:
    '''Check if FFMPEG is available on the system.'''
    try:
        run_ffmpeg_subprocess(["ffmpeg", "-version"])
        return True
    except FFMPEGError:
        return False
    
def get_ffmpeg_version() -> str|None:
    '''Retrieve the version of FFMPEG installed on the system.'''
    result = run_ffmpeg_subprocess(["ffmpeg", "-version"])
    lines = result.stdout.strip().split('\n')
    return lines[0]


