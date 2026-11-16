"""Tests for the studio: filtergraph syntax, catalog parsing, compiler, importer, library and HTTP API."""
from __future__ import annotations

import asyncio
import datetime
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from apps.api.dependencies import get_studio
from apps.api.main import create_app
from mediatools.application.media_jobs import STUDIO_RENDER, MediaJobService
from mediatools.application.studio import EXAMPLES, StudioService
from mediatools.index_db import FilterGraphRecord, GraphNameTakenError, MediaJobRecord
from mediatools.jobs import Job, JobStatus
from mediatools.video.ffmpeg.filtergraph import (
    Edge,
    FilterCatalog,
    FilterGraphDoc,
    FilterNode,
    GraphNode,
    GraphParam,
    GraphRef,
    InputNode,
    OutputNode,
    compile_graph,
    import_command,
    parse_filtergraph,
)
from mediatools.video.ffmpeg.filtergraph.catalog import (
    FilterSummary,
    parse_filter_help,
    parse_filter_list,
)
from mediatools.video.ffmpeg.filtergraph.syntax import (
    format_filter,
    get_token,
    parse_args,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "iw/2", "if(gt(t,2),1,0)", "a:b", "it's", "back\\slash", "[x];y,z", " padded ", "%{pts:hms}", "", "x=y",
])
def test_escaping_round_trips(value: str):
    text = format_filter("f", [value], [("k", value)])
    [[parsed]] = parse_filtergraph(f"[in]{text}[out]")
    assert parsed.args == [value] and parsed.options == [("k", value)]
    assert parsed.in_labels == ["in"] and parsed.out_labels == ["out"]


def test_get_token_matches_av_get_token():
    assert get_token("  a\\,b 'c,d' ,rest", 0, ",") == ("a,b c,d", 13)
    assert get_token("x\\  ", 0, ",")[0] == "x "


def test_parse_args_positional_then_named():
    assert parse_args("640:-2:flags=lanczos") == (["640", "-2"], [("flags", "lanczos")])
    with pytest.raises(ValueError):
        parse_args("w=1:2")


def test_parse_filtergraph_chains():
    chains = parse_filtergraph("[0:v]split[a][b];\n [a]scale=w=iw/2:h=-2,hflip[c] ; [b][c]hstack")
    assert [[f.name for f in c] for c in chains] == [["split"], ["scale", "hflip"], ["hstack"]]
    assert chains[1][0].options == [("w", "iw/2"), ("h", "-2")]
    assert chains[1][1].out_labels == ["c"]


# ---------------------------------------------------------------------------
# Catalog parsing (fixture text, no ffmpeg needed)
# ---------------------------------------------------------------------------

LIST = """Filters:
  T.. = Timeline support
 TS overlay           VV->V      Overlay a video source on top of the input.
 .. split             V->N       Pass on the input to N video outputs.
 .. movie             |->N       Read from a movie source.
"""

HELP = """Filter fade
  Fade in/out input video.
    Inputs:
       #0: default (video)
    Outputs:
       #0: default (video)
fade AVOptions:
   type              <int>        ..FV....... set the fade direction (from 0 to 1) (default in)
     in              0            ..FV....... fade-in
     out             1            ..FV....... fade-out
   t                 <int>        ..FV....... set the fade direction (from 0 to 1) (default in)
     in              0            ..FV....... fade-in
     out             1            ..FV....... fade-out
   color             <color>      ..FV.....T. set color (default "black")
   textfile          <string>     ..FV....... set text file

This filter has support for timeline through the 'enable' option.
"""


def test_parse_filter_list_and_help():
    summaries = {f.name: f for f in parse_filter_list(LIST)}
    assert summaries["overlay"].timeline and summaries["overlay"].inputs == "VV"
    assert summaries["movie"].blocked and not summaries["split"].blocked
    spec = parse_filter_help(HELP, FilterSummary(name="fade", description="", inputs="V", outputs="V",
                                                 timeline=False, slice_threading=False, category="Video"))
    by_name = {o.name: o for o in spec.options}
    assert by_name["type"].aliases == ["t"] and [c.name for c in by_name["type"].constants] == ["in", "out"]
    assert (by_name["type"].min, by_name["type"].max, by_name["type"].default) == ("0", "1", "in")
    assert by_name["color"].default == "black" and by_name["color"].runtime
    assert by_name["textfile"].blocked and "enable" in by_name and spec.timeline
    assert spec.positional == ["type", "color", "textfile"]
    assert spec.doc_url.endswith("#fade")


