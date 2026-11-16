from __future__ import annotations

import asyncio
import dataclasses
import datetime
import os
import shlex
import typing
import uuid
from pathlib import Path

from ...contracts import JobAccepted, MediaJobPage
from ...contracts.studio import (
    CompileView,
    ExampleList,
    ExampleView,
    FilterCatalogView,
    GraphList,
    GraphSaveRequest,
    GraphSummary,
    ImportResult,
    IoOptionsView,
    MediaEntry,
    MediaListing,
    SavedGraphView,
    StudioRunAccepted,
    StudioRunItem,
    StudioRunRequest,
)
from ...index_db import (
    FilterGraphRecord,
    GraphNameTakenError,
    MediaJobCollection,
    MediaJobRecord,
)
from ...jobs import JobManager, JobStatus, new_job_id
from ...video.ffmpeg.filtergraph import (
    INPUT_OPTIONS,
    OUTPUT_OPTIONS,
    CompiledGraph,
    FilterCatalog,
    FilterGraphDoc,
    FilterNode,
    FilterSpec,
    GraphRef,
    compile_graph,
    graph_interface,
    import_command,
    referenced_graph_ids,
)
from ..errors import (
    GraphConflictError,
    GraphNotFoundError,
    InvalidJobRequestError,
    MediaFileNotFoundError,
    PathOutsideRootError,
)
from ..media_jobs import STUDIO_RENDER, MediaJobService
from ..paths import resolve_allowed_source, resolve_under_root
from .examples import EXAMPLES

MAX_REFS = 64
MAX_LISTED = 5000
OUTPUT_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ts", ".gif", ".apng", ".webp", ".png", ".jpg", ".jpeg",
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus",
}
MEDIA_KINDS: dict[str, typing.Literal["video", "audio", "image"]] = {
    **dict.fromkeys((".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ts", ".mts", ".m2ts", ".wmv", ".flv", ".3gp", ".mpg", ".mpeg"), "video"),
    **dict.fromkeys((".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"), "audio"),
    **dict.fromkeys((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".apng"), "image"),
}
_HEAVY_PARAMS = ("graph", "compiled", "input_paths")


class GraphStore(typing.Protocol):
    async def list_all(self) -> list[FilterGraphRecord]: ...
    async def get(self, graph_id: str) -> FilterGraphRecord | None: ...
    async def get_many(self, graph_ids: typing.Iterable[str]) -> dict[str, FilterGraphRecord]: ...
    async def find_by_name(self, name_key: str) -> FilterGraphRecord | None: ...
    async def insert(self, record: FilterGraphRecord) -> None: ...
    async def replace(self, record: FilterGraphRecord, expected_revision: int) -> bool: ...
    async def delete(self, graph_id: str) -> bool: ...
    async def used_by(self, graph_id: str) -> list[FilterGraphRecord]: ...


def _summary(record: FilterGraphRecord, doc: FilterGraphDoc) -> dict[str, typing.Any]:
    return {
        "id": record.id, "name": record.name, "description": record.description, "tags": record.tags,
        "created_at": record.created_at, "updated_at": record.updated_at, "revision": record.revision,
        "interface": graph_interface(doc),
        "params": doc.params,
        "filters": list(dict.fromkeys(n.filter for n in doc.nodes if isinstance(n, FilterNode))),
        "uses": sorted(referenced_graph_ids(doc)),
    }


