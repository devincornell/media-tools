from __future__ import annotations

import dataclasses
import typing
import pathlib

#import ffmpeg # type: ignore

from .probe_errors import NoVideoStreamError, NoAudioStreamError, ProbeError, NoDurationError

from .stream_info import VideoStreamInfo, AudioStreamInfo

from mediatools.util import get_or_None_factory, VideoTime


@dataclasses.dataclass
class ProbeInfo:
    fname: str
    nb_streams: int
    nb_programs: int
    format_name: str
    format_long_name: str
    start_time: str
    bit_rate: int
    dur: str
    size: int
    probe_score: int
    tags: typing.Dict[str, str | int | bool | float]
    video_streams: typing.List[VideoStreamInfo]
    audio_streams: typing.List[AudioStreamInfo]
    other_streams: typing.List[typing.Dict[str, typing.Any]] # no idea if this will be used.

    #@classmethod
    #def read_from_file(cls, input_fname: str|pathlib.Path, check_for_errors: bool = False) -> typing.Self:
    #    '''Read a file and return an ffprobeinfo.'''
    #    try:
    #        probe_info = ffmpeg.probe(input_fname)
    #    except ffmpeg.Error as e:
    #        raise ProbeError(f'There was a problem probing the file {input_fname}. stdout= {e.stdout}, stderr={e.stderr}') from e
    #    return cls.from_dict(probe_info, check_for_errors=check_for_errors)

    @classmethod
    def from_dict(cls, probe_info: typing.Dict[str,typing.Dict], check_for_errors: bool = False) -> typing.Self:
        '''Parse out streams and format info.'''
        from_info = get_or_None_factory(probe_info['format'])
        o = cls(
            fname = from_info('filename', str), # type: ignore
            nb_streams = from_info('nb_streams',int), # type: ignore
            nb_programs = from_info('nb_programs', int), # type: ignore
            format_name = from_info('format_name', str), # type: ignore
            format_long_name = from_info('format_long_name', str), # type: ignore
            start_time = from_info('start_time', str), # type: ignore
            dur = from_info('duration', str), # type: ignore
            size = from_info('size', int), # type: ignore
            bit_rate = from_info('bit_rate', int), # type: ignore
            probe_score = from_info('probe_score', int), # type: ignore
            tags = from_info('tags', str), # type: ignore
            video_streams = [VideoStreamInfo.from_dict(si, check_for_errors=check_for_errors) for si in probe_info['streams'] if si['codec_type']=='video'],
            audio_streams = [AudioStreamInfo.from_dict(si) for si in probe_info['streams'] if si['codec_type']=='audio'],
            other_streams = [si for si in probe_info['streams'] if si['codec_type'] not in ('video','audio')],
        )
        if check_for_errors:
            o.check_for_errors()

        return o
    
    def check_for_errors(self) -> None:
        '''Check for errors in the probe info.'''
        if self.dur is None or self.dur == 'N/A':
            raise NoDurationError(f'The duration of the file {self.fname} could not be determined.')
        if not self.video_streams:
            raise NoVideoStreamError(f'The file {self.fname} does not contain any video streams.')

    @property
    def file_bitrate(self) -> float:
        '''File size divided by video duration.'''
        return self.size / self.duration

    @property
    def length(self) -> float:
        if self.dur is None or self.dur == 'N/A':
            raise NoDurationError(f'The duration of the file {self.fname} could not be determined, so could not calculate length.')
        return float(self.dur) - float(self.start_time)
    
    @property
    def duration(self) -> float:
        try:
            return float(self.dur)
        except (ValueError,TypeError):
            raise NoDurationError(f'The duration of the file {self.fname} could not be determined. It is likely that the file is not a valid video file or is corrupted.')

    ############################# stream accessors #############################
    @property
    def video(self) -> VideoStreamInfo:
        try:
            return self.video_streams[0]
        except (KeyError,IndexError) as e:
            raise NoVideoStreamError()
    
    @property
    def audio(self) -> AudioStreamInfo:
        try:
            return self.audio_streams[0]
        except (KeyError,IndexError) as e:
            raise NoAudioStreamError()
    
    @property
    def streams(self) -> typing.List[VideoStreamInfo | AudioStreamInfo | typing.Dict]:
        '''All streams'''
        return self.video_streams + self.audio_streams + self.other_streams