# ---------------------------------------------------------------------------
# Compiler and importer (real ffmpeg catalog)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def catalog() -> FilterCatalog:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")
    return FilterCatalog()


def _doc(nodes: list, edges: list[tuple[str, str, str, str]]) -> FilterGraphDoc:
    return FilterGraphDoc(nodes=nodes, edges=[Edge(source=a, source_pad=b, target=c, target_pad=d) for a, b, c, d in edges])


def _io(*extra) -> list:
    return [InputNode(id="in", name="in"), *extra, OutputNode(id="out", name="out")]


def test_compile_chains_and_maps(catalog: FilterCatalog):
    doc = _doc(_io(FilterNode(id="s", filter="scale", options={"w": "iw/2", "h": "-2"}), FilterNode(id="f", filter="hflip")),
               [("in", "v", "s", "0"), ("s", "0", "f", "0"), ("f", "0", "out", "v"), ("in", "a", "out", "a")])
    c = compile_graph(doc, catalog)
    assert c.ok, c.issues
    assert c.filter_complex == "[0:v]scale=w=iw/2:h=-2,hflip[hflip1]"
    assert c.outputs[0].maps == ["[hflip1]", "0:a?"]
    assert {(link.source, link.chained) for link in c.links} == {("in", False), ("s", True), ("f", False)}


def test_compile_adds_split_for_fan_out(catalog: FilterCatalog):
    doc = _doc([*_io(FilterNode(id="s", filter="scale", options={"w": "320", "h": "-2"})), OutputNode(id="o2", name="small")],
               [("in", "v", "s", "0"), ("s", "0", "out", "v"), ("s", "0", "o2", "v")])
    c = compile_graph(doc, catalog)
    assert c.ok
    assert c.filter_complex == "[0:v]scale=w=320:h=-2[scale1];[scale1]split=outputs=2[scale1_0][scale1_1]"
    assert [o.maps for o in c.outputs] == [["[scale1_0]"], ["[scale1_1]"]]
    assert any(i.level == "info" and "split" in i.message for i in c.issues)


@pytest.mark.parametrize("node, edges, message", [
    (FilterNode(id="o", filter="overlay"), [("in", "v", "o", "0"), ("o", "0", "out", "v")], "input pad #1 'overlay' is not connected"),
    (FilterNode(id="s", filter="split"), [("in", "v", "s", "0"), ("s", "0", "out", "v")], "output pad #1"),
    (FilterNode(id="v", filter="volume"), [("in", "v", "v", "0")], "Can't link video"),
    (FilterNode(id="x", filter="nosuchfilter"), [], "Unknown filter"),
    (FilterNode(id="m", filter="movie", options={"filename": "/etc/passwd"}), [], "isn't allowed"),
    (FilterNode(id="d", filter="drawtext", options={"textfile": "/etc/passwd"}), [("in", "v", "d", "0"), ("d", "0", "out", "v")], "server files"),
    (FilterNode(id="d", filter="drawtext", args=["/etc/passwd"]), [("in", "v", "d", "0"), ("d", "0", "out", "v")], "named options"),
    (FilterNode(id="s", filter="scale", options={"w": "1", "width": "2"}), [("in", "v", "s", "0"), ("s", "0", "out", "v")], "set twice"),
    (FilterNode(id="s", filter="scale", options={"w": "1\n2"}), [("in", "v", "s", "0"), ("s", "0", "out", "v")], "line breaks"),
])
def test_compile_reports_problems(catalog: FilterCatalog, node, edges, message: str):
    c = compile_graph(_doc(_io(node), edges), catalog)
    assert not c.ok
    assert any(message in i.message for i in c.errors), [i.message for i in c.issues]


def test_compile_rejects_unsafe_io_options(catalog: FilterCatalog):
    doc = _doc([InputNode(id="in", options={"f": "lavfi"}), OutputNode(id="out", options={"passlogfile": "/tmp/x"})],
               [("in", "v", "out", "v")])
    messages = [i.message for i in compile_graph(doc, catalog).errors]
    assert any("-f is not supported" in m for m in messages) and any("-passlogfile" in m for m in messages)


