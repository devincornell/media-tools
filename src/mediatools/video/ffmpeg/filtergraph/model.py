'''The node-graph document the studio edits, and the pads (connection points) of each node.

A document maps onto an ffmpeg command:

* an `input` node is one `-i FILE`; its pads `v` and `a` are the streams `[N:v]` and `[N:a]`;
* a `filter` node is one filter instance (`scale=w=640:h=-2`), with the input and output pads ffmpeg lists for it;
* a `graph` node embeds another saved graph: its pads are that graph's input streams and output pads;
* an `output` node is one output file: each connected pad becomes a `-map`, and its options are output options;
* an edge is a link between two pads, i.e. a `[label]` in the filtergraph.
'''
from __future__ import annotations

import typing
from typing import Annotated

import pydantic

from .catalog import FilterSpec, MediaType

NodeId = Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
PadKey = Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")]
SlotName = Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")]
OptionName = Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z0-9_:-]{1,64}$")]
OptionValue = Annotated[str, pydantic.StringConstraints(max_length=4000)]

MAX_PADS = 64
INPUT_STREAMS: tuple[tuple[str, MediaType], ...] = (("v", "video"), ("a", "audio"))


class _Model(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")


class Position(_Model):
    x: float
    y: float


class _Node(_Model):
    id: NodeId
    position: Position | None = None
    note: Annotated[str, pydantic.Field(max_length=2000)] = ""


class InputNode(_Node):
    '''One input file (`-i`), bound to a real file when the graph is run.'''

    kind: typing.Literal["input"] = "input"
    name: SlotName = "in"
    options: dict[OptionName, OptionValue] = {}
    sample_path: Annotated[str | None, pydantic.Field(max_length=4096)] = None


class FilterNode(_Node):
    '''One filter instance.'''

    kind: typing.Literal["filter"] = "filter"
    filter: Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z0-9_]{1,64}$")]
    args: Annotated[list[OptionValue], pydantic.Field(max_length=64, description="Positional values, before named options.")] = []
    options: dict[OptionName, OptionValue] = {}
    extra_inputs: Annotated[int | None, pydantic.Field(ge=0, le=MAX_PADS)] = None
    extra_outputs: Annotated[int | None, pydantic.Field(ge=0, le=MAX_PADS)] = None


