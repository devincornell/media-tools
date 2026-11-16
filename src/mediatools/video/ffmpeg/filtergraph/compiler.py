'''Turn a `FilterGraphDoc` into an ffmpeg `-filter_complex` string, inputs and `-map`s, checking it on the way.

Saved graphs used as nodes are inlined; a filter output used by several consumers gets an automatic
`split`/`asplit` (ffmpeg allows each output pad to be used once); straight runs of single-input,
single-output filters are written as a comma-separated chain, the way people write filtergraphs by hand.
'''
from __future__ import annotations

import dataclasses
import re
import shlex
import typing
from collections.abc import Mapping
from typing import Annotated

import pydantic

from ..core.command import FFMPEG, ffinput, ffmpeg, ffoutput
from .catalog import FilterCatalog, FilterSpec, UnknownFilterError
from .io_options import INPUT_BY_NAME, OUTPUT_BY_NAME, io_args, validate_io_options
from .model import (
    FilterGraphDoc,
    FilterNode,
    GraphNode,
    InputNode,
    NodePads,
    OutputNode,
    filter_pads,
    graph_interface,
    input_pads,
    output_pads,
)
from .syntax import format_filter

MAX_DEPTH = 8
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


class Issue(pydantic.BaseModel):
    level: typing.Literal["error", "warning", "info"]
    message: str
    node: Annotated[str | None, pydantic.Field(description="Top-level node the issue belongs to.")] = None
    pad: str | None = None
    side: typing.Literal["in", "out"] | None = None


class CompiledInput(pydantic.BaseModel):
    node: str
    name: str
    index: Annotated[int, pydantic.Field(description="Position among the `-i` inputs, as in `[0:v]`.")]
    args: list[tuple[str, str]]
    flags: list[str]
    sample_path: str | None = None


class CompiledOutput(pydantic.BaseModel):
    node: str
    name: str
    maps: list[str]
    args: list[tuple[str, str]]
    flags: list[str]
    filename: str


class LinkView(pydantic.BaseModel):
    '''How one edge of the document appears in the filtergraph.'''

    source: str
    source_pad: str
    target: str
    target_pad: str
    label: Annotated[str, pydantic.Field(description="Link label (`scale1`) or input stream (`0:v`).")]
    chained: Annotated[bool, pydantic.Field(description="Written as `,` inside a chain, so the label isn't printed.")] = False


class CompiledGraph(pydantic.BaseModel):
    ok: bool
    filter_complex: str
    filter_complex_pretty: str
    inputs: list[CompiledInput]
    outputs: list[CompiledOutput]
    issues: list[Issue]
    pads: dict[str, NodePads]
    links: list[LinkView]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    def ffmpeg_command(
        self,
        input_paths: Mapping[str, str],
        output_paths: Mapping[str, str],
        *,
        overwrite: bool = False,
        progress: str | None = None,
    ) -> FFMPEG:
        '''The ffmpeg command for concrete files, keyed by input/output node id.'''
        if not self.ok:
            raise ValueError("The graph has errors: " + "; ".join(i.message for i in self.errors))
        return ffmpeg(
            inputs=[
                ffinput(input_paths[i.node], other_args=list(i.args), other_flags=list(i.flags))
                for i in self.inputs
            ],
            outputs=[
                ffoutput(output_paths[o.node], y=overwrite, maps=list(o.maps), other_args=list(o.args), other_flags=list(o.flags))
                for o in self.outputs
            ],
            filter_complex=self.filter_complex or None,
            progress=progress,
        )

    def preview(self) -> str:
        '''The command with placeholder file names, for display.'''
        if not self.ok or not self.outputs:
            return ""
        cmd = self.ffmpeg_command(
            {i.node: i.sample_path or f"{i.name}.mp4" for i in self.inputs},
            {o.node: o.filename.replace("{stem}", "input").replace("{output}", o.name).replace("{graph}", "graph") for o in self.outputs},
        )
        return " ".join(shlex.quote(a) for a in cmd.build_command())


@dataclasses.dataclass(frozen=True)
class GraphRef:
    '''A saved graph available for `graph` nodes.'''

    name: str
    doc: FilterGraphDoc


