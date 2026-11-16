from __future__ import annotations

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..video.ffmpeg.filtergraph import (
    CompiledGraph,
    FilterGraphDoc,
    FilterSummary,
    GraphParam,
    IoOptionSpec,
    Issue,
    NodePads,
)
from .jobs import JobAccepted


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
ParamValues = Annotated[
    dict[Annotated[str, StringConstraints(max_length=32)], Annotated[str, StringConstraints(max_length=4000)]],
    Field(max_length=64, description="Parameter name -> value, replacing the parameter's default."),
]


class FilterCatalogView(_Contract):
    ffmpeg_version: Annotated[str, Field(description="First line of `ffmpeg -version`.")]
    filters: Annotated[list[FilterSummary], Field(description="Every filter of the local ffmpeg build.")]


class IoOptionsView(_Contract):
    inputs: Annotated[list[IoOptionSpec], Field(description="Options an input node may set (before `-i`).")]
    outputs: Annotated[list[IoOptionSpec], Field(description="Options an output node may set (before the file name).")]


class GraphSaveRequest(_Contract):
    '''Create or update a saved filtergraph.'''

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=4000)] = ""
    tags: Annotated[list[Tag], Field(max_length=20)] = []
    graph: FilterGraphDoc
    revision: Annotated[int | None, Field(description="Revision being replaced; the save is refused if it changed since.")] = None


class GraphSummary(_Contract):
    id: str
    name: str
    description: str
    tags: list[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    revision: Annotated[int, Field(description="Increases with every save.")]
    interface: Annotated[NodePads, Field(description="Pads the graph shows when used as a node in another graph.")]
    params: Annotated[list[GraphParam], Field(description="Parameters that can be set when running or embedding it.")]
    filters: Annotated[list[str], Field(description="Filters used, in order of appearance.")]
    uses: Annotated[list[str], Field(description="IDs of saved graphs this one embeds.")]


class SavedGraphView(GraphSummary):
    graph: FilterGraphDoc


class GraphList(_Contract):
    items: list[GraphSummary]


class CompileRequest(_Contract):
    graph: FilterGraphDoc
    params: ParamValues = {}


class CompileView(CompiledGraph):
    '''A compiled graph plus the command it produces with placeholder file names.'''

    model_config = ConfigDict(frozen=True)

    command: Annotated[str, Field(description="Example command line (placeholder file names).")]


class ImportRequest(_Contract):
    text: Annotated[str, Field(min_length=1, max_length=20000, description="An ffmpeg command line, or filtergraph text.")]


class ImportResult(_Contract):
    graph: FilterGraphDoc
    issues: list[Issue]


class ExampleView(_Contract):
    id: str
    title: str
    category: str
    summary: Annotated[str, Field(description="One line, for people who don't know ffmpeg.")]
    explanation: Annotated[str, Field(description="How it works, in ffmpeg terms.")]
    command: Annotated[str, Field(description="The equivalent ffmpeg command.")]
    graph: FilterGraphDoc


class ExampleList(_Contract):
    items: list[ExampleView]


PathStr = Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class StudioRunItem(_Contract):
    '''One ffmpeg run: a file for every input node and an output path for every output node.'''

    inputs: Annotated[dict[str, PathStr], Field(description="Input node id -> file, relative to the gallery root or absolute inside an allowed root.")]
    outputs: Annotated[dict[str, PathStr], Field(description="Output node id -> file path relative to the gallery root.")]


class StudioRunRequest(_Contract):
    '''Run a graph once per item; each item becomes one job.'''

    graph: FilterGraphDoc
    graph_id: Annotated[str | None, Field(description="Saved graph the run came from, if any.")] = None
    graph_name: Annotated[str, Field(max_length=120)] = "Untitled graph"
    items: Annotated[list[StudioRunItem], Field(min_length=1, max_length=200)]
    params: ParamValues = {}
    overwrite: Annotated[bool, Field(description="Replace output files that already exist.")] = False


class StudioRunAccepted(_Contract):
    jobs: list[JobAccepted]


class MediaEntry(_Contract):
    name: str
    path: Annotated[str, Field(description="Relative to the gallery root.")]
    kind: Literal["video", "audio", "image"]
    size: int


class MediaListing(_Contract):
    '''Folders and media files in one gallery folder, read live from disk.'''

    path: Annotated[str, Field(description="Listed folder relative to the gallery root (`.` for the root).")]
    parent: Annotated[str | None, Field(description="Parent folder, or null at the root.")]
    dirs: list[str]
    files: list[MediaEntry]
    truncated: Annotated[bool, Field(description="True if there were too many entries to list them all.")]
