'''Build a `FilterGraphDoc` from an ffmpeg command line or from filtergraph text.

Understands `-i`, `-filter_complex`/`-lavfi`, `-vf`/`-af`, `-map`, and the input/output options listed in
`io_options`; anything else is reported and ignored. Positions are left empty for the editor to lay out.
'''
from __future__ import annotations

import dataclasses
import os
import re
import shlex

from .catalog import FilterCatalog, FilterSpec, MediaType, UnknownFilterError
from .compiler import Issue
from .io_options import ALIASES, INPUT_BY_NAME, OUTPUT_BY_NAME
from .model import (
    Edge,
    FilterGraphDoc,
    FilterNode,
    InputNode,
    OutputNode,
    OutputPadDef,
    filter_pads,
)
from .syntax import FiltergraphSyntaxError, ParsedFilter, parse_filtergraph

_GLOBAL_FLAGS = {"y", "n", "hide_banner", "nostats", "stats", "nostdin", "benchmark"}
_GLOBAL_ARGS = {"loglevel", "v", "progress", "stats_period", "filter_threads", "filter_complex_threads"}
_FLAGS = _GLOBAL_FLAGS | {"an", "vn", "sn", "dn", "shortest", "noautorotate", "re", "accurate_seek", "copyts"}
_STREAM = re.compile(r"^(\d+)(?::([vVa])(?::(\d+))?)?(\?)?$")
# Containers without audio (or video), whose streams ffmpeg's automatic selection skips.
_NO_AUDIO = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".apng", ".tif", ".tiff"}
_NO_VIDEO = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}

Endpoint = tuple[str, str]


@dataclasses.dataclass
class _Output:
    path: str
    options: dict[str, str]
    maps: list[str]
    vf: str | None
    af: str | None


def import_command(text: str, catalog: FilterCatalog) -> tuple[FilterGraphDoc, list[Issue]]:
    '''Parse a full `ffmpeg ...` command, or plain filtergraph text, into a document.'''
    text = text.strip().replace("\\\n", " ")
    try:
        tokens = shlex.split(text)
    except ValueError as e:
        return FilterGraphDoc(), [Issue(level="error", message=f"Could not split the command: {e}")]
    if tokens and os.path.basename(tokens[0]) == "ffmpeg":
        tokens = tokens[1:]
    if not tokens or not any(t.startswith("-") for t in tokens):
        return _Builder(catalog).build(inputs=[("in.mp4", {})], filter_complex=text, outputs=[], default_output=True)

    issues: list[Issue] = []
    inputs: list[tuple[str, dict[str, str]]] = []
    outputs: list[_Output] = []
    fc: list[str] = []
    pending: dict[str, str] = {}
    maps: list[str] = []
    vf: str | None = None
    af: str | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("-") or tok == "-":
            outputs.append(_Output(tok, _allowed(pending, OUTPUT_BY_NAME, "output", issues), maps, vf, af))
            pending, maps, vf, af = {}, [], None, None
            i += 1
            continue
        name = ALIASES.get(tok[1:], tok[1:])
        if name in _FLAGS:
            if name not in _GLOBAL_FLAGS:
                pending[name] = "true"
            i += 1
            continue
        if i + 1 >= len(tokens):
            issues.append(Issue(level="warning", message=f"{tok} has no value; ignored."))
            break
        value = tokens[i + 1]
        i += 2
        if name == "i":
            inputs.append((value, _allowed(pending, INPUT_BY_NAME, "input", issues)))
            pending = {}
        elif name == "filter_complex":
            fc.append(value)
        elif name == "vf":
            vf = value
        elif name == "af":
            af = value
        elif name == "map":
            maps.append(value)
        elif name in _GLOBAL_ARGS:
            continue
        else:
            pending[name] = value
    if pending or maps:
        issues.append(Issue(level="warning", message="Options after the last output file were ignored."))
    if not inputs:
        inputs = [("in.mp4", {})]
    doc, more = _Builder(catalog).build(inputs=inputs, filter_complex=";".join(fc), outputs=outputs,
                                        default_output=not outputs)
    return doc, issues + more


def _allowed(options: dict[str, str], specs: dict, where: str, issues: list[Issue]) -> dict[str, str]:
    kept = {}
    for name, value in options.items():
        if name in specs:
            kept[name] = value
        else:
            issues.append(Issue(level="warning", message=f"-{name} isn't supported on an {where}; ignored."))
    return kept


def _slot_name(path: str, index: int, taken: set[str]) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    name = stem if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", stem) and stem not in taken else f"in{index}"
    taken.add(name)
    return name