def test_compile_detects_loops(catalog: FilterCatalog):
    doc = _doc(_io(FilterNode(id="o", filter="overlay"), FilterNode(id="s", filter="split")),
               [("in", "v", "o", "0"), ("s", "0", "o", "1"), ("o", "0", "s", "0"), ("s", "1", "out", "v")])
    assert any("loop" in i.message for i in compile_graph(doc, catalog).errors)


def test_graph_nodes_are_inlined(catalog: FilterCatalog):
    blur = _doc([InputNode(id="i", name="src"), FilterNode(id="b", filter="gblur", options={"sigma": "5"}),
                 OutputNode(id="o", name="res", pads=[{"name": "v", "type": "video"}])],
                [("i", "v", "b", "0"), ("b", "0", "o", "v")])
    refs = {"g1": GraphRef(name="Blur", doc=blur)}
    doc = _doc(_io(GraphNode(id="g", graph_id="g1"), FilterNode(id="h", filter="hflip")),
               [("in", "v", "g", "src:v"), ("g", "res:v", "h", "0"), ("h", "0", "out", "v")])
    c = compile_graph(doc, catalog, refs)
    assert c.ok, c.issues
    assert c.filter_complex == "[0:v]gblur=sigma=5,hflip[hflip1]"
    assert [p.key for p in c.pads["g"].inputs] == ["src:v"] and [p.key for p in c.pads["g"].outputs] == ["res:v"]

    loop = {"g1": GraphRef(name="Loop", doc=_doc([GraphNode(id="x", graph_id="g1")], []))}
    assert any("uses itself" in i.message for i in compile_graph(_doc(_io(GraphNode(id="g", graph_id="g1")), []), catalog, loop).errors)


def _param_doc(**params) -> FilterGraphDoc:
    doc = _doc(
        [InputNode(id="in", params={"ss": "start"}),
         FilterNode(id="s", filter="scale", options={"h": "-2"}, params={"w": "width"}),
         OutputNode(id="out", params={"crf": "quality"})],
        [("in", "v", "s", "0"), ("s", "0", "out", "v")])
    return doc.model_copy(update={"params": [GraphParam(name="width", default="640"), GraphParam(name="start"),
                                             GraphParam(name="quality", default="23"), *params.values()]})


def test_parameters_take_defaults_and_values(catalog: FilterCatalog):
    c = compile_graph(_param_doc(), catalog)
    assert c.ok, c.issues
    assert c.filter_complex == "[0:v]scale=h=-2:w=640[scale1]"
    assert c.inputs[0].args == [] and c.outputs[0].args == [("crf", "23")]

    c = compile_graph(_param_doc(), catalog, values={"width": "320", "start": "5"})
    assert c.ok and c.filter_complex == "[0:v]scale=h=-2:w=320[scale1]" and c.inputs[0].args == [("ss", "5")]


@pytest.mark.parametrize("values, message", [
    ({"nope": "1"}, "no parameter 'nope'"),
    ({"quality": "-f"}, "-crf: invalid value"),
    ({"width": "1\n2"}, "line breaks"),
])
def test_parameter_values_are_checked(catalog: FilterCatalog, values: dict, message: str):
    c = compile_graph(_param_doc(), catalog, values=values)
    assert any(message in i.message for i in c.errors), [i.message for i in c.issues]


def test_parameter_bindings_are_checked(catalog: FilterCatalog):
    doc = _param_doc(extra=GraphParam(name="unused"))
    doc.nodes[1].params["bogus"] = "width"
    doc.nodes[2].params["t"] = "missing"
    c = compile_graph(doc, catalog)
    messages = [i.message for i in c.issues]
    assert "scale has no option 'bogus'." in messages
    assert "Option 't' uses parameter 'missing', which doesn't exist." in messages
    assert "Parameter 'unused' isn't used by any option." in messages


