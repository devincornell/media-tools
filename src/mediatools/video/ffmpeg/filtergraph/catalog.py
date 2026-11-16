'''What filters the local ffmpeg build offers, read from `ffmpeg -filters` and `ffmpeg -h filter=NAME`.

Introspecting the binary (instead of a hand-written list) means every filter of the installed ffmpeg is
available with exactly the options, defaults, ranges and named constants that ffmpeg itself documents.
'''
from __future__ import annotations

import re
import subprocess
import threading
import typing
from collections.abc import Callable

import pydantic

MediaType = typing.Literal["video", "audio"]
Runner = Callable[[list[str]], str]

FFMPEG_DOCS = "https://ffmpeg.org/ffmpeg-filters.html"

# Filters that read or write arbitrary files, load code, open sockets, or rewrite other filters' options at runtime.
BLOCKED_FILTERS: dict[str, str] = {
    "movie": "reads arbitrary files; use an input node instead",
    "amovie": "reads arbitrary files; use an input node instead",
    "sendcmd": "can change other filters' options (including file paths) at runtime",
    "asendcmd": "can change other filters' options (including file paths) at runtime",
    "zmq": "opens a network socket",
    "azmq": "opens a network socket",
    "ladspa": "loads native plugins",
    "lv2": "loads native plugins",
    "frei0r": "loads native plugins",
    "frei0r_src": "loads native plugins",
    "program_opencl": "runs a program from a file",
    "openclsrc": "runs a program from a file",
    "subtitles": "reads a subtitle file from the server",
    "ass": "reads a subtitle file from the server",
    "signature": "writes files on the server",
    "vidstabdetect": "writes files on the server",
    "vidstabtransform": "reads files from the server",
    "buffer": "internal to ffmpeg",
    "abuffer": "internal to ffmpeg",
    "buffersink": "internal to ffmpeg",
    "abuffersink": "internal to ffmpeg",
}
# Most file options say so in their help text; these don't.
_FILE_OPTION_NAMES = {"model", "axisfile", "fontfile", "textfile"}
_FILE_HELP = re.compile(r"\b(file|files|filename|path|directory|bitmap|uri|url|address|library)\b", re.IGNORECASE)
_HW_SUFFIXES = ("_cuda", "_npp", "_vaapi", "_qsv", "_opencl", "_vulkan", "_videotoolbox", "_amf", "_d3d11", "_d3d12", "_rkrga")

# Shown first in the palette, with a short plain-language category.
POPULAR: dict[str, str] = {
    "scale": "Resize", "crop": "Resize", "pad": "Resize", "setsar": "Resize", "transpose": "Rotate & flip",
    "rotate": "Rotate & flip", "hflip": "Rotate & flip", "vflip": "Rotate & flip", "gblur": "Blur & sharpen",
    "boxblur": "Blur & sharpen", "unsharp": "Blur & sharpen", "hqdn3d": "Blur & sharpen", "eq": "Color",
    "hue": "Color", "curves": "Color", "colorchannelmixer": "Color", "negate": "Color", "vignette": "Color",
    "format": "Color", "fps": "Time", "setpts": "Time", "trim": "Time", "reverse": "Time", "fade": "Time",
    "xfade": "Time", "minterpolate": "Time", "overlay": "Compose", "hstack": "Compose", "vstack": "Compose",
    "xstack": "Compose", "blend": "Compose", "concat": "Compose", "split": "Compose", "drawtext": "Text & draw",
    "drawbox": "Text & draw", "palettegen": "GIF", "paletteuse": "GIF", "deshake": "Repair", "volume": "Audio",
    "atempo": "Audio", "afade": "Audio", "atrim": "Audio", "areverse": "Audio", "loudnorm": "Audio",
    "highpass": "Audio", "lowpass": "Audio", "amix": "Audio", "amerge": "Audio", "asplit": "Audio",
    "aresample": "Audio", "pan": "Audio", "acrossfade": "Audio", "asetpts": "Audio", "null": "Pass-through",
    "anull": "Pass-through",
}


class OptionConstant(pydantic.BaseModel):
    name: str
    value: str
    help: str = ""


class OptionSpec(pydantic.BaseModel):
    '''One AVOption of a filter, as listed by `ffmpeg -h filter=NAME`.'''

    name: str
    aliases: list[str] = []
    type: str
    help: str = ""
    default: str | None = None
    min: str | None = None
    max: str | None = None
    constants: list[OptionConstant] = []
    media: list[MediaType] = []
    runtime: bool = pydantic.Field(False, description="Can be changed while running (ffmpeg flag T).")
    blocked: bool = False


class PadSpec(pydantic.BaseModel):
    name: str
    type: MediaType


class PadRule(pydantic.BaseModel):
    '''How a side's pads are determined: fixed, counted by an option, concat's n*(v+a), or set by hand.'''

    kind: typing.Literal["fixed", "count", "concat", "manual"] = "fixed"
    option: str | None = None
    default: int = 0
    type: MediaType = "video"