class GraphNode(_Node):
    '''A saved graph used as one node.'''

    kind: typing.Literal["graph"] = "graph"
    graph_id: Annotated[str, pydantic.StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class OutputPadDef(_Model):
    name: SlotName
    type: MediaType


def _default_output_pads() -> list[OutputPadDef]:
    return [OutputPadDef(name="v", type="video"), OutputPadDef(name="a", type="audio")]


class OutputNode(_Node):
    '''One output file. Each connected pad is mapped into it, in order.'''

    kind: typing.Literal["output"] = "output"
    name: SlotName = "out"
    pads: list[OutputPadDef] = pydantic.Field(default_factory=_default_output_pads, max_length=MAX_PADS)
    options: dict[OptionName, OptionValue] = {}
    filename: Annotated[str, pydantic.Field(max_length=255, description="File name template, e.g. `{stem}-small.mp4`.")] = "{stem}-{output}.mp4"


Node = Annotated[InputNode | FilterNode | GraphNode | OutputNode, pydantic.Field(discriminator="kind")]


class Edge(_Model):
    source: NodeId
    source_pad: PadKey
    target: NodeId
    target_pad: PadKey


class FilterGraphDoc(_Model):
    '''A complete, editable filtergraph with its inputs and outputs.'''

    version: typing.Literal[1] = 1
    nodes: Annotated[list[Node], pydantic.Field(max_length=500)] = []
    edges: Annotated[list[Edge], pydantic.Field(max_length=2000)] = []

    @pydantic.model_validator(mode="after")
    def _unique(self) -> FilterGraphDoc:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node ids must be unique.")
        for kind in ("input", "output"):
            names = [n.name for n in self.nodes if n.kind == kind]  # type: ignore[union-attr]
            if len(names) != len(set(names)):
                raise ValueError(f"Each {kind} node needs a unique name.")
        for node in self.nodes:
            if isinstance(node, OutputNode) and len({p.name for p in node.pads}) != len(node.pads):
                raise ValueError(f"Output {node.name!r} has duplicate pad names.")
        return self

    def node(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)


class Pad(pydantic.BaseModel):
    key: str
    name: str
    type: MediaType


class NodePads(pydantic.BaseModel):
    inputs: list[Pad] = []
    outputs: list[Pad] = []


def filter_pads(spec: FilterSpec, node: FilterNode) -> NodePads:
    '''Pads of a filter instance; dynamic filters (split, hstack, concat, ...) depend on its options.'''
    named = dict(node.options)
    for name, value in zip(spec.positional, node.args):
        named.setdefault(name, value)

    def count(option: str | None, default: int) -> int:
        raw = named.get(option) if option else None
        if raw is None and option:
            opt = spec.option(option)
            raw = next((v for k, v in named.items() if opt and k in opt.aliases), None)
        try:
            return max(0, min(MAX_PADS, int(raw))) if raw is not None else default
        except ValueError:
            return default

    def side(rule_side: str) -> list[Pad]:
        rule = spec.input_rule if rule_side == "in" else spec.output_rule
        listed = spec.input_pads if rule_side == "in" else spec.output_pads
        prefix = "in" if rule_side == "in" else "out"
        if rule.kind == "concat":
            n, v, a = count("n", 2), count("v", 1), count("a", 0)
            if rule_side == "in":
                pads = []
                for seg in range(n):
                    pads += [Pad(key="", name=f"s{seg}.v{j}", type="video") for j in range(v)]
                    pads += [Pad(key="", name=f"s{seg}.a{j}", type="audio") for j in range(a)]
            else:
                pads = [Pad(key="", name=f"v{j}", type="video") for j in range(v)]
                pads += [Pad(key="", name=f"a{j}", type="audio") for j in range(a)]
        elif rule.kind == "count":
            pads = [Pad(key="", name=f"{prefix}{i}", type=rule.type) for i in range(count(rule.option, rule.default))]
        else:
            pads = [Pad(key="", name=p.name, type=p.type) for p in listed]
            if rule.kind == "manual":
                extra = node.extra_inputs if rule_side == "in" else node.extra_outputs
                n_extra = rule.default if extra is None else extra
                pads += [Pad(key="", name=f"{prefix}{len(pads) + i}", type=rule.type) for i in range(n_extra)]
        for i, pad in enumerate(pads[:MAX_PADS]):
            pad.key = str(i)
        return pads[:MAX_PADS]

    return NodePads(inputs=side("in"), outputs=side("out"))


def input_pads(node: InputNode) -> NodePads:
    return NodePads(outputs=[Pad(key=k, name=k, type=t) for k, t in INPUT_STREAMS])


def output_pads(node: OutputNode) -> NodePads:
    return NodePads(inputs=[Pad(key=p.name, name=p.name, type=p.type) for p in node.pads])


def graph_interface(doc: FilterGraphDoc) -> NodePads:
    '''The pads a saved graph shows when used as a node: its used input streams and connected output pads.'''
    used_sources = {(e.source, e.source_pad) for e in doc.edges}
    used_targets = {(e.target, e.target_pad) for e in doc.edges}
    pads = NodePads()
    for node in doc.nodes:
        if isinstance(node, InputNode):
            for key, mtype in INPUT_STREAMS:
                if (node.id, key) in used_sources:
                    pads.inputs.append(Pad(key=f"{node.name}:{key}", name=f"{node.name}:{key}", type=mtype))
        elif isinstance(node, OutputNode):
            for p in node.pads:
                if (node.id, p.name) in used_targets:
                    pads.outputs.append(Pad(key=f"{node.name}:{p.name}", name=f"{node.name}:{p.name}", type=p.type))
    return pads
