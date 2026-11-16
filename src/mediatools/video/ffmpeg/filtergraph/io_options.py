'''The ffmpeg input and output options a filtergraph's input and output nodes may set.

Only listed options are accepted: options such as `-f lavfi`, `-filter_script`, `-passlogfile` or
`-x264-params stats=...` would let a graph read or write arbitrary files on the server.
'''
from __future__ import annotations

import re
import typing

import pydantic

IoKind = typing.Literal["time", "int", "number", "text", "flag", "choice"]

_TIME = re.compile(r"^-?(\d+(\.\d+)?(ms|us|s)?|(\d+:)?\d{1,2}:\d{1,2}(\.\d+)?)$")
_INT = re.compile(r"^-?\d+$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?(/\d+(\.\d+)?)?$")
_TEXT = re.compile(r"^[A-Za-z0-9_.+\-:/,=@ ]{0,200}$")


class IoOptionSpec(pydantic.BaseModel):
    name: str = pydantic.Field(description="Option name without the dash, e.g. `c:v`.")
    kind: IoKind
    group: str
    help: str
    choices: list[str] = pydantic.Field([], description="Allowed values for `choice` options.")
    suggestions: list[str] = pydantic.Field([], description="Common values, for `text` options.")


def _opt(name: str, kind: IoKind, group: str, help: str, choices: list[str] | None = None,
         suggestions: list[str] | None = None) -> IoOptionSpec:
    return IoOptionSpec(name=name, kind=kind, group=group, help=help, choices=choices or [], suggestions=suggestions or [])


INPUT_OPTIONS: list[IoOptionSpec] = [
    _opt("ss", "time", "Trim", "Start reading at this position (seconds or hh:mm:ss.ms). Fast: seeks before decoding."),
    _opt("t", "time", "Trim", "Read at most this duration."),
    _opt("to", "time", "Trim", "Stop reading at this position."),
    _opt("sseof", "time", "Trim", "Start relative to the end of the file (negative, e.g. -10)."),
    _opt("itsoffset", "time", "Timing", "Shift this input's timestamps (delay it relative to other inputs)."),
    _opt("r", "number", "Timing", "Force the input frame rate (ignore the file's timestamps)."),
    _opt("framerate", "number", "Timing", "Frame rate for image sequences."),
    _opt("stream_loop", "int", "Looping", "Loop the input this many extra times (-1 = forever; set a duration!)."),
    _opt("loop", "int", "Looping", "Loop a single image (1 = on). Set `t` so it ends."),
    _opt("hwaccel", "choice", "Decoding", "Hardware-accelerated decoding.", ["auto", "cuda", "vaapi", "qsv", "vdpau", "videotoolbox", "none"]),
    _opt("c:v", "text", "Decoding", "Force a video decoder.", suggestions=["h264", "hevc", "h264_cuvid", "hevc_cuvid"]),
    _opt("noautorotate", "flag", "Decoding", "Don't rotate video according to its rotation metadata."),
]

_VIDEO_CODECS = ["libx264", "libx265", "libsvtav1", "libaom-av1", "libvpx-vp9", "h264_nvenc", "hevc_nvenc",
                 "h264_vaapi", "hevc_vaapi", "prores_ks", "mjpeg", "png", "gif", "copy"]
_AUDIO_CODECS = ["aac", "libopus", "libmp3lame", "flac", "pcm_s16le", "libvorbis", "copy"]
_FORMATS = ["mp4", "mov", "matroska", "webm", "gif", "image2", "mp3", "wav", "flac", "ogg", "opus", "ipod",
            "adts", "mpegts", "avi", "apng", "webp"]

