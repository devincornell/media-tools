from __future__ import annotations

import dataclasses
import typing


from .util import get_or_None_factory, VideoTime


@dataclasses.dataclass
class BaseStreamInfo:
    stream_ind: int
    codec_name: typing.Optional[str]
    codec_long_name: typing.Optional[str]
    start_time: typing.Optional[VideoTime]
    start_pts: typing.Optional[int]
    time_base: typing.Optional[str]
    tags: typing.Dict[str,str]
    disposition: typing.Dict[str,bool]

@dataclasses.dataclass
class AudioStreamInfo(BaseStreamInfo):
    sample_fmt: str
    sample_rate: int
    channels: int
    channel_layout: str

    @classmethod
    def from_dict(cls, stream_info: typing.Dict[str,typing.Any]) -> typing.Self:
        from_stream = get_or_None_factory(stream_info)
        return cls(
            stream_ind = from_stream('index', int), # type: ignore
            codec_name = from_stream('codec_name'), # type: ignore
            codec_long_name = from_stream('codec_long_name'), # type: ignore
            start_time = from_stream('start_time', VideoTime), # type: ignore
            start_pts = from_stream('start_pts'), # type: ignore
            time_base = from_stream('time_base'), # type: ignore
            tags = from_stream('tags'), # type: ignore
            sample_fmt = from_stream('sample_fmt'), # type: ignore
            sample_rate = from_stream('sample_rate', int), # type: ignore
            channels = from_stream('channels', int), # type: ignore
            channel_layout = from_stream('channel_layout'), # type: ignore
            disposition = {k:bool(v) for k,v in stream_info['disposition'].items()} if 'disposition' in stream_info else {},
        )

@dataclasses.dataclass
class VideoStreamInfo(BaseStreamInfo):
    height: int
    width: int
    coded_width: typing.Optional[int]
    coded_height: typing.Optional[int]
    bits_per_raw_sample: typing.Optional[int]
    avg_frame_rate: typing.Optional[str]
    r_frame_rate: typing.Optional[str]
    chroma_location: typing.Optional[str]
    color_range: typing.Optional[str]
    color_space: typing.Optional[str]
    field_order: typing.Optional[str]
    has_b_frames: typing.Optional[int]
    closed_captions: typing.Optional[bool]
    is_avc: typing.Optional[str]
    level: typing.Optional[int]
    pix_fmt: typing.Optional[str]
    profile: typing.Optional[str]
    refs: typing.Optional[int]
    start_pts: typing.Optional[int]
    time_base: typing.Optional[str]

    @classmethod
    def from_dict(cls, stream_info: typing.Dict[str,typing.Any]) -> typing.Self:
        #def getter(d,k,t) -> typing.Optional[str | int| bool | float]:
        #    result = d.get(k)
        #    return t(result) if result is not None else None
        from_stream = get_or_None_factory(stream_info)

        return cls(
            stream_ind = from_stream('index'),
            codec_name = from_stream('codec_name'), # type: ignore
            codec_long_name = from_stream('codec_long_name'), # type: ignore
            start_time = from_stream('start_time'), # type: ignore
            start_pts = from_stream('start_pts'), # type: ignore
            time_base = from_stream('time_base'), # type: ignore
            tags = from_stream('tags'), # type: ignore

            height = from_stream('height', int), # type: ignore
            width = from_stream('width', int), # type: ignore
            coded_width = from_stream('coded_width', int),
            coded_height = from_stream('coded_height', int), # type: ignore
            bits_per_raw_sample = from_stream('bits_per_raw_sample', int), # type: ignore

            avg_frame_rate = from_stream('avg_frame_rate'), # type: ignore
            r_frame_rate = from_stream('r_frame_rate'), # type: ignore
            chroma_location = from_stream('chroma_location'), # type: ignore
            color_range = from_stream('color_range'), # type: ignore
            color_space = from_stream('color_space'), # type: ignore
            field_order = from_stream('field_order'), # type: ignore
            has_b_frames = from_stream('has_b_frames', int), # type: ignore
            closed_captions = from_stream('closed_captions', bool), # type: ignore
            is_avc = from_stream('is_avc'), # type: ignore
            level = from_stream('level', int), # type: ignore
            pix_fmt = from_stream('pix_fmt'), # type: ignore
            profile = from_stream('profile'), # type: ignore
            refs = from_stream('refs', int), # type: ignore
            disposition = {k:bool(v) for k,v in stream_info['disposition'].items()} if 'disposition' in stream_info else {},
        )
    
    @property
    def pixels(self) -> int:
        return self.height * self.width

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def resolution(self) -> typing.Tuple[int,int]:
        '''Width by height as a tuple.'''
        return (self.width, self.height)

    @property
    def frame_rate(self) -> int:
        if self.avg_frame_rate is None:
            raise ValueError(f'Average frame rate was not provided.')
        return int(self.avg_frame_rate.split('/')[0])