def test_graph_nodes_pass_parameters(catalog: FilterCatalog):
    blur = _doc([InputNode(id="i", name="src"), FilterNode(id="b", filter="gblur", params={"sigma": "amount"}),
                 OutputNode(id="o", name="res", pads=[{"name": "v", "type": "video"}])],
                [("i", "v", "b", "0"), ("b", "0", "o", "v")])
    blur = blur.model_copy(update={"params": [GraphParam(name="amount", default="5")]})
    refs = {"g1": GraphRef(name="Blur", doc=blur)}

    def outer(node: GraphNode, params: tuple[GraphParam, ...] = ()) -> FilterGraphDoc:
        doc = _doc(_io(node), [("in", "v", "g", "src:v"), ("g", "res:v", "out", "v")])
        return doc.model_copy(update={"params": list(params)})

    assert compile_graph(outer(GraphNode(id="g", graph_id="g1")), catalog, refs).filter_complex == "[0:v]gblur=sigma=5[gblur1]"
    fixed = outer(GraphNode(id="g", graph_id="g1", options={"amount": "9"}))
    assert compile_graph(fixed, catalog, refs).filter_complex == "[0:v]gblur=sigma=9[gblur1]"
    lifted = outer(GraphNode(id="g", graph_id="g1", params={"amount": "blur"}), (GraphParam(name="blur", default="2"),))
    assert compile_graph(lifted, catalog, refs, {"blur": "7"}).filter_complex == "[0:v]gblur=sigma=7[gblur1]"
    wrong = outer(GraphNode(id="g", graph_id="g1", options={"radius": "1"}))
    assert any("'Blur' has no parameter 'radius'" in i.message for i in compile_graph(wrong, catalog, refs).errors)


def test_import_command(catalog: FilterCatalog):
    doc, issues = import_command(
        'ffmpeg -ss 2 -i clip.mp4 -i logo.png -filter_complex "[1:v]scale=iw/4:-2[l];[0:v][l]overlay=x=10:y=10[v]" '
        '-map "[v]" -map 0:a? -c:v libx264 -crf 20 -x264-params stats=/tmp/x {stem}-logo.mp4', catalog)
    assert [i.message for i in issues] == ["-x264-params isn't supported on an output; ignored."]
    inputs = [n for n in doc.nodes if isinstance(n, InputNode)]
    assert [(n.name, n.options) for n in inputs] == [("clip", {"ss": "2"}), ("logo", {})]
    scale = next(n for n in doc.nodes if isinstance(n, FilterNode) and n.filter == "scale")
    assert scale.options == {"w": "iw/4", "h": "-2"} and not scale.args
    out = next(n for n in doc.nodes if isinstance(n, OutputNode))
    assert (out.name, out.filename, out.options) == ("logo", "{stem}-logo.mp4", {"c:v": "libx264", "crf": "20"})
    c = compile_graph(doc, catalog)
    assert c.ok and c.filter_complex == "[1:v]scale=w=iw/4:h=-2[scale1];[0:v][scale1]overlay=x=10:y=10[overlay1]"


def test_import_plain_filtergraph(catalog: FilterCatalog):
    doc, issues = import_command("hqdn3d,unsharp", catalog)
    c = compile_graph(doc, catalog)
    assert not issues and c.ok and c.filter_complex == "[0:v]hqdn3d,unsharp[unsharp1]"
    assert c.outputs[0].maps == ["[unsharp1]", "0:a?"]


@pytest.fixture(scope="module")
def sample_videos(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")
    d = tmp_path_factory.mktemp("studio_src")
    for name in ("a.mp4", "b.mp4"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=640x360:rate=10",
                        "-f", "lavfi", "-i", "sine=duration=1", "-shortest", "-pix_fmt", "yuv420p", str(d / name)], check=True)
    return d


@pytest.mark.parametrize("example", EXAMPLES, ids=[e.id for e in EXAMPLES])
def test_examples_run_in_ffmpeg(catalog: FilterCatalog, sample_videos: Path, tmp_path: Path, example):
    doc, issues = import_command(example.command, catalog)
    assert not [i for i in issues if i.level == "error"], issues
    c = compile_graph(doc, catalog)
    assert c.ok, [i.message for i in c.issues]
    inputs = {inp.node: str(sample_videos / ("a.mp4" if inp.index == 0 else "b.mp4")) for inp in c.inputs}
    outputs = {o.node: str(tmp_path / o.filename.format(stem="x", output=o.name, graph="g")) for o in c.outputs}
    c.ffmpeg_command(inputs, outputs, overwrite=True).run()
    assert all(Path(p).stat().st_size > 0 for p in outputs.values())


