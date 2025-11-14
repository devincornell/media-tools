from __future__ import annotations

import sys
import dataclasses
import typing
#import pathlib
from pathlib import Path
import tqdm
import shutil
import datetime
import hashlib
import mediatools.util
import tempfile

from .video_info import VideoInfo
from .errors import VideoFileDoesNotExistError
from .ffmpeg import FFMPEG, FFInput, FFOutput, FFMPEGResult, ProbeInfo, NoDurationError, probe, LOGLEVEL_OPTIONS



@dataclasses.dataclass(repr=False)
class VideoFile:
    '''Represents a video file.'''
    fpath: Path
    
    @classmethod
    def from_path(cls,
        fpath: str | Path,
        check_exists: bool = True,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and (not fp.exists() or not fp.is_file()):
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(fp)

    def get_info(self) -> VideoInfo:
        '''Get the video information for this video file.'''
        return VideoInfo.from_video_file(self, do_check=True)


    ######################## dunder Methods ########################
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.fpath}")'
    
    ######################## File Methods ########################
    def exists(self) -> bool:
        return self.fpath.exists()

    ############################# Utility #############################
    def probe(self) -> ProbeInfo:
        '''Probe the file in question.'''
        return probe(str(self.fpath))
    
    def read_metadata(self) -> dict[str, typing.Any]:
        '''Read metadata from the video file.'''
        pinfo = self.probe()
        return pinfo.tags
    
    def update_metadata(self, new_metadata: dict[str, str], delete_old: bool = False) -> FFMPEGResult:
        '''Update metadata for the video file.'''

        exist_meta = self.read_metadata() if not delete_old else {}
        metadata = {**exist_meta, **new_metadata}
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_fp = Path(tmpdir) / self.fpath.name
            command = FFMPEG(
                inputs = [FFInput(self.fpath)],
                outputs = [FFOutput(
                    temp_fp,
                    vcodec='copy',
                    acodec='copy',
                    metadata=metadata,
                )],
            )
            result = command.run()
            new_meta = probe(temp_fp).tags
            if (new_keys := set(new_meta.keys())) != (exp_keys := set(metadata.keys())):
                missing = exp_keys - new_keys
                raise RuntimeError(f'Metadata update failed. These fields could not be updated: {missing}')
            shutil.move(temp_fp, self.fpath)
            return result

        return command.run()

    def hash(filepath: Path|str, hash_func=hashlib.sha256):
        """Calculate file hash with optimal chunk size."""
        h = hash_func()
        chunk_size = 128 * h.block_size  # Optimal chunk size
    
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                h.update(chunk)
        return h.hexdigest()
    
    def size(self) -> int:
        '''Get the size of the video file in bytes.'''
        return self.fpath.stat().st_size

    ############################# file operations #############################
    def copy(self, new_fpath: Path, overwrite: bool = False) -> VideoFile:
        '''Copy the file to a new location.'''
        new_fpath = Path(new_fpath)
        if new_fpath.exists() and not overwrite:
            raise FileExistsError(f'The file "{new_fpath}" already exists. ')
        shutil.copy2(self.fpath, new_fpath)
        return VideoFile.from_path(new_fpath)
    
    def move(self, new_fpath: Path, overwrite: bool = False) -> VideoFile:
        '''Copy the file to a new location.'''
        if overwrite:
            self.fpath.replace(target=new_fpath)
        else:
            self.fpath.rename(target=new_fpath)
        return VideoFile.from_path(new_fpath)


    ############################# file operations #############################
    def ffmpeg(
        self,
        output_file: str|Path,
        overwrite_output: bool = False,
        ss: str|None = None,
        duration: str|None = None,
        vf: str|None = None,
        af: str|None = None,
        vcodec: str|None = None,
        acodec: str|None = None,
        video_bitrate: str|None = None,
        audio_bitrate: str|None = None,
        framerate: int|None = None,
        format: str|None = None,
        filter_complex: str|None = None,
        disable_audio: bool = False,
        disable_video: bool = False,
        crf: int|None = None,
        preset: str|None = None,
        hwaccel: str|None = None,
        loglevel: LOGLEVEL_OPTIONS|None = None,
        hide_banner: bool = True,
        nostats: bool = True,
        output_args: list[tuple[str,str]]|None = None,
        input_args: list[tuple[str,str]]|None = None,
        command_flags: list[str]|None = None,
    ) -> FFMPEGResult:
        '''Execute an ffmpeg command.'''
        return FFMPEG(
            input_files = [self.fpath],
            output_file = output_file,
            overwrite_output = overwrite_output,
            ss = ss,
            duration = duration,
            vf = vf,
            af = af,
            vcodec = vcodec,
            acodec = acodec,
            video_bitrate = video_bitrate,
            audio_bitrate = audio_bitrate,
            framerate = framerate,
            format = format,
            filter_complex = filter_complex,
            disable_audio = disable_audio,
            disable_video = disable_video,
            crf = crf,
            preset = preset,
            hwaccel = hwaccel,
            loglevel = loglevel,
            hide_banner = hide_banner,
            nostats = nostats,
            output_args = output_args,
            input_args = input_args,
            command_flags = command_flags,
        ).run()



@dataclasses.dataclass
class NewVideoResult:
    vf: VideoFile
    result: FFMPEGResult

    @classmethod
    def from_ffmpeg_result(cls, result: FFMPEGResult, check_exists: bool = False) -> NewVideoResult:
        '''Check that the file exists and return a NewVideoResult.'''
        fpath = Path(result.command.output_file)
        if check_exists and not fpath.exists():
            raise FileNotFoundError(f'The video file "{fpath}" was not found '
                f'even though ffmpeg did not raise an exception.')
        return cls(vf=VideoFile.from_path(fpath), result=result)

@dataclasses.dataclass
class NewThumbResult:
    fp: Path
    result: FFMPEGResult


