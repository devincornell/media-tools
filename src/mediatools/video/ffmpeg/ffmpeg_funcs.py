from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
import json
import datetime
from pathlib import Path

from .ffmpeg import FFMPEG, FFInput, FFOutput, stream_filter, FFMPEGResult, run_ffmpeg_subprocess
from .errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError
from .probe_info import ProbeInfo
from .probe import probe

XCoord = int
YCoord = int
Height = int
Width = int


######################## Video Manipulation Methods ########################
def compress(
    input_fname: str|Path,
    output_fname: Path, 
    vcodec: str = 'libx264', 
    crf: int|None = 30, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Compress a video to the specified format and return a videofile of the output file.'''
    output_fname = Path(output_fname)

    if not overwrite and output_fname.exists():
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    command = FFMPEG(
        inputs=[FFInput(str(input_fname))],
        outputs=[FFOutput(str(output_fname), vcodec=vcodec, crf=crf, overwrite=overwrite)],
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
        inputs=[FFInput(str(input_fname), ss=start_time.total_seconds(), to=end_time.total_seconds())],
        outputs=[FFOutput(str(output_fname), overwrite=overwrite)],
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
        inputs=[FFInput(str(input_fname))],
        outputs=[FFOutput(str(output_fname), vf=f'crop={size[0]}:{size[1]}:{topleft_point[0]}:{topleft_point[1]}', overwrite=overwrite)],
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
        inputs=[FFInput(str(input_fname))],
        outputs=[FFOutput(str(ofp), overwrite=overwrite, vf=f'scale={width}:{height}', vframes=1)],
        ss=time_point_sec,
        **output_kwargs
    )
    return command.run()

def make_animated_thumb(
    input_fname: str|Path,
    output_fname: str, 
    fps: int,
    target_period: int,
    height: int = -1, 
    width: int = -1, 
    overwrite: bool = False, 
    **output_kwargs
) -> FFMPEGResult:
    '''Make an animated thumbnail from this video by speeding up the video and sampling frames evenly.
    Args:
        target_period: the number of seconds the output gif should last.
        fps: the number of frames per second in the output gif.
        height: the height of the output gif.
        width: the width of the output gif.
        overwrite: whether to overwrite the output file if it exists.
    '''
    ofp = Path(output_fname)
    if ofp.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    duration = probe(input_fname).duration
    pts = duration / target_period

    command = FFMPEG(
        inputs=[FFInput(str(input_fname))],
        outputs=[FFOutput(str(ofp), vf=f"setpts=PTS/{pts},fps={fps},scale={width}:{height}:-1", overwrite=overwrite)],
        **output_kwargs
    )
    
    return command.run()


def make_compilation(input_files: list[tuple[str|Path, str|int, str|int]], output_fname: str|Path, overwrite: bool = False, **output_kwargs) -> FFMPEGResult:

    #ffmpeg -i [INPUT_FILE.mov] \
    #    -c:v libx264 -crf 18 \
    #    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1:color=black,setsar=1,fps=30" \
    #    -pix_fmt yuv420p \
    #    -c:a aac -ar 44100 -ac 2 \
    #    [OUTPUT_FILE_processed.mp4]
    pass




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