# ---------------------------------------------------------------------------
# Service and HTTP API (in-memory fakes)
# ---------------------------------------------------------------------------

class FakeGraphs:
    def __init__(self) -> None:
        self.docs: dict[str, FilterGraphRecord] = {}

    async def list_all(self):
        return sorted(self.docs.values(), key=lambda r: r.updated_at, reverse=True)

    async def get(self, graph_id):
        return self.docs.get(graph_id)

    async def get_many(self, graph_ids):
        return {g: self.docs[g] for g in graph_ids if g in self.docs}

    async def find_by_name(self, name_key):
        return next((r for r in self.docs.values() if r.name_key == name_key), None)

    async def insert(self, record):
        if await self.find_by_name(record.name_key):
            raise GraphNameTakenError(record.name)
        self.docs[record.id] = record

    async def replace(self, record, expected_revision):
        if self.docs[record.id].revision != expected_revision:
            return False
        self.docs[record.id] = record
        return True

    async def delete(self, graph_id):
        return self.docs.pop(graph_id, None) is not None

    async def used_by(self, graph_id):
        return [r for r in self.docs.values() if graph_id in r.uses]


class FakeRecords:
    def __init__(self) -> None:
        self.docs: dict[str, MediaJobRecord] = {}

    async def insert(self, record):
        self.docs[record.job_id] = record

    async def get(self, job_id):
        return self.docs.get(job_id)

    async def get_many(self, job_ids):
        return {j: self.docs[j] for j in job_ids if j in self.docs}


class FakeJobs:
    def __init__(self) -> None:
        self.jobs: list[Job] = []

    async def submit(self, job_type, *, job_id=None, max_attempts=3, request_ref=None):
        now = datetime.datetime.now(datetime.UTC)
        job = Job(id=job_id or str(uuid.uuid4()), job_type=job_type, scope_id="s", max_attempts=max_attempts,
                  available_at=now, created_at=now, updated_at=now)
        self.jobs.insert(0, job)
        return job

    async def list(self, *, status=None, job_type=None, limit=50, offset=0):
        found = [j for j in self.jobs if job_type in (None, j.job_type) and status in (None, j.status)]
        return found[offset:offset + limit], len(found)


@pytest.fixture
def studio_root(tmp_path: Path, sample_videos: Path) -> Path:
    root = tmp_path / "media"
    (root / "clips").mkdir(parents=True)
    shutil.copy(sample_videos / "a.mp4", root / "clips" / "a.mp4")
    (root / "clips" / "notes.txt").write_text("x")
    (root / "existing.mp4").write_bytes(b"x")
    return root


@pytest.fixture
def studio(studio_root: Path, catalog: FilterCatalog) -> StudioService:
    jobs, records = FakeJobs(), FakeRecords()
    media_jobs = MediaJobService(root_path=studio_root, copy_source_roots=(), jobs=jobs, records=records)  # type: ignore[arg-type]
    return StudioService(root_path=studio_root, source_roots=(), catalog=catalog, store=FakeGraphs(),
                         jobs=jobs, records=records, media_jobs=media_jobs)  # type: ignore[arg-type]


@pytest.fixture
def client(studio: StudioService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_studio] = lambda: studio
    return TestClient(app)


SIMPLE = {
    "nodes": [
        {"kind": "input", "id": "in", "name": "in"},
        {"kind": "filter", "id": "s", "filter": "scale", "options": {"w": "iw/2", "h": "-2"}},
        {"kind": "output", "id": "out", "name": "out"},
    ],
    "edges": [
        {"source": "in", "source_pad": "v", "target": "s", "target_pad": "0"},
        {"source": "s", "source_pad": "0", "target": "out", "target_pad": "v"},
    ],
}


def test_studio_page_and_catalog(client: TestClient):
    assert "text/html" in client.get("/studio").headers["content-type"]
    filters = client.get("/api/studio/filters").json()
    assert any(f["name"] == "scale" and f["popular"] for f in filters["filters"])
    spec = client.get("/api/studio/filters/overlay").json()
    assert [p["name"] for p in spec["input_pads"]] == ["main", "overlay"] and spec["doc_url"].endswith("#overlay")
    assert client.get("/api/studio/filters/nope").status_code == 404
    assert {o["name"] for o in client.get("/api/studio/io-options").json()["inputs"]} >= {"ss", "t"}