@dataclasses.dataclass(frozen=True)
class StudioService:
    '''Filter catalog, saved-graph library, compilation and render jobs for the studio.'''

    root_path: Path
    source_roots: tuple[Path, ...]
    catalog: FilterCatalog
    store: GraphStore
    jobs: JobManager
    records: MediaJobCollection
    media_jobs: MediaJobService
    max_attempts: int = 2
    _examples: dict[str, list[ExampleView]] = dataclasses.field(default_factory=dict, compare=False, repr=False)

    # ------------------------------------------------------------------ catalog

    async def filters(self) -> FilterCatalogView:
        filters = await asyncio.to_thread(self.catalog.filters)
        return FilterCatalogView(ffmpeg_version=await asyncio.to_thread(self.catalog.version), filters=filters)

    async def filter_spec(self, name: str) -> FilterSpec:
        return await asyncio.to_thread(self.catalog.spec, name)

    @staticmethod
    def io_options() -> IoOptionsView:
        return IoOptionsView(inputs=INPUT_OPTIONS, outputs=OUTPUT_OPTIONS)

    async def examples(self) -> ExampleList:
        if "all" not in self._examples:
            self._examples["all"] = await asyncio.to_thread(self._build_examples)
        return ExampleList(items=self._examples["all"])

    def _build_examples(self) -> list[ExampleView]:
        out = []
        for ex in EXAMPLES:
            doc, issues = import_command(ex.command, self.catalog)
            if any(i.level == "error" for i in issues) or not compile_graph(doc, self.catalog).ok:
                continue  # e.g. a filter missing from this ffmpeg build
            out.append(ExampleView(id=ex.id, title=ex.title, category=ex.category, summary=ex.summary,
                                   explanation=ex.explanation, command=ex.command, graph=doc))
        return out

    # ------------------------------------------------------------------ compile / import

    async def compile(self, doc: FilterGraphDoc, values: typing.Mapping[str, str] | None = None) -> CompileView:
        compiled = await self._compile(doc, values)
        return CompileView(**compiled.model_dump(), command=compiled.preview())

    async def import_text(self, text: str) -> ImportResult:
        doc, issues = await asyncio.to_thread(import_command, text, self.catalog)
        return ImportResult(graph=doc, issues=issues)

    async def _compile(self, doc: FilterGraphDoc, values: typing.Mapping[str, str] | None = None) -> CompiledGraph:
        refs = await self._load_refs(doc)
        return await asyncio.to_thread(compile_graph, doc, self.catalog, refs, values)

    async def _load_refs(self, doc: FilterGraphDoc, override: tuple[str, FilterGraphDoc] | None = None) -> dict[str, GraphRef]:
        '''All saved graphs reachable from `doc` (optionally with one graph replaced by an unsaved version).'''
        refs: dict[str, GraphRef] = {}
        todo = set(referenced_graph_ids(doc))
        while todo and len(refs) < MAX_REFS:
            found = await self.store.get_many(todo)
            todo = set()
            for gid, rec in found.items():
                sub = FilterGraphDoc.model_validate(rec.graph)
                if override and gid == override[0]:
                    sub = override[1]
                refs[gid] = GraphRef(name=rec.name, doc=sub)
                todo |= referenced_graph_ids(sub) - refs.keys()
        return refs

    # ------------------------------------------------------------------ library

    async def list_graphs(self) -> GraphList:
        items = []
        for rec in await self.store.list_all():
            items.append(GraphSummary(**_summary(rec, FilterGraphDoc.model_validate(rec.graph))))
        return GraphList(items=items)

    async def get_graph(self, graph_id: str) -> SavedGraphView:
        rec = await self._record(graph_id)
        doc = FilterGraphDoc.model_validate(rec.graph)
        return SavedGraphView(**_summary(rec, doc), graph=doc)

    async def create_graph(self, req: GraphSaveRequest) -> SavedGraphView:
        graph_id = uuid.uuid4().hex[:16]
        await self._check_save(graph_id, req)
        now = datetime.datetime.now(datetime.UTC)
        rec = self._to_record(graph_id, req, revision=1, created_at=now)
        try:
            await self.store.insert(rec)
        except GraphNameTakenError as e:
            raise GraphConflictError(f"A saved graph is already called {req.name!r}.") from e
        return await self.get_graph(graph_id)

    async def update_graph(self, graph_id: str, req: GraphSaveRequest) -> SavedGraphView:
        current = await self._record(graph_id)
        if req.revision is not None and req.revision != current.revision:
            raise GraphConflictError(f"{current.name!r} was changed elsewhere (revision {current.revision}); reload it first.")
        await self._check_save(graph_id, req)
        rec = self._to_record(graph_id, req, revision=current.revision + 1, created_at=current.created_at)
        try:
            stored = await self.store.replace(rec, current.revision)
        except GraphNameTakenError as e:
            raise GraphConflictError(f"A saved graph is already called {req.name!r}.") from e
        if not stored:
            raise GraphConflictError(f"{current.name!r} was changed elsewhere; reload it first.")
        return await self.get_graph(graph_id)

    async def delete_graph(self, graph_id: str) -> None:
        rec = await self._record(graph_id)
        users = await self.store.used_by(graph_id)
        if users:
            names = ", ".join(repr(u.name) for u in users[:5])
            raise GraphConflictError(f"{rec.name!r} is used by {names}; remove it from there first.")
        await self.store.delete(graph_id)

    async def _record(self, graph_id: str) -> FilterGraphRecord:
        rec = await self.store.get(graph_id)
        if rec is None:
            raise GraphNotFoundError(f"Saved graph not found: {graph_id}")
        return rec

    async def _check_save(self, graph_id: str, req: GraphSaveRequest) -> None:
        other = await self.store.find_by_name(req.name.casefold())
        if other is not None and other.id != graph_id:
            raise GraphConflictError(f"A saved graph is already called {req.name!r}.")
        uses = referenced_graph_ids(req.graph)
        if graph_id in uses:
            raise InvalidJobRequestError("A graph can't contain itself.")
        refs = await self._load_refs(req.graph, override=(graph_id, req.graph))
        missing = uses - refs.keys()
        if missing:
            raise InvalidJobRequestError(f"Saved graph(s) not found: {', '.join(sorted(missing))}")
        # Saving must not close a loop: no embedded graph may (indirectly) embed this one.
        if graph_id in refs:
            raise InvalidJobRequestError("This would make the graph contain itself through another saved graph.")

    @staticmethod
    def _to_record(graph_id: str, req: GraphSaveRequest, revision: int, created_at: datetime.datetime) -> FilterGraphRecord:
        return FilterGraphRecord(
            id=graph_id, name=req.name, name_key=req.name.casefold(), description=req.description,
            tags=list(dict.fromkeys(req.tags)), graph=req.graph.model_dump(mode="json"),
            uses=sorted(referenced_graph_ids(req.graph)), revision=revision,
            created_at=created_at, updated_at=datetime.datetime.now(datetime.UTC),
        )

    # ------------------------------------------------------------------ running

    async def run(self, req: StudioRunRequest) -> StudioRunAccepted:
        compiled = await self._compile(req.graph, req.params)
        if not compiled.ok:
            raise InvalidJobRequestError("Fix the graph first: " + "; ".join(i.message for i in compiled.errors[:3]))
        plans = [self._plan(compiled, item, req.overwrite) for item in req.items]
        seen: set[Path] = set()
        for _, outputs in plans:
            for path in outputs.values():
                if path in seen:
                    raise InvalidJobRequestError(f"Two runs would write the same file: {path.relative_to(self.root_path)}")
                seen.add(path)

        batch_id = uuid.uuid4().hex[:12]
        graph_json = req.graph.model_dump(mode="json")
        compiled_json = compiled.model_dump(mode="json", include={"filter_complex", "inputs", "outputs"})
        accepted = []
        for i, (item, (inputs, outputs)) in enumerate(zip(req.items, plans)):
            job_id = new_job_id()
            out_rel = {n: str(p.relative_to(self.root_path)) for n, p in outputs.items()}
            command = compiled.ffmpeg_command({n: str(p) for n, p in inputs.items()}, {n: str(p) for n, p in outputs.items()},
                                       overwrite=req.overwrite)
            params: dict[str, typing.Any] = {
                "graph_id": req.graph_id, "graph_name": req.graph_name, "batch_id": batch_id,
                "item": i + 1, "items": len(req.items),
                "inputs": dict(item.inputs), "outputs": out_rel, "overwrite": req.overwrite,
                "param_values": req.graph.param_values(req.params),
                "filter_complex": compiled.filter_complex,
                "command": " ".join(shlex.quote(a) for a in command.build_command()),
                "input_paths": {n: str(p) for n, p in inputs.items()},
                "compiled": compiled_json, "graph": graph_json,
            }
            await self.records.insert(MediaJobRecord(
                job_id=job_id,
                job_type=STUDIO_RENDER,
                target_path=str(next(iter(outputs.values())).parent.relative_to(self.root_path)),
                params=params,
            ))
            job = await self.jobs.submit(STUDIO_RENDER, job_id=job_id, max_attempts=self.max_attempts)
            accepted.append(JobAccepted(job_id=job.id, status=job.status.value, status_url=f"/v1/jobs/{job.id}"))
        return StudioRunAccepted(jobs=accepted)

    def _plan(self, compiled: CompiledGraph, item: StudioRunItem, overwrite: bool) -> tuple[dict[str, Path], dict[str, Path]]:
        inputs: dict[str, Path] = {}
        for inp in compiled.inputs:
            raw = item.inputs.get(inp.node)
            if not raw:
                raise InvalidJobRequestError(f"Choose a file for input '{inp.name}'.")
            try:
                path = (resolve_allowed_source(raw, (self.root_path, *self.source_roots)) if os.path.isabs(raw)
                        else resolve_under_root(self.root_path, raw))
            except PathOutsideRootError as e:
                raise InvalidJobRequestError(str(e)) from e
            if not path.is_file():
                raise InvalidJobRequestError(f"Input file not found: {raw}")
            inputs[inp.node] = path
        outputs: dict[str, Path] = {}
        for out in compiled.outputs:
            raw = item.outputs.get(out.node)
            if not raw:
                raise InvalidJobRequestError(f"Choose a file name for output '{out.name}'.")
            try:
                path = resolve_under_root(self.root_path, raw)
            except PathOutsideRootError as e:
                raise InvalidJobRequestError(str(e)) from e
            if path.suffix.lower() not in OUTPUT_SUFFIXES:
                raise InvalidJobRequestError(f"{raw}: use one of {', '.join(sorted(OUTPUT_SUFFIXES))}.")
            if "%" in path.name or path.name.startswith("."):
                raise InvalidJobRequestError(f"{raw}: file names can't contain % or start with a dot.")
            if path in inputs.values() or path in outputs.values():
                raise InvalidJobRequestError(f"{raw} is used more than once (inputs and outputs must differ).")
            if path.is_dir():
                raise InvalidJobRequestError(f"{raw} is a folder.")
            if path.exists() and not overwrite:
                raise InvalidJobRequestError(f"{raw} already exists (tick 'overwrite' to replace it).")
            outputs[out.node] = path
        return inputs, outputs

    async def list_jobs(self, *, status: JobStatus | None = None, limit: int = 50, offset: int = 0) -> MediaJobPage:
        page = await self.media_jobs.list(status=status, kind="studio", limit=limit, offset=offset)
        items = [item.model_copy(update={"params": {k: v for k, v in item.params.items() if k not in _HEAVY_PARAMS}})
                 for item in page.items]
        return page.model_copy(update={"items": items})

    async def job_graph(self, job_id: str) -> FilterGraphDoc:
        record = await self.records.get(job_id)
        if record is None or record.job_type != STUDIO_RENDER or "graph" not in record.params:
            raise GraphNotFoundError(f"No studio graph for job {job_id}")
        doc = FilterGraphDoc.model_validate(record.params["graph"])
        # The values the run used become the defaults, so the opened graph reproduces it.
        used = record.params.get("param_values")
        if not isinstance(used, dict):
            return doc
        return doc.model_copy(update={"params": [p.model_copy(update={"default": str(used.get(p.name, p.default))}) for p in doc.params]})

    # ------------------------------------------------------------------ files

    async def media(self, rel: str) -> MediaListing:
        return await asyncio.to_thread(self._media, rel)

    def _media(self, rel: str) -> MediaListing:
        folder = resolve_under_root(self.root_path, rel)
        if not folder.is_dir():
            raise MediaFileNotFoundError(f"Folder not found: {rel}")
        dirs: list[str] = []
        files: list[MediaEntry] = []
        truncated = False
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
        except PermissionError as e:
            raise MediaFileNotFoundError(f"The server can't read {rel}") from e
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if len(dirs) + len(files) >= MAX_LISTED:
                truncated = True
                break
            try:
                if entry.is_dir():
                    dirs.append(entry.name)
                elif entry.is_file() and (kind := MEDIA_KINDS.get(os.path.splitext(entry.name)[1].lower())):
                    path = str((folder / entry.name).relative_to(self.root_path))
                    files.append(MediaEntry(name=entry.name, path=path, kind=kind, size=entry.stat().st_size))
            except OSError:
                continue
        here = str(folder.relative_to(self.root_path))
        parent = None if folder == self.root_path else str(folder.parent.relative_to(self.root_path))
        return MediaListing(path=here, parent=parent, dirs=dirs, files=files, truncated=truncated)