OUTPUT_OPTIONS: list[IoOptionSpec] = [
    _opt("c:v", "text", "Video encoding", "Video encoder (`copy` keeps the stream as is; only valid without filtering).", suggestions=_VIDEO_CODECS),
    _opt("crf", "number", "Video encoding", "Constant quality for x264/x265/AV1/VP9: lower is better (x264: 18 = visually lossless, 23 = default)."),
    _opt("preset", "text", "Video encoding", "Speed/size trade-off of the encoder.", suggestions=["ultrafast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "p1", "p4", "p7"]),
    _opt("tune", "text", "Video encoding", "Tune the encoder for a kind of content.", suggestions=["film", "animation", "grain", "stillimage", "fastdecode", "zerolatency"]),
    _opt("b:v", "text", "Video encoding", "Target video bitrate, e.g. 5M."),
    _opt("maxrate", "text", "Video encoding", "Maximum video bitrate (with bufsize)."),
    _opt("minrate", "text", "Video encoding", "Minimum video bitrate."),
    _opt("bufsize", "text", "Video encoding", "Rate-control buffer size, e.g. 10M."),
    _opt("q:v", "number", "Video encoding", "Fixed quality scale for encoders like mjpeg (2-31, lower is better)."),
    _opt("cq", "number", "Video encoding", "Constant quality for NVENC encoders."),
    _opt("qp", "number", "Video encoding", "Constant quantizer."),
    _opt("pix_fmt", "text", "Video encoding", "Pixel format; yuv420p plays everywhere.", suggestions=["yuv420p", "yuv420p10le", "yuv444p", "rgb24", "rgba", "gray"]),
    _opt("profile:v", "text", "Video encoding", "Codec profile.", suggestions=["baseline", "main", "high", "main10"]),
    _opt("level", "text", "Video encoding", "Codec level, e.g. 4.1."),
    _opt("g", "int", "Video encoding", "Keyframe interval (GOP size) in frames."),
    _opt("bf", "int", "Video encoding", "Maximum number of B-frames."),
    _opt("r", "number", "Video encoding", "Output frame rate (drops/duplicates frames; prefer the fps filter)."),
    _opt("fps_mode", "choice", "Video encoding", "How output timestamps are produced.", ["auto", "cfr", "vfr", "passthrough"]),
    _opt("aspect", "text", "Video encoding", "Display aspect ratio, e.g. 16:9."),
    _opt("c:a", "text", "Audio encoding", "Audio encoder (`copy` keeps the stream as is).", suggestions=_AUDIO_CODECS),
    _opt("b:a", "text", "Audio encoding", "Audio bitrate, e.g. 160k."),
    _opt("q:a", "number", "Audio encoding", "Variable audio quality (encoder specific)."),
    _opt("ar", "int", "Audio encoding", "Sample rate in Hz, e.g. 48000."),
    _opt("ac", "int", "Audio encoding", "Number of audio channels."),
    _opt("c:s", "text", "Other streams", "Subtitle encoder.", suggestions=["copy", "mov_text"]),
    _opt("an", "flag", "Other streams", "Drop all audio."),
    _opt("vn", "flag", "Other streams", "Drop all video."),
    _opt("sn", "flag", "Other streams", "Drop all subtitles."),
    _opt("dn", "flag", "Other streams", "Drop all data streams."),
    _opt("map_metadata", "int", "Other streams", "Copy global metadata from this input index (-1 = none)."),
    _opt("map_chapters", "int", "Other streams", "Copy chapters from this input index (-1 = none)."),
    _opt("ss", "time", "Length", "Skip this much of the output (slow: decodes first)."),
    _opt("t", "time", "Length", "Stop writing after this duration."),
    _opt("to", "time", "Length", "Stop writing at this position."),
    _opt("frames:v", "int", "Length", "Stop after this many video frames (e.g. 1 for a still image)."),
    _opt("frames:a", "int", "Length", "Stop after this many audio frames."),
    _opt("fs", "text", "Length", "Stop when the file reaches this size, e.g. 50M."),
    _opt("shortest", "flag", "Length", "Finish when the shortest stream ends."),
    _opt("f", "choice", "Container", "Force the container format (normally taken from the file extension).", _FORMATS),
    _opt("movflags", "text", "Container", "MP4/MOV flags; +faststart lets browsers play before the download finishes.", suggestions=["+faststart"]),
    _opt("loop", "int", "Container", "GIF/APNG loop count (0 = forever, -1 = no loop)."),
    _opt("threads", "int", "Performance", "Encoder threads (0 = automatic)."),
]

INPUT_BY_NAME = {o.name: o for o in INPUT_OPTIONS}
OUTPUT_BY_NAME = {o.name: o for o in OUTPUT_OPTIONS}

ALIASES = {
    "vcodec": "c:v", "codec:v": "c:v", "acodec": "c:a", "codec:a": "c:a", "scodec": "c:s", "codec:s": "c:s",
    "vframes": "frames:v", "aframes": "frames:a", "qscale:v": "q:v", "qscale:a": "q:a", "b": "b:v",
    "profile": "profile:v", "vsync": "fps_mode", "filter:v": "vf", "filter:a": "af", "lavfi": "filter_complex",
}


def validate_io_options(options: typing.Mapping[str, str], specs: typing.Mapping[str, IoOptionSpec]) -> list[str]:
    '''Problems with a node's input or output options; empty if all are allowed and well-formed.'''
    problems = []
    for name, value in options.items():
        spec = specs.get(name)
        if spec is None:
            problems.append(f"-{name} is not supported here")
            continue
        if spec.kind == "flag":
            if value.lower() not in ("", "1", "true", "yes", "0", "false", "no"):
                problems.append(f"-{name} is a switch: use true or false")
            continue
        ok = {
            "time": _TIME.match(value),
            "int": _INT.match(value),
            "number": _NUMBER.match(value),
            "choice": value in spec.choices,
            "text": _TEXT.match(value) and not value.startswith("-"),
        }[spec.kind]
        if not ok:
            hint = f" (one of {', '.join(spec.choices)})" if spec.kind == "choice" else ""
            problems.append(f"-{name}: invalid value {value!r}{hint}")
    return problems


def io_args(options: typing.Mapping[str, str], specs: typing.Mapping[str, IoOptionSpec]) -> tuple[list[tuple[str, str]], list[str]]:
    '''Split options into `-name value` pairs and enabled `-flag`s.'''
    args: list[tuple[str, str]] = []
    flags: list[str] = []
    for name, value in options.items():
        spec = specs.get(name)
        if spec is not None and spec.kind == "flag":
            if value.lower() in ("", "1", "true", "yes"):
                flags.append(name)
        else:
            args.append((name, value))
    return args, flags