class FilterSummary(pydantic.BaseModel):
    name: str
    description: str
    inputs: str = pydantic.Field(description="ffmpeg's input code: V, A, VV, N (dynamic) or | (source).")
    outputs: str = pydantic.Field(description="ffmpeg's output code: V, A, N (dynamic) or | (sink).")
    timeline: bool
    slice_threading: bool
    category: str
    popular: bool = False
    blocked: bool = False


class FilterSpec(FilterSummary):
    input_pads: list[PadSpec] = []
    output_pads: list[PadSpec] = []
    input_rule: PadRule = PadRule()
    output_rule: PadRule = PadRule()
    options: list[OptionSpec] = []
    positional: list[str] = pydantic.Field([], description="Option names in the order positional values fill them.")
    blocked_reason: str | None = None
    doc_url: str = FFMPEG_DOCS

    def option(self, name: str) -> OptionSpec | None:
        for opt in self.options:
            if opt.name == name or name in opt.aliases:
                return opt
        return None


class UnknownFilterError(LookupError):
    '''The filter does not exist in this ffmpeg build.'''


class FFmpegUnavailableError(RuntimeError):
    '''ffmpeg could not be run.'''


def doc_url(name: str) -> str:
    # The manual's anchors are texinfo-encoded: `_` becomes `_005f`.
    return f"{FFMPEG_DOCS}#{name.replace('_', '_005f')}"


def _category(name: str, ins: str, outs: str) -> str:
    if name in POPULAR:
        return POPULAR[name]
    if name.endswith(_HW_SUFFIXES) or name.startswith("hw"):
        return "Hardware"
    if ins == "|":
        return "Video sources" if "V" in outs else "Audio sources" if "A" in outs else "Sources"
    if outs == "|":
        return "Sinks"
    if len(ins) > 1 or ins == "N" or len(outs) > 1 or outs == "N":
        return "Multiple inputs/outputs"
    if ins == "A" and outs == "V":
        return "Audio visualization"
    if ins == "A":
        return "Audio"
    return "Video"


_LIST_LINE = re.compile(r"^\s*([TSC.]{2,3})\s+(\S+)\s+([AVN|]+)->([AVN|]+)\s+(.*)$")


def parse_filter_list(text: str) -> list[FilterSummary]:
    '''Parse `ffmpeg -filters`.'''
    out = []
    for line in text.splitlines():
        m = _LIST_LINE.match(line)
        if not m:
            continue
        flags, name, ins, outs, desc = m.groups()
        out.append(FilterSummary(
            name=name, description=desc.strip(), inputs=ins, outputs=outs,
            timeline="T" in flags, slice_threading="S" in flags, category=_category(name, ins, outs),
            popular=name in POPULAR, blocked=name in BLOCKED_FILTERS,
        ))
    return out


_OPTION_LINE = re.compile(r"^   (\S+)\s+<([\w ]+)>\s+([.A-Z]{11})(?:\s(.*))?$")
_CONST_LINE = re.compile(r"^     (\S+)\s+(?:(\S+)\s+)?([.A-Z]{11})(?:\s(.*))?$")
_PAD_LINE = re.compile(r"^\s+#(\d+):\s+(.+?)\s+\((\w+)\)\s*$")
_DEFAULT = re.compile(r"\s*\(default (.*)\)\s*$")
_RANGE = re.compile(r"\s*\(from (\S+) to (\S+)\)")


def _split_help(text: str) -> tuple[str, str | None, str | None, str | None]:
    default = vmin = vmax = None
    if m := _DEFAULT.search(text):
        default = m.group(1)
        if len(default) >= 2 and default[0] == default[-1] == '"':
            default = default[1:-1]
        text = text[:m.start()]
    if m := _RANGE.search(text):
        vmin, vmax = m.groups()
        text = text[:m.start()] + text[m.end():]
    return text.strip(), default, vmin, vmax


def _is_file_option(opt: OptionSpec) -> bool:
    return opt.type in ("string", "dictionary") and (opt.name in _FILE_OPTION_NAMES or bool(_FILE_HELP.search(opt.help)))


