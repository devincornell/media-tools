from __future__ import annotations

import dataclasses
import subprocess
import typing
import shlex
import json
import datetime
from pathlib import Path

from .ffmpeg import FFMPEG, FFMPEGResult, run_ffmpeg_subprocess
from .ffmpeg_errors import FFMPEGError, FFMPEGCommandTimeoutError, FFMPEGExecutionError, FFMPEGNotFoundError
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
    
    #result = self.run(
    #    ffmpeg_command = (
    #        ffmpeg
    #        .input(str(self.vf.fpath))
    #        .output(str(output_fname), vcodec=vcodec, crf=crf, **output_kwargs)
    #    ),
    #    overwrite_output=overwrite,
    #)
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

    #duration = duration_sec if duration_sec is not None else (end_sec - start_sec)
    #stdout = self.run(
    #    ffmpeg_command = (
    #        ffmpeg
    #        .input(self.vf.fpath, ss=start_time.total_seconds())
    #        .output(str(output_fname), t=(end_time-start_time).total_seconds(), **output_kwargs)
    #    ),
    #    overwrite_output=overwrite,
    #)
    #return NewVideoResult.check_file_exists(fpath=output_fname, stdout=stdout)

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

    #stdout = self.run(
    #    ffmpeg_command = (
    #        ffmpeg
    #        .input(str(self.vf.fpath))
    #        .crop(*topleft_point, *size)
    #        .output(str(output_fname), **output_kwargs)
    #    ),
    #    overwrite_output=overwrite,
    #)
    #return NewVideoResult.check_file_exists(fpath=output_fname, stdout=stdout)

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
    Args:
        time_point is the proportion of the video at which to take the thumb (e.g. 0.5 means at half way through.)
    Notes:
        copied from here:
            https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
    '''
    ofp = Path(output_fname)
    if ofp.exists() and not overwrite:
        raise FileExistsError(f'The file {output_fname} already exists. User overwrite=True to overwrite it.')
    
    #try:
    #    probe = self.vf.probe(check_for_errors=True)
    #    ss = int(probe.duration * time_point)
    #except (TypeError, NoDurationError):
    #    ss = .01  # default to 1 second if duration is not available

    #stdout = self.run(
    #    ffmpeg_command = (
    #        ffmpeg
    #        .input(self.vf.fpath, ss=ss)
    #        .filter('scale', width, height)
    #        .output(str(ofp), vframes=1, **output_kwargs)
    #    ),
    #    overwrite_output=overwrite,
    #)
    #return NewThumbResult(ofp, stdout)
    command = FFMPEG(
        input_files=[str(input_fname)],
        output_file=str(ofp),
        ss=time_point_sec,
        vf=f'scale={width}:{height}',
        overwrite_output=overwrite,
        command_args={'vframes': '1'},
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

def probe(fp: str|Path) -> ProbeInfo:
    '''Probe the file in question and return a ProbeInfo object.'''
    return ProbeInfo.from_dict(probe_info=json.loads(probe_dict(fp)), check_for_errors=False)

def probe_dict(fp: str|Path) -> dict[str,typing.Any]:
    '''Probe the file in question and return a dictionary of the probe info.'''
    result = run_ffmpeg_subprocess(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(fp)])
    return result.stdout