@dataclasses.dataclass
class _Flat:
    id: str
    kind: str  # input, output, filter, relay
    origin: str
    inner: bool
    pads: NodePads
    node: InputNode | FilterNode | OutputNode | None = None
    spec: FilterSpec | None = None


Endpoint = tuple[str, str]
_AnyNode = InputNode | FilterNode | GraphNode | OutputNode


def compile_graph(
    doc: FilterGraphDoc,
    catalog: FilterCatalog,
    refs: Mapping[str, GraphRef] | None = None,
    values: Mapping[str, str] | None = None,
) -> CompiledGraph:
    '''Compile `doc`; `values` replaces the defaults of its parameters.'''
    return _Compiler(catalog, refs or {}).run(doc, values or {})


def referenced_graph_ids(doc: FilterGraphDoc) -> set[str]:
    return {n.graph_id for n in doc.nodes if isinstance(n, GraphNode)}


class _Compiler:
    def __init__(self, catalog: FilterCatalog, refs: Mapping[str, GraphRef]):
        self.catalog = catalog
        self.refs = refs
        self.issues: list[Issue] = []
        self.nodes: dict[str, _Flat] = {}
        self.edges: list[tuple[Endpoint, Endpoint]] = []
        self.ports: dict[str, dict[str, dict[str, Endpoint]]] = {}
        self.top_pads: dict[str, NodePads] = {}
        self.top_edges: list[tuple[Endpoint, Endpoint]] = []
        self.top_nodes: dict[str, _AnyNode] = {}

    def issue(self, level: str, message: str, node: str | None = None, pad: str | None = None, side: str | None = None) -> None:
        self.issues.append(Issue(level=level, message=message, node=node, pad=pad, side=side))  # type: ignore[arg-type]

    # ------------------------------------------------------------------ driver

    def run(self, doc: FilterGraphDoc, values: Mapping[str, str]) -> CompiledGraph:
        names = {p.name for p in doc.params}
        for key in values:
            if key not in names:
                self.issue("error", f"The graph has no parameter '{key}'.")
        used = {p for n in doc.nodes for p in n.params.values()}
        for p in doc.params:
            if p.name not in used:
                self.issue("warning", f"Parameter '{p.name}' isn't used by any option.")
        self._flatten(doc, prefix="", stack=(), origin=None, context="", values=doc.param_values(values))
        # From here on, top-level nodes carry their parameter values as plain options.
        doc = doc.model_copy(update={"nodes": [self.top_nodes.get(n.id, n) for n in doc.nodes]})
        if not any(isinstance(n, OutputNode) for n in doc.nodes):
            self.issue("error", "Add an output node: it decides which streams are written to the output file.")
        empty = CompiledGraph(ok=False, filter_complex="", filter_complex_pretty="", inputs=[], outputs=[],
                              issues=self.issues, pads=self.top_pads, links=[])
        if any(i.level == "error" for i in self.issues):
            return empty
        resolved = self._eliminate_relays()
        if resolved is None:
            return empty
        return self._generate(doc, resolved)

    # ------------------------------------------------------------------ flattening

    def _flatten(self, doc: FilterGraphDoc, prefix: str, stack: tuple[str, ...], origin: str | None, context: str,
                 values: Mapping[str, str]) -> None:
        top = origin is None
        level_pads: dict[str, NodePads] = {}
        for node in doc.nodes:
            fid = prefix + node.id
            where = origin or node.id
            node = self._bind(node, values, where, context)
            if top:
                self.top_nodes[node.id] = node
            if isinstance(node, InputNode):
                pads = input_pads(node)
                kind = "input" if top else "relay"
                if top:
                    self._check_io(node, INPUT_BY_NAME, where, context)
                self.nodes[fid] = _Flat(fid, kind, where, not top, NodePads(inputs=pads.outputs, outputs=pads.outputs) if not top else pads, node)
            elif isinstance(node, OutputNode):
                pads = output_pads(node)
                kind = "output" if top else "relay"
                if top:
                    self._check_io(node, OUTPUT_BY_NAME, where, context)
                self.nodes[fid] = _Flat(fid, kind, where, not top, pads if top else NodePads(inputs=pads.inputs, outputs=pads.inputs), node)
            elif isinstance(node, FilterNode):
                spec = self._filter_spec(node, where, context)
                pads = filter_pads(spec, node) if spec else NodePads()
                self.nodes[fid] = _Flat(fid, "filter", where, not top, pads, node, spec)
            else:
                pads = self._expand_graph(node, fid, stack, where, context)
            level_pads[node.id] = pads
        if top:
            self.top_pads = level_pads

        for edge in self._check_edges(doc, level_pads, origin, context):
            src = self._endpoint(prefix, edge.source, edge.source_pad, "out")
            dst = self._endpoint(prefix, edge.target, edge.target_pad, "in")
            if src and dst:
                self.edges.append((src, dst))
                if top:
                    self.top_edges.append(((edge.source, edge.source_pad), (edge.target, edge.target_pad)))

    def _endpoint(self, prefix: str, node_id: str, pad: str, side: str) -> Endpoint | None:
        fid = prefix + node_id
        if fid in self.ports:
            return self.ports[fid][side].get(pad)
        return (fid, pad) if fid in self.nodes else None

    def _bind(self, node: _AnyNode, values: Mapping[str, str], where: str, context: str) -> _AnyNode:
        '''The node with its parameter-bound options replaced by the parameters' values.'''
        if not node.params:
            return node
        options = dict(node.options)
        for key, name in node.params.items():
            if name not in values:
                self.issue("error", f"{context}Option '{key}' uses parameter '{name}', which doesn't exist.", where)
                continue
            options.pop(key, None)
            if values[name] != "":
                options[key] = values[name]
        return node.model_copy(update={"options": options})

    def _expand_graph(self, node: GraphNode, fid: str, stack: tuple[str, ...], where: str, context: str) -> NodePads:
        ref = self.refs.get(node.graph_id)
        if ref is None:
            self.issue("error", f"{context}Saved graph {node.graph_id} was not found (deleted?).", where)
            return NodePads()
        if node.graph_id in stack:
            self.issue("error", f"{context}'{ref.name}' uses itself.", where)
            return NodePads()
        if len(stack) >= MAX_DEPTH:
            self.issue("error", f"{context}Saved graphs are nested more than {MAX_DEPTH} levels deep.", where)
            return NodePads()
        names = {p.name for p in ref.doc.params}
        for key in sorted({*node.options, *node.params} - names):
            self.issue("error", f"{context}'{ref.name}' has no parameter '{key}'.", where)
        self._flatten(ref.doc, prefix=f"{fid}/", stack=(*stack, node.graph_id), origin=where, context=f"{context}In '{ref.name}': ",
                      values=ref.doc.param_values(node.options))
        ports: dict[str, dict[str, Endpoint]] = {"in": {}, "out": {}}
        for inner in ref.doc.nodes:
            if isinstance(inner, InputNode):
                for key in ("v", "a"):
                    ports["in"][f"{inner.name}:{key}"] = (f"{fid}/{inner.id}", key)
            elif isinstance(inner, OutputNode):
                for p in inner.pads:
                    ports["out"][f"{inner.name}:{p.name}"] = (f"{fid}/{inner.id}", p.name)
        self.ports[fid] = ports
        return graph_interface(ref.doc)

    def _filter_spec(self, node: FilterNode, where: str, context: str) -> FilterSpec | None:
        try:
            spec = self.catalog.spec(node.filter)
        except UnknownFilterError:
            self.issue("error", f"{context}Unknown filter '{node.filter}': this ffmpeg build doesn't have it.", where)
            return None
        if spec.blocked:
            self.issue("error", f"{context}The {node.filter} filter isn't allowed here: {spec.blocked_reason}.", where)
        seen: dict[str, str] = {}
        for i, value in enumerate(node.args):
            if i >= len(spec.positional):
                self.issue("error", f"{context}{node.filter} takes at most {len(spec.positional)} positional values.", where)
                break
            seen[spec.positional[i]] = f"positional value #{i + 1}"
        if node.args and any(o.blocked for o in spec.options):
            self.issue("error", f"{context}Use named options for {node.filter} (it has file options that aren't allowed).", where)
        for key, value in node.options.items():
            opt = spec.option(key)
            if opt is None:
                self.issue("error", f"{context}{node.filter} has no option '{key}'.", where)
                continue
            if opt.blocked:
                self.issue("error", f"{context}Option {node.filter}:{key} reads or writes server files and isn't allowed.", where)
            if opt.name in seen:
                self.issue("error", f"{context}{node.filter}: '{key}' is set twice (also as {seen[opt.name]}).", where)
            seen[opt.name] = key
        for key in node.params:
            if key not in node.options and spec.option(key) is None:
                self.issue("error", f"{context}{node.filter} has no option '{key}'.", where)
        for value in [*node.args, *node.options.values()]:
            if _CONTROL.search(value):
                self.issue("error", f"{context}{node.filter}: option values can't contain line breaks or control characters.", where)
                break
        return spec

    def _check_io(self, node: InputNode | OutputNode, specs: Mapping[str, typing.Any], where: str, context: str) -> None:
        for problem in validate_io_options(node.options, specs):
            self.issue("error", context + problem, where)
        for key in node.params:
            if key not in node.options and key not in specs:
                self.issue("error", f"{context}-{key} is not supported here", where)

    def _check_edges(self, doc: FilterGraphDoc, pads: Mapping[str, NodePads], origin: str | None, context: str) -> list:
        '''Report wiring problems on one level of the document and return its usable edges.'''
        top = origin is None
        valid = []
        incoming: dict[Endpoint, int] = {}
        outgoing: dict[Endpoint, int] = {}
        for edge in doc.edges:
            src_pads, dst_pads = pads.get(edge.source), pads.get(edge.target)
            src = next((p for p in src_pads.outputs if p.key == edge.source_pad), None) if src_pads else None
            dst = next((p for p in dst_pads.inputs if p.key == edge.target_pad), None) if dst_pads else None
            if src is None or dst is None:
                missing = edge.source if src is None else edge.target
                self.issue("error", f"{context}A link points to a pad that no longer exists.", origin or missing)
                continue
            if src.type != dst.type:
                self.issue("error", f"{context}Can't link {src.type} pad '{src.name}' to {dst.type} pad '{dst.name}'.",
                           origin or edge.target, None if origin else edge.target_pad, "in")
                continue
            key = (edge.target, edge.target_pad)
            incoming[key] = incoming.get(key, 0) + 1
            if incoming[key] == 2:
                self.issue("error", f"{context}Pad '{dst.name}' has more than one incoming link.", origin or edge.target,
                           None if origin else edge.target_pad, "in")
            outgoing[(edge.source, edge.source_pad)] = outgoing.get((edge.source, edge.source_pad), 0) + 1
            valid.append(edge)

        for node in doc.nodes:
            node_pads = pads.get(node.id, NodePads())
            where = origin or node.id
            if isinstance(node, (FilterNode, GraphNode)):
                label = node.filter if isinstance(node, FilterNode) else "graph"
                for p in node_pads.inputs:
                    if (node.id, p.key) not in incoming:
                        self.issue("error", f"{context}{label}: input pad #{p.key} '{p.name}' is not connected.",
                                   where, None if origin else p.key, "in")
            if isinstance(node, FilterNode) and top:
                for p in node_pads.outputs:
                    if (node.id, p.key) not in outgoing:
                        self.issue("error", f"{node.filter}: output pad #{p.key} '{p.name}' is not connected "
                                   "(link it, or end it with nullsink/anullsink).", node.id, p.key, "out")
            if isinstance(node, InputNode) and top and not any((node.id, k) in outgoing for k in ("v", "a")):
                self.issue("warning", f"Input '{node.name}' isn't used, so it won't be read.", node.id)
            if isinstance(node, OutputNode) and top and not any((node.id, p.name) in incoming for p in node.pads):
                self.issue("error", f"Output '{node.name}' has nothing connected.", node.id)
        return valid

    # ------------------------------------------------------------------ relays (inlined graphs' inputs/outputs)

    def _eliminate_relays(self) -> list[tuple[Endpoint, Endpoint]] | None:
        feeds: dict[Endpoint, Endpoint] = {dst: src for src, dst in self.edges if self.nodes[dst[0]].kind == "relay"}

        def resolve(src: Endpoint) -> Endpoint | None:
            seen = set()
            while self.nodes[src[0]].kind == "relay":
                if src in seen or src not in feeds:
                    return None
                seen.add(src)
                src = feeds[src]
            return src

        out = []
        for src, dst in self.edges:
            if self.nodes[dst[0]].kind == "relay":
                continue
            real = resolve(src)
            if real is None:
                self.issue("error", "An input of a saved graph is not connected.", self.nodes[dst[0]].origin)
                return None
            out.append((real, dst))
        self._resolve = resolve
        return out

    # ------------------------------------------------------------------ code generation

    def _generate(self, doc: FilterGraphDoc, edges: list[tuple[Endpoint, Endpoint]]) -> CompiledGraph:
        consumers: dict[Endpoint, list[Endpoint]] = {}
        source_of: dict[Endpoint, Endpoint] = {}
        for src, dst in edges:
            consumers.setdefault(src, []).append(dst)
            source_of[dst] = src

        inputs: list[CompiledInput] = []
        index: dict[str, int] = {}
        for node in doc.nodes:
            if isinstance(node, InputNode) and any((node.id, k) in consumers for k in ("v", "a")):
                index[node.id] = len(inputs)
                args, flags = io_args(node.options, INPUT_BY_NAME)
                inputs.append(CompiledInput(node=node.id, name=node.name, index=len(inputs), args=args, flags=flags,
                                            sample_path=node.sample_path))

        filters = [n for n in self.nodes.values() if n.kind == "filter"]
        order = self._toposort(filters, source_of)
        if order is None:
            return CompiledGraph(ok=False, filter_complex="", filter_complex_pretty="", inputs=[], outputs=[],
                                 issues=self.issues, pads=self.top_pads, links=[])

        # Labels: one per filter output pad; fan-out goes through a split.
        names: dict[str, int] = {}
        base: dict[str, str] = {}
        for f in order:
            assert isinstance(f.node, FilterNode)
            stem = re.sub(r"\W", "", f.node.filter) or "f"
            names[stem] = names.get(stem, 0) + 1
            base[f.id] = f"{stem}{names[stem]}"
        pad_label: dict[Endpoint, str] = {}
        edge_label: dict[tuple[Endpoint, Endpoint], str] = {}
        extra_chains: dict[str, list[str]] = {}
        for f in order:
            for pad in f.pads.outputs:
                ep = (f.id, pad.key)
                suffix = re.sub(r"\W", "", pad.name) or pad.key
                label = base[f.id] if len(f.pads.outputs) == 1 else f"{base[f.id]}_{suffix}"
                pad_label[ep] = label
                cons = consumers.get(ep, [])
                if not cons:
                    sink = "anullsink" if pad.type == "audio" else "nullsink"
                    extra_chains.setdefault(f.id, []).append(f"[{label}]{sink}")
                elif len(cons) == 1:
                    edge_label[(ep, cons[0])] = label
                else:
                    split = "asplit" if pad.type == "audio" else "split"
                    split_outs = [f"{label}_{i}" for i in range(len(cons))]
                    extra_chains.setdefault(f.id, []).append(f"[{label}]{split}=outputs={len(cons)}" + "".join(f"[{o}]" for o in split_outs))
                    for c, o in zip(cons, split_outs):
                        edge_label[(ep, c)] = o
                    self.issue("info", f"'{pad.name}' feeds {len(cons)} links, so a {split} was added.", f.origin, None if f.inner else pad.key, "out")
        for node_id, i in index.items():
            for key in ("v", "a"):
                for c in consumers.get((node_id, key), []):
                    edge_label[((node_id, key), c)] = f"{i}:{key}"

        # Chains: a single-input filter fed by a single-output, single-consumer filter continues its chain.
        def predecessor(f: _Flat) -> _Flat | None:
            if len(f.pads.inputs) != 1:
                return None
            src = source_of.get((f.id, f.pads.inputs[0].key))
            if src is None or self.nodes[src[0]].kind != "filter":
                return None
            prev = self.nodes[src[0]]
            if len(prev.pads.outputs) != 1 or len(consumers.get(src, [])) != 1:
                return None
            return prev

        chain_of: dict[str, list[_Flat]] = {}
        chains: list[list[_Flat]] = []
        chained_links: set[tuple[Endpoint, Endpoint]] = set()
        for f in order:
            prev = predecessor(f)
            if prev is not None:
                chain = chain_of[prev.id]
                chained_links.add(((prev.id, prev.pads.outputs[0].key), (f.id, f.pads.inputs[0].key)))
            else:
                chain = []
                chains.append(chain)
            chain.append(f)
            chain_of[f.id] = chain

        texts: list[str] = []
        for chain in chains:
            head, tail = chain[0], chain[-1]
            ins = "".join(f"[{edge_label[(source_of[(head.id, p.key)], (head.id, p.key))]}]" for p in head.pads.inputs)
            body = ",".join(self._filter_text(f) for f in chain)
            outs = "".join(f"[{pad_label[(tail.id, p.key)]}]" for p in tail.pads.outputs)
            texts.append(ins + body + outs)
            for f in chain:
                texts.extend(extra_chains.get(f.id, []))

        outputs: list[CompiledOutput] = []
        for node in doc.nodes:
            if not isinstance(node, OutputNode):
                continue
            maps = []
            for p in node.pads:
                mapped = source_of.get((node.id, p.name))
                if mapped is None:
                    continue
                label = edge_label[(mapped, (node.id, p.name))]
                maps.append(f"{label}?" if self.nodes[mapped[0]].kind == "input" else f"[{label}]")
            args, flags = io_args(node.options, OUTPUT_BY_NAME)
            outputs.append(CompiledOutput(node=node.id, name=node.name, maps=maps, args=args, flags=flags, filename=node.filename))

        links = []
        for (s, sp), (t, tp) in self.top_edges:
            real = self._resolve(self._endpoint("", s, sp, "out") or (s, sp))
            dst_ep = self._endpoint("", t, tp, "in")
            label = ""
            if real is not None:
                if dst_ep is not None and (real, dst_ep) in edge_label:
                    label = edge_label[(real, dst_ep)]
                elif real in pad_label:
                    label = pad_label[real]
                elif real[0] in index:
                    label = f"{index[real[0]]}:{real[1]}"
            links.append(LinkView(source=s, source_pad=sp, target=t, target_pad=tp, label=label,
                                  chained=real is not None and dst_ep is not None and (real, dst_ep) in chained_links))

        self._warn_endless(doc)
        return CompiledGraph(
            ok=True, filter_complex=";".join(texts), filter_complex_pretty=";\n".join(texts),
            inputs=inputs, outputs=outputs, issues=self.issues, pads=self.top_pads, links=links,
        )

    def _filter_text(self, f: _Flat) -> str:
        assert isinstance(f.node, FilterNode)
        return format_filter(f.node.filter, list(f.node.args), list(f.node.options.items()))

    def _toposort(self, filters: list[_Flat], source_of: Mapping[Endpoint, Endpoint]) -> list[_Flat] | None:
        deps: dict[str, set[str]] = {}
        for f in filters:
            deps[f.id] = {
                src[0] for p in f.pads.inputs
                if (src := source_of.get((f.id, p.key))) is not None and self.nodes[src[0]].kind == "filter"
            }
        order: list[_Flat] = []
        done: set[str] = set()
        pending = list(filters)
        while pending:
            ready = [f for f in pending if deps[f.id] <= done]
            if not ready:
                for origin in sorted({f.origin for f in pending}):
                    self.issue("error", "This node is part of a loop: a filter can't (indirectly) feed itself.", origin)
                return None
            for f in ready:
                order.append(f)
                done.add(f.id)
            pending = [f for f in pending if f.id not in done]
        return order

    def _warn_endless(self, doc: FilterGraphDoc) -> None:
        outputs_limited = all(any(k in n.options for k in ("t", "to", "frames:v", "fs", "shortest"))
                              for n in doc.nodes if isinstance(n, OutputNode))
        for n in doc.nodes:
            if not isinstance(n, InputNode):
                continue
            loops = n.options.get("stream_loop") == "-1" or n.options.get("loop", "0") not in ("0", "")
            if loops and not outputs_limited and "t" not in n.options and "to" not in n.options:
                self.issue("warning", f"Input '{n.name}' loops with no duration set (-t), so the run may never end.", n.id)