def test_compile_and_import_endpoints(client: TestClient):
    r = client.post("/api/studio/compile", json={"graph": SIMPLE}).json()
    assert r["ok"] and r["filter_complex"] == "[0:v]scale=w=iw/2:h=-2[scale1]" and "-filter_complex" in r["command"]
    bad = client.post("/api/studio/compile", json={"graph": {**SIMPLE, "edges": SIMPLE["edges"][:1]}}).json()
    assert not bad["ok"] and bad["issues"][0]["node"] == "s"
    imported = client.post("/api/studio/import", json={"text": "ffmpeg -i x.mp4 -vf hflip y.mp4"}).json()
    assert [n["kind"] for n in imported["graph"]["nodes"]] == ["input", "filter", "output"]
    examples = client.get("/api/studio/examples").json()["items"]
    assert {e["id"] for e in examples} == {e.id for e in EXAMPLES}


def test_library_crud(client: TestClient):
    r = client.post("/api/studio/graphs", json={"name": "Half", "description": "d", "tags": ["resize"], "graph": SIMPLE})
    assert r.status_code == 201
    half = r.json()
    assert half["revision"] == 1 and half["filters"] == ["scale"]
    assert [p["key"] for p in half["interface"]["inputs"]] == ["in:v"]
    assert client.post("/api/studio/graphs", json={"name": "half", "graph": SIMPLE}).status_code == 409

    user = {"nodes": [{"kind": "input", "id": "i"}, {"kind": "graph", "id": "g", "graph_id": half["id"]},
                      {"kind": "output", "id": "o"}],
            "edges": [{"source": "i", "source_pad": "v", "target": "g", "target_pad": "in:v"},
                      {"source": "g", "source_pad": "out:v", "target": "o", "target_pad": "v"}]}
    wrapper = client.post("/api/studio/graphs", json={"name": "Wrapper", "graph": user}).json()
    assert wrapper["uses"] == [half["id"]]
    assert client.post("/api/studio/compile", json={"graph": user}).json()["filter_complex"] == "[0:v]scale=w=iw/2:h=-2[scale1]"

    # Embedding Wrapper in Half would make Half contain itself.
    looped = {**user, "nodes": [*user["nodes"][:1], {"kind": "graph", "id": "g", "graph_id": wrapper["id"]}, user["nodes"][2]]}
    assert client.put(f"/api/studio/graphs/{half['id']}", json={"name": "Half", "graph": looped}).status_code == 422
    assert client.put(f"/api/studio/graphs/{half['id']}", json={"name": "Half", "graph": SIMPLE, "revision": 7}).status_code == 409
    updated = client.put(f"/api/studio/graphs/{half['id']}", json={"name": "Half size", "graph": SIMPLE, "revision": 1}).json()
    assert updated["revision"] == 2 and updated["name"] == "Half size"

    assert client.delete(f"/api/studio/graphs/{half['id']}").status_code == 409  # used by Wrapper
    assert client.delete(f"/api/studio/graphs/{wrapper['id']}").status_code == 204
    assert client.delete(f"/api/studio/graphs/{half['id']}").status_code == 204
    assert client.get("/api/studio/graphs").json() == {"items": []}
    assert client.get(f"/api/studio/graphs/{half['id']}").status_code == 404


def test_media_listing(client: TestClient):
    root = client.get("/api/studio/media").json()
    assert root["path"] == "." and root["parent"] is None and root["dirs"] == ["clips"]
    clips = client.get("/api/studio/media", params={"path": "clips"}).json()
    assert [(f["name"], f["kind"]) for f in clips["files"]] == [("a.mp4", "video")]
    assert client.get("/api/studio/media", params={"path": "../.."}).status_code == 404