def parse_filter_help(text: str, summary: FilterSummary) -> FilterSpec:
    '''Parse `ffmpeg -h filter=NAME` into pads, pad rules and options.'''
    lines = text.splitlines()
    description = summary.description
    pads: dict[str, list[PadSpec]] = {"in": [], "out": []}
    dynamic = {"in": False, "out": False}
    side: str | None = None
    options: list[OptionSpec] = []
    seen: set[str] = set()
    positional: list[str] = []
    section = 0
    current: OptionSpec | None = None
    last_key: tuple[str, str, str | None] | None = None
    timeline = summary.timeline

    for i, line in enumerate(lines):
        if i == 1 and line.startswith("  ") and line.strip():
            description = line.strip()
            continue
        stripped = line.strip()
        if stripped == "Inputs:":
            side = "in"
            continue
        if stripped == "Outputs:":
            side = "out"
            continue
        if "support for timeline" in stripped:
            timeline = True
            continue
        if stripped.endswith("AVOptions:"):
            side = None
            section += 1
            last_key = None
            continue
        if side is not None:
            if m := _PAD_LINE.match(line):
                kind = m.group(3)
                pads[side].append(PadSpec(name=m.group(2), type="audio" if kind == "audio" else "video"))
            elif stripped.startswith("dynamic"):
                dynamic[side] = True
            continue
        if m := _OPTION_LINE.match(line):
            name, otype, flags, rest = m.group(1), m.group(2).strip(), m.group(3), m.group(4) or ""
            help_text, default, vmin, vmax = _split_help(rest)
            key = (otype, help_text, default)
            media: list[MediaType] = [t for t, f in (("video", "V"), ("audio", "A")) if f in flags]  # type: ignore[misc]
            if section == 1 and last_key == key and current is not None:
                current.aliases.append(name)
                seen.add(name)
                continue
            last_key = key if section == 1 else None
            if name in seen:
                current = None
                continue
            seen.add(name)
            current = OptionSpec(
                name=name, type=otype, help=help_text, default=default, min=vmin, max=vmax,
                media=media, runtime="T" in flags,
            )
            current.blocked = _is_file_option(current)
            options.append(current)
            if section == 1:
                positional.append(name)
            continue
        # Constants listed again under an alias are skipped.
        m = _CONST_LINE.match(line)
        if m and current is not None and not any(c.name == m.group(1) for c in current.constants):
            current.constants.append(OptionConstant(name=m.group(1), value=m.group(2) or "", help=(m.group(4) or "").strip()))

    if timeline and not any(o.name == "enable" for o in options):
        options.append(OptionSpec(
            name="enable", type="string", runtime=True,
            help="Timeline: expression that turns the filter on/off per frame, e.g. between(t,2,5).",
        ))

    blocked_reason = BLOCKED_FILTERS.get(summary.name)
    media_hint: MediaType = _media_hint(summary, options)
    return FilterSpec(
        **summary.model_dump(exclude={"description", "timeline", "blocked"}),
        description=description,
        timeline=timeline,
        blocked=blocked_reason is not None,
        blocked_reason=blocked_reason,
        input_pads=pads["in"],
        output_pads=pads["out"],
        input_rule=_pad_rule(summary.name, "inputs", pads["in"], dynamic["in"], options, media_hint),
        output_rule=_pad_rule(summary.name, "outputs", pads["out"], dynamic["out"], options, media_hint),
        options=options,
        positional=positional,
        doc_url=doc_url(summary.name),
    )


def _media_hint(summary: FilterSummary, options: list[OptionSpec]) -> MediaType:
    for code in (summary.inputs, summary.outputs):
        if code and set(code) <= {"A"}:
            return "audio"
        if code and set(code) <= {"V"}:
            return "video"
    for opt in options:
        if opt.media == ["audio"]:
            return "audio"
        if opt.media == ["video"]:
            return "video"
    return "audio" if summary.name.startswith("a") else "video"


_COUNT_OPTIONS = {"inputs": ("inputs", "nb_inputs"), "outputs": ("outputs", "nb_outputs")}


def _pad_rule(
    name: str, side: str, listed: list[PadSpec], dynamic: bool, options: list[OptionSpec], media: MediaType,
) -> PadRule:
    if not dynamic:
        return PadRule(kind="fixed")
    if name == "concat":
        return PadRule(kind="concat")
    if not listed:
        for opt in options:
            if opt.name in _COUNT_OPTIONS[side] and opt.type in ("int", "int64"):
                default = int(opt.default) if opt.default and opt.default.lstrip("-").isdigit() else 2
                return PadRule(kind="count", option=opt.name, default=default, type=media)
    return PadRule(kind="manual", default=0 if listed else 1, type=media)


def _run_ffmpeg(args: list[str]) -> str:
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", *args], capture_output=True, text=True, timeout=30, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise FFmpegUnavailableError(f"Could not run ffmpeg: {e}") from e
    return result.stdout


class FilterCatalog:
    '''Cached view of the filters available in the local ffmpeg build. Thread-safe.'''

    def __init__(self, runner: Runner = _run_ffmpeg):
        self._run = runner
        self._lock = threading.Lock()
        self._summaries: dict[str, FilterSummary] | None = None
        self._specs: dict[str, FilterSpec] = {}
        self._version: str | None = None

    def version(self) -> str:
        if self._version is None:
            first = self._run(["-version"]).splitlines()[:1]
            self._version = first[0] if first else "unknown"
        return self._version

    def filters(self) -> list[FilterSummary]:
        with self._lock:
            if self._summaries is None:
                self._summaries = {f.name: f for f in parse_filter_list(self._run(["-filters"]))}
                if not self._summaries:
                    self._summaries = None
                    raise FFmpegUnavailableError("ffmpeg returned no filters")
            return list(self._summaries.values())

    def summary(self, name: str) -> FilterSummary | None:
        self.filters()
        assert self._summaries is not None
        return self._summaries.get(name)

    def spec(self, name: str) -> FilterSpec:
        summary = self.summary(name)
        if summary is None:
            raise UnknownFilterError(f"Unknown filter: {name}")
        with self._lock:
            if name not in self._specs:
                self._specs[name] = parse_filter_help(self._run(["-h", f"filter={name}"]), summary)
            return self._specs[name]
