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
from .ffmpeg import FFMPEG, FFInput, FFOutput, FFInputArgs, ffinput, ffoutput, FFMPEGResult, ProbeInfo, NoDurationError, probe, LOGLEVEL_OPTIONS



@dataclasses.dataclass(repr=False)
class VideoFile:
    '''Represents a video file.'''
    fpath: Path
    meta: dict[str, dict|str|int|float|bool|list|None] = dataclasses.field(default_factory=dict)
    
    @classmethod
    def from_path(cls,
        fpath: str | Path,
        check_exists: bool = True,
        meta: dict[str, dict|str|int|float|bool|list|None] = None,
    ) -> typing.Self:
        fp = Path(fpath)
        if check_exists and (not fp.exists() or not fp.is_file()):
            raise VideoFileDoesNotExistError(f'This video file does not exist: {fp}')
        return cls(fp, meta=meta or {})

    def get_info(self) -> VideoInfo:
        '''Get the video information for this video file.'''
        return VideoInfo.from_video_file(self, do_check=True)
    
    def to_dict(self) -> dict[str, typing.Any]:
        '''Convert the video file to a dictionary representation.'''
        return {
            'fpath': str(self.fpath),
            'meta': self.meta,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> VideoFile:
        '''Create a VideoFile instance from a dictionary representation.'''
        return VideoFile(
            fpath = Path(data['fpath']),
            meta = data.get('meta', {}),
        )


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
                inputs = [ffinput(self.fpath)],
                outputs = [ffoutput(
                    temp_fp,
                    c_v='copy',
                    c_a='copy',
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
        outputs: list[FFOutput],
        input_args: FFInputArgs|None = None,
        # Global command options (matching FFMPEG class exactly)
        filter_complex: str|list[str]|None = None,
        loglevel: LOGLEVEL_OPTIONS|None = None,
        hide_banner: bool = True,
        nostats: bool = True,
        progress: str|None = None,
        passlogfile: str|None = None,
        pass_num: int|None = None,
        # Generic extensibility
        other_args: list[tuple[str,str]]|None = None,
        other_flags: list[str]|None = None,
    ) -> FFMPEG:
        """Execute an FFmpeg command using this video file as input.
        
        This method creates and returns an FFMPEG command object configured with this video
        file as the input and the specified outputs and options. The method provides a
        convenient interface to all FFmpeg global options while using this VideoFile as
        the primary input source.
        
        Args:
            outputs: List of FFOutput objects specifying output files and encoding parameters.
                    Use the ffoutput() convenience function to create these easily.
            input_args: Optional FFInputArgs to specify input-specific options like seeking,
                       hardware acceleration, etc. Use ffinput() args or FFInputArgs directly.
            
            # Global Command Options (matching FFMPEG class)
            filter_complex: Complex filter graph for advanced multi-input/output operations.
                          Can be a string or list of strings that will be joined with semicolons.
            loglevel: FFmpeg logging level ('error', 'warning', 'info', 'quiet', 'panic').
            hide_banner: Whether to hide the FFmpeg banner (default: True).
            nostats: Whether to disable statistics output (default: True).
            progress: File path for writing progress reports.
            passlogfile: Logfile for two-pass encoding.
            pass_num: Encoding pass number for multi-pass encoding.
            
            # Generic Extensibility
            other_args: Additional command arguments as (name, value) tuples.
            other_flags: Additional command flags as strings.
        
        Returns:
            FFMPEG: Configured FFMPEG command object ready to run.
        
        Examples:
            Basic compression:
                >>> vf = VideoFile.from_path("input.mp4")
                >>> cmd = vf.ffmpeg(outputs=[
                ...     ffoutput("output.mp4", c_v="libx264", crf=23, y=True)
                ... ])
                >>> result = cmd.run()
            
            Extract audio track:
                >>> cmd = vf.ffmpeg(outputs=[
                ...     ffoutput("audio.mp3", vn=True, c_a="libmp3lame", y=True)
                ... ])
                >>> result = cmd.run()
            
            Create thumbnail at specific time:
                >>> cmd = vf.ffmpeg(
                ...     outputs=[ffoutput("thumb.jpg", vframes=1, y=True)],
                ...     input_args=FFInputArgs(ss="00:01:30")
                ... )
                >>> result = cmd.run()
            
            Resize with custom filter:
                >>> cmd = vf.ffmpeg(outputs=[
                ...     ffoutput("resized.mp4", 
                ...              v_f="scale=1280:720:force_original_aspect_ratio=decrease",
                ...              y=True)
                ... ])
                >>> result = cmd.run()
            
            Hardware accelerated encoding:
                >>> cmd = vf.ffmpeg(
                ...     outputs=[ffoutput("output.mp4", c_v="h264_nvenc", preset="fast", y=True)],
                ...     input_args=FFInputArgs(hwaccel="cuda")
                ... )
                >>> result = cmd.run()
            
            Two-pass encoding:
                >>> # Pass 1
                >>> cmd1 = vf.ffmpeg(
                ...     outputs=[ffoutput("/dev/null", c_v="libx264", b_v="1000k", f="mp4", an=True)],
                ...     pass_num=1,
                ...     passlogfile="logfile"
                ... )
                >>> result1 = cmd1.run()
                >>> 
                >>> # Pass 2  
                >>> cmd2 = vf.ffmpeg(
                ...     outputs=[ffoutput("output.mp4", c_v="libx264", b_v="1000k", y=True)],
                ...     pass_num=2,
                ...     passlogfile="logfile"
                ... )
                >>> result2 = cmd2.run()
            
            Multiple outputs with different settings:
                >>> cmd = vf.ffmpeg(outputs=[
                ...     ffoutput("high_quality.mp4", c_v="libx264", crf=18, y=True),
                ...     ffoutput("low_quality.mp4", c_v="libx264", crf=30, s="854x480", y=True),
                ...     ffoutput("thumbnail.jpg", vframes=1, ss="00:00:05", y=True)
                ... ])
                >>> result = cmd.run()
            
            Complex filter example (picture-in-picture):
                >>> cmd = vf.ffmpeg(
                ...     outputs=[ffoutput("pip.mp4", y=True)],
                ...     filter_complex="[0:v]scale=1280:720[main];[1:v]scale=320:240[pip];"
                ...                    "[main][pip]overlay=W-w-10:H-h-10[out]",
                ... )
                >>> # Note: This example assumes additional input handling
            
            Quiet operation with custom logging:
                >>> cmd = vf.ffmpeg(
                ...     outputs=[ffoutput("output.mp4", c_v="libx264", y=True)],
                ...     loglevel="quiet",
                ...     progress="progress.txt",
                ...     hide_banner=True
                ... )
                >>> result = cmd.run()
        """
        return FFMPEG(
            inputs=[FFInput(
                path = self.fpath,
                args = input_args or FFInputArgs(),
            )],
            outputs=outputs,
            filter_complex=filter_complex,
            loglevel=loglevel,
            hide_banner=hide_banner,
            nostats=nostats,
            progress=progress,
            passlogfile=passlogfile,
            pass_num=pass_num,
            other_args=other_args or [],
            other_flags=other_flags or [],
        )



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


