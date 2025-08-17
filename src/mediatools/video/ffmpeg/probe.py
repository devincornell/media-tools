from pathlib import Path
import json
import typing
from .errors import FFMPEGExecutionError, ProbeError

from .probe_info import ProbeInfo
from .ffmpeg import run_ffmpeg_subprocess

def probe(fp: str|Path) -> ProbeInfo:
    '''Probe the file in question and return a ProbeInfo object.'''
    return ProbeInfo.from_dict(probe_info=probe_dict(fp), check_for_errors=False)

def probe_dict(fp: str|Path) -> dict[str,typing.Any]:
    '''Probe the file in question and return a dictionary of the probe info.'''
    try:
        result = run_ffmpeg_subprocess(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(fp)])
        return json.loads(result.stdout)
    except FFMPEGExecutionError as e:
        raise ProbeError(f'Error probing file {fp}: {e}') from e