def test_run_validates_and_queues(client: TestClient, studio: StudioService):
    def run(**item):
        return client.post("/api/studio/run", json={"graph": SIMPLE, "graph_name": "Half", "items": [item]})

    assert "Choose a file" in run(inputs={}, outputs={"out": "x.mp4"}).json()["detail"]
    assert "not found" in run(inputs={"in": "clips/nope.mp4"}, outputs={"out": "x.mp4"}).json()["detail"]
    assert run(inputs={"in": "../etc/passwd"}, outputs={"out": "x.mp4"}).status_code == 422
    assert "already exists" in run(inputs={"in": "clips/a.mp4"}, outputs={"out": "existing.mp4"}).json()["detail"]
    assert run(inputs={"in": "clips/a.mp4"}, outputs={"out": "x.sh"}).status_code == 422
    assert run(inputs={"in": "clips/a.mp4"}, outputs={"out": "clips/a.mp4"}).status_code == 422

    r = run(inputs={"in": "clips/a.mp4"}, outputs={"out": "out/a-half.mp4"})
    assert r.status_code == 202
    job_id = r.json()["jobs"][0]["job_id"]
    record = asyncio.run(studio.records.get(job_id))
    assert record.job_type == STUDIO_RENDER and record.params["outputs"] == {"out": "out/a-half.mp4"}
    page = client.get("/api/studio/jobs").json()
    assert page["total"] == 1 and page["items"][0]["kind"] == "studio" and "graph" not in page["items"][0]["params"]
    assert client.get(f"/api/studio/jobs/{job_id}/graph").json()["nodes"][1]["filter"] == "scale"


def test_run_with_parameters(client: TestClient, studio: StudioService):
    graph = {**SIMPLE, "params": [{"name": "width", "default": "iw/2"}],
             "nodes": [SIMPLE["nodes"][0], {**SIMPLE["nodes"][1], "options": {"h": "-2"}, "params": {"w": "width"}}, SIMPLE["nodes"][2]]}
    saved = client.post("/api/studio/graphs", json={"name": "Sized", "graph": graph}).json()
    assert saved["params"] == [{"name": "width", "description": "", "default": "iw/2"}]

    def run(params: dict):
        return client.post("/api/studio/run", json={"graph": graph, "params": params,
                                                    "items": [{"inputs": {"in": "clips/a.mp4"}, "outputs": {"out": "out/p.mp4"}}]})

    assert "no parameter" in run({"nope": "1"}).json()["detail"]
    job_id = run({"width": "320"}).json()["jobs"][0]["job_id"]
    record = asyncio.run(studio.records.get(job_id))
    assert record.params["filter_complex"] == "[0:v]scale=h=-2:w=320[scale1]" and record.params["param_values"] == {"width": "320"}
    assert client.get(f"/api/studio/jobs/{job_id}/graph").json()["params"][0]["default"] == "320"


# ---------------------------------------------------------------------------
# End to end: real ffmpeg, MongoDB job worker
# ---------------------------------------------------------------------------

MONGO_URL = os.environ.get("TEST_MONGODB_URL")


@pytest.mark.skipif(not MONGO_URL or not HAS_FFMPEG, reason="needs TEST_MONGODB_URL and ffmpeg")
def test_render_job_end_to_end(studio_root: Path, tmp_path: Path):
    import pymongo

    from apps.api.composition import build_services
    from apps.api.settings import ServerConfig, Settings
    from mediatools.contracts.studio import StudioRunRequest

    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()

    async def main() -> None:
        db_name = f"test_studio_{uuid.uuid4().hex[:8]}"
        client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(MONGO_URL)
        try:
            config = ServerConfig.from_settings(Settings(
                site_root_path=studio_root, site_thumb_path=thumbs, site_mongodb_url=MONGO_URL, site_database_name=db_name,
            ))
            services = await build_services(config, client[db_name])
            accepted = await services.studio.run(StudioRunRequest.model_validate({
                "graph": SIMPLE, "items": [{"inputs": {"in": "clips/a.mp4"}, "outputs": {"out": "renders/a-half.mp4"}}],
            }))
            await services.worker.run_once()
            view = await services.media_jobs.get(accepted.jobs[0].job_id)
            assert view.job.status == JobStatus.SUCCEEDED.value, view.job.error_message
            assert view.result and view.result["outputs"] == ["renders/a-half.mp4"]
            assert (studio_root / "renders" / "a-half.mp4").stat().st_size > 0
            assert not list((studio_root / "renders").glob(".*tmp*"))
            log = [ln.message for ln in await services.job_manager.logs(view.job.id, limit=1000)]
            assert any(m.startswith("$ ffmpeg") for m in log)
            assert "renders" in await services.gallery.list_directories()
        finally:
            await client.drop_database(db_name)
            await client.aclose()

    asyncio.run(main())