class _Builder:
    def __init__(self, catalog: FilterCatalog):
        self.catalog = catalog
        self.issues: list[Issue] = []
        self.nodes: list = []
        self.edges: list[Edge] = []
        self.inputs: list[InputNode] = []
        self.labels: dict[str, tuple[Endpoint, MediaType]] = {}
        self.used_labels: set[str] = set()
        self.used_streams: set[tuple[int, str]] = set()
        self.loose: list[tuple[Endpoint, MediaType]] = []
        self.pending: list[tuple[str, Endpoint]] = []
        self.counter = 0

    def _id(self, stem: str) -> str:
        self.counter += 1
        return f"{stem}{self.counter}"

    def build(
        self, inputs: list[tuple[str, dict[str, str]]], filter_complex: str, outputs: list[_Output], default_output: bool,
    ) -> tuple[FilterGraphDoc, list[Issue]]:
        taken: set[str] = set()
        for idx, (path, options) in enumerate(inputs):
            node = InputNode(id=self._id("input"), name=_slot_name(path, idx, taken), options=options)
            self.inputs.append(node)
            self.nodes.append(node)
        try:
            if filter_complex.strip():
                self._add_graph(parse_filtergraph(filter_complex), collect_loose=True)
        except FiltergraphSyntaxError as e:
            self.issues.append(Issue(level="error", message=f"Filtergraph: {e}"))
            return FilterGraphDoc(nodes=self.nodes), self.issues

        if default_output:
            outputs = [_Output("{stem}-studio.mp4", {}, [], None, None)]
        for n, out in enumerate(outputs):
            self._add_output(out, first=n == 0)
        for label in self.labels.keys() - self.used_labels:
            self.issues.append(Issue(level="warning", message=f"[{label}] is never used."))
        return FilterGraphDoc(nodes=self.nodes, edges=self.edges), self.issues

    def _spec(self, name: str) -> FilterSpec | None:
        try:
            return self.catalog.spec(name)
        except UnknownFilterError:
            self.issues.append(Issue(level="error", message=f"Unknown filter '{name}'."))
            return None

    def _add_graph(
        self, chains: list[list[ParsedFilter]], collect_loose: bool, auto_input: int | None = None,
    ) -> list[tuple[Endpoint, MediaType]]:
        '''Add filters; returns the unlabeled outputs at chain ends.'''
        loose: list[tuple[Endpoint, MediaType]] = []
        for chain in chains:
            prev_free: list[tuple[Endpoint, MediaType]] = []
            for pf in chain:
                node, ins, outs = self._add_filter(pf)
                if len(pf.in_labels) > len(ins) or len(pf.out_labels) > len(outs):
                    self.issues.append(Issue(level="warning", message=f"{pf.name} has more labels than pads; extra labels ignored."))
                in_iter = iter(ins)
                for label, (key, mtype) in zip(pf.in_labels, in_iter):
                    self._connect_label(label, (node.id, key), mtype)
                for key, mtype in in_iter:
                    if prev_free:
                        src, _ = prev_free.pop(0)
                        self.edges.append(Edge(source=src[0], source_pad=src[1], target=node.id, target_pad=key))
                    else:
                        stream = None if auto_input is None else f"{auto_input}:{'a' if mtype == 'audio' else 'v'}"
                        self._connect_stream(stream, (node.id, key), mtype)
                for label, (key, mtype) in zip(pf.out_labels, outs):
                    self.labels[label] = ((node.id, key), mtype)
                prev_free = [((node.id, key), mtype) for key, mtype in outs[len(pf.out_labels):]]
            loose += prev_free
        if collect_loose:
            self.loose = loose
        return loose

    def _add_filter(self, pf: ParsedFilter) -> tuple[FilterNode, list[tuple[str, MediaType]], list[tuple[str, MediaType]]]:
        spec = self._spec(pf.name)
        args, options = list(pf.args), dict(pf.options)
        if spec is not None and args and len(args) <= len(spec.positional) and not (set(spec.positional[:len(args)]) & options.keys()):
            # Named options are clearer in the editor than positional ones.
            options = {**dict(zip(spec.positional, args)), **options}
            args = []
        node = FilterNode(id=self._id(pf.name), filter=pf.name, args=args, options=options)
        self.nodes.append(node)
        if spec is None:
            return node, [("0", "video")], [("0", "video")]
        pads = filter_pads(spec, node)
        return node, [(p.key, p.type) for p in pads.inputs], [(p.key, p.type) for p in pads.outputs]

    def _connect_label(self, label: str, target: Endpoint, mtype: MediaType) -> None:
        if _STREAM.match(label):
            self._connect_stream(label, target, mtype)
        elif label in self.labels:
            src, _ = self.labels[label]
            self.used_labels.add(label)
            self.edges.append(Edge(source=src[0], source_pad=src[1], target=target[0], target_pad=target[1]))
        else:
            # Labels may be used before they are defined; resolve once everything is parsed.
            self.pending.append((label, target))

    def _stream_source(self, spec: str | None, mtype: MediaType) -> Endpoint | None:
        key = "a" if mtype == "audio" else "v"
        if spec is None:
            for idx in range(len(self.inputs)):
                if (idx, key) not in self.used_streams:
                    break
            else:
                idx = 0
        else:
            m = _STREAM.match(spec)
            assert m
            idx = int(m.group(1))
            if m.group(2):
                key = "a" if m.group(2) == "a" else "v"
            if m.group(3) not in (None, "0"):
                self.issues.append(Issue(level="warning", message=f"[{spec}]: only the first stream of each type is supported; using {idx}:{key}."))
        if idx >= len(self.inputs):
            self.issues.append(Issue(level="error", message=f"Stream {spec} refers to input #{idx}, but there are only {len(self.inputs)} inputs."))
            return None
        self.used_streams.add((idx, key))
        return (self.inputs[idx].id, key)

    def _connect_stream(self, spec: str | None, target: Endpoint, mtype: MediaType) -> None:
        src = self._stream_source(spec, mtype)
        if src is not None:
            self.edges.append(Edge(source=src[0], source_pad=src[1], target=target[0], target_pad=target[1]))

    def _resolve_deferred(self) -> None:
        for label, target in self.pending:
            if label in self.labels:
                src, _ = self.labels[label]
                self.used_labels.add(label)
                self.edges.append(Edge(source=src[0], source_pad=src[1], target=target[0], target_pad=target[1]))
            else:
                self.issues.append(Issue(level="error", message=f"[{label}] is used but never defined."))
        self.pending = []

    def _add_output(self, out: _Output, first: bool) -> None:
        self._resolve_deferred()
        sources: list[tuple[Endpoint, MediaType]] = []
        if out.maps:
            for m in out.maps:
                label = m[1:-1] if m.startswith("[") and m.endswith("]") else None
                if label is not None:
                    if label in self.labels:
                        sources.append(self.labels[label])
                        self.used_labels.add(label)
                    else:
                        self.issues.append(Issue(level="error", message=f"-map {m}: no such filter output."))
                elif sm := _STREAM.match(m):
                    kinds = [sm.group(2)] if sm.group(2) else ["v", "a"]
                    for kind in kinds:
                        mtype: MediaType = "audio" if kind == "a" else "video"
                        src = self._stream_source(m if sm.group(2) else f"{sm.group(1)}:{kind}", mtype)
                        if src:
                            sources.append((src, mtype))
                else:
                    self.issues.append(Issue(level="warning", message=f"-map {m} isn't supported; ignored."))
        else:
            if first:
                sources += self.loose
                self.loose = []
            ext = os.path.splitext(out.path)[1].lower()
            for kind, chain_text, flag in (("video", out.vf, "vn"), ("audio", out.af, "an")):
                if flag in out.options or any(t == kind for _, t in sources):
                    continue
                if ext in (_NO_AUDIO if kind == "audio" else _NO_VIDEO):
                    continue
                key = "v" if kind == "video" else "a"
                default_src: Endpoint | None = (self.inputs[0].id, key) if self.inputs else None
                if chain_text:
                    try:
                        chains = parse_filtergraph(chain_text)
                    except FiltergraphSyntaxError as e:
                        self.issues.append(Issue(level="error", message=f"-{'vf' if kind == 'video' else 'af'}: {e}"))
                        continue
                    ends = self._add_graph(chains, collect_loose=False, auto_input=0)
                    self._resolve_deferred()
                    sources += ends[:1]
                elif default_src is not None:
                    sources.append((default_src, kind))  # type: ignore[arg-type]
        pads: list[OutputPadDef] = []
        node_id = self._id("output")
        for src, mtype in sources:
            base = "v" if mtype == "video" else "a"
            name = base if not any(p.name == base for p in pads) else f"{base}{len(pads)}"
            pads.append(OutputPadDef(name=name, type=mtype))
            self.edges.append(Edge(source=src[0], source_pad=src[1], target=node_id, target_pad=name))
        stem, ext = os.path.splitext(os.path.basename(out.path))
        filename = os.path.basename(out.path) if "{" in out.path else f"{{stem}}-{stem or 'out'}{ext or '.mp4'}"
        names = {n.name for n in self.nodes if isinstance(n, OutputNode)}
        name = re.sub(r"\{[^}]*\}", "", stem).strip("-_. ")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", name) or name in names:
            name = "out" if "out" not in names else f"out{len(names)}"
        self.nodes.append(OutputNode(id=node_id, name=name, pads=pads, options=out.options, filename=filename))
