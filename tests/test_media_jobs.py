"""End-to-end tests for media jobs: real ffmpeg, a disposable MongoDB at TEST_MONGODB_URL, temp directories."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import pymongo
import pytest

from apps.api.composition import Services, build_services
from apps.api.settings import TEMPLATES_DIR, ServerConfig, Settings
from mediatools.application import InvalidJobRequestError
from mediatools.contracts import (
    CleanupRequest,
    ConvertMp4Request,
    MoveRequest,
    ReindexRequest,
    ThumbnailsRequest,
)
from mediatools.index_db import index_hash_func
from mediatools.jobs import JobStatus

MONGO_URL = os.environ.get("TEST_MONGODB_URL")
pytestmark = [
    pytest.mark.skipif(not MONGO_URL, reason="TEST_MONGODB_URL not set"),
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed"),
]


def make_video(path: Path, seconds: float, size: str = "64x48") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


@pytest.fixture(scope="module")
def video_cache(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("videos")
    specs = {"v1": (1.0, "mp4"), "v2": (1.2, "mp4"), "v3": (1.4, "mp4"), "v4": (1.6, "mkv"),
             "v5": (1.8, "mp4"), "v6": (2.0, "mp4"), "v7": (2.2, "mp4"), "v8": (2.4, "mp4")}
    out = {}
    for name, (secs, ext) in specs.items():
        out[name] = d / f"{name}.{ext}"
        make_video(out[name], secs)
    return out


@pytest.fixture
def tree(tmp_path: Path, video_cache: dict[str, Path]) -> dict[str, Path]:
    root, thumbs, incoming = tmp_path / "media", tmp_path / "thumbs", tmp_path / "incoming"
    for p in (root, thumbs, incoming):
        p.mkdir()
    def cp(name: str, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(video_cache[name], dst)

    cp("v1", root / "a" / "clip1.mp4")
    cp("v1", root / "a" / "clip1_copy.mp4")
    (root / "a" / "empty.mp4").write_bytes(b"")
    (root / "a" / "bad.mp4").write_bytes(b"not a video" * 200)
    cp("v4", root / "b" / "clip2.mkv")
    cp("v2", root / "trip" / "x.mp4")
    cp("v3", root / "trip2" / "y.mp4")
    batch = incoming / "batch"
    cp("v5", batch / "new1.mp4")
    cp("v6", batch / "sub" / "new2.mp4")
    cp("v7", batch / "dupe.mp4")
    cp("v7", root / "trip" / "batch" / "dupe.mp4")
    cp("v8", batch / "conflict.mp4")
    (root / "trip" / "batch" / "conflict.mp4").write_bytes(b"different")
    return {"root": root, "thumbs": thumbs, "incoming": incoming, "batch": batch}


def settings_for(tree: dict[str, Path], db_name: str, **extra: object) -> Settings:
    return Settings(
        site_root_path=tree["root"], site_thumb_path=tree["thumbs"], site_mongodb_url=MONGO_URL,
        site_database_name=db_name, **{"site_copy_source_roots": [tree["incoming"]], **extra},
    )


def run_services(
    tree: dict[str, Path],
    body: Callable[[Services, pymongo.AsyncMongoClient, str], Awaitable[None]],
    **extra: object,
) -> None:
    async def main() -> None:
        db_name = f"test_media_jobs_{uuid.uuid4().hex[:8]}"
        client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(MONGO_URL)
        try:
            config = ServerConfig.from_settings(settings_for(tree, db_name, **extra))
            await body(await build_services(config, client[db_name]), client, db_name)
        finally:
            await client.drop_database(db_name)
            await client.aclose()

    asyncio.run(main())


async def submit_and_run(services: Services, request: object) -> tuple[JobStatus, dict]:
    job = await services.media_jobs.submit(request)  # type: ignore[arg-type]
    await services.worker.run_once()
    view = await services.media_jobs.get(job.id)
    return JobStatus(view.job.status), {"view": view, "result": view.result or {}}


def test_reindex_subdir_tracks_stale_and_siblings(tree: dict[str, Path]):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        status, out = await submit_and_run(s, ReindexRequest(path="."))
        assert status is JobStatus.SUCCEEDED, out["view"].job.error_message
        r = out["result"]
        assert r["directories"] == 6 and r["videos_new"] == 5  # clip1/clip1_copy share a hash
        assert r["error_count"] == 3  # empty.mp4, bad.mp4, trip/batch/conflict.mp4 can't be probed
        assert set(await s.gallery.list_directories()) == {".", "a", "b", "trip", "trip/batch", "trip2"}
        log = [ln.message for ln in await s.job_manager.logs(out["view"].job.id, limit=1000)]
        assert any(m.startswith("Found 6 directories") for m in log)
        assert "[1/6] .: 0 videos, 0 images" in log
        assert sum(m.startswith("[") and "/6] " in m for m in log) == 6
        assert any("unreadable: a/bad.mp4" in m for m in log)
        assert log[-1] == "Finished"

        def disk_size(p: Path) -> int:
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

        ftree = await s.browser.tree()
        by_path = {f.path: f for f in ftree.folders}
        assert ftree.total_size == disk_size(tree["root"]) == by_path["."].size
        assert by_path["trip"].size == disk_size(tree["root"] / "trip")
        assert by_path["trip/batch"].parent == "trip" and by_path["trip"].num_subdirs == 1
        assert round(by_path["a"].percent, 6) == round(100 * disk_size(tree["root"] / "a") / ftree.total_size, 6)
        assert (by_path["a"].num_videos, by_path["a"].files) == (4, 4)
        listing = await s.browser.files("trip/batch")
        assert [(f.name, f.size) for f in listing.files] == [
            ("conflict.mp4", 9), ("dupe.mp4", (tree["root"] / "trip/batch/dupe.mp4").stat().st_size),
        ]

        shutil.rmtree(tree["root"] / "trip" / "batch")
        status, out = await submit_and_run(s, ReindexRequest(path="trip"))
        assert status is JobStatus.SUCCEEDED and out["result"]["directories_removed"] == 1
        assert set(await s.gallery.list_directories()) == {".", "a", "b", "trip", "trip2"}  # trip2 untouched
        page = await s.gallery.directory_page("trip")
        assert [v.vid_path_rel for v in page.vids] == ["trip/x.mp4"]

    run_services(tree, body)


def test_overlapping_jobs_wait_disjoint_jobs_run_in_parallel(tree: dict[str, Path]):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        jobs = [
            await s.media_jobs.submit(ReindexRequest(path=".")),
            await s.media_jobs.submit(ReindexRequest(path="trip")),
            await s.media_jobs.submit(ThumbnailsRequest(path="a")),
        ]
        stop = asyncio.Event()
        run = asyncio.create_task(s.worker.run(stop))
        deadline = time.monotonic() + 60
        while any(j.status is not JobStatus.SUCCEEDED for j in [await s.job_manager.get(j.id) for j in jobs]):
            assert time.monotonic() < deadline
            await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(run, 10)

        logs = {j.id: [ln.message for ln in await s.job_manager.logs(j.id, limit=1000)] for j in jobs}
        waited = [j for j in jobs if any(m.startswith("Waiting for another job") for m in logs[j.id])]
        assert len(waited) >= 1  # one of the overlapping rescans (. and trip) had to wait for the other
        attempts = [(await s.job_manager.get(j.id)).attempts for j in jobs]
        assert all(len(a) == 1 for a in attempts), attempts
        attempts = [a[0] for a in attempts]
        assert max(a.started_at for a in attempts) < min(a.finished_at for a in attempts if a.finished_at)

    run_services(tree, body)


def test_thumbnails_created_then_skipped(tree: dict[str, Path]):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        status, out = await submit_and_run(s, ThumbnailsRequest(path="trip", workers=2))
        assert status is JobStatus.SUCCEEDED, out["view"].job.error_message
        assert out["result"]["created"] == 2 and out["result"]["error_count"] == 1  # batch/conflict.mp4 isn't a video
        gif = tree["thumbs"] / f"{index_hash_func(tree['root'] / 'trip' / 'x.mp4')}.gif"
        assert gif.stat().st_size > 0
        assert not list(tree["thumbs"].glob(".*tmp*"))
        status, out = await submit_and_run(s, ThumbnailsRequest(path="trip"))
        assert out["result"]["created"] == 0 and out["result"]["skipped_existing"] == 2

    run_services(tree, body)


def test_cleanup_dry_run_then_delete(tree: dict[str, Path]):
    a = tree["root"] / "a"

    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        req = {"path": "a", "delete_empty": True, "delete_unprobable": True, "delete_duplicates": True}
        status, out = await submit_and_run(s, CleanupRequest(**req))
        r = out["result"]
        assert status is JobStatus.SUCCEEDED and r["dry_run"] is True and r["deleted"] == 0
        assert r["counts"] == {"empty": 1, "unprobable": 1, "duplicates": 1}
        assert r["duplicates"] == ["a/clip1.mp4 (kept clip1_copy.mp4)"]
        assert len(list(a.iterdir())) == 4

        status, out = await submit_and_run(s, CleanupRequest(**req, dry_run=False))
        assert status is JobStatus.SUCCEEDED and out["result"]["deleted"] == 3
        assert [p.name for p in a.iterdir()] == ["clip1_copy.mp4"]
        assert out["result"]["reindex"]["videos"] == 1

    run_services(tree, body)


def test_convert_mp4(tree: dict[str, Path]):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        status, out = await submit_and_run(s, ConvertMp4Request(path="b"))
        assert status is JobStatus.SUCCEEDED and out["result"]["converted"] == 1
        assert (tree["root"] / "b" / "clip2.mp4").stat().st_size > 0
        assert (tree["root"] / "b" / "clip2.mkv").exists()

    run_services(tree, body)


def test_move_from_inside_gallery_drops_source_entries(tree: dict[str, Path]):
    root = tree["root"]
    src = root / "a"

    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        (src / "deep").mkdir()
        shutil.move(src / "clip1.mp4", src / "deep" / "clip1.mp4")
        await submit_and_run(s, ReindexRequest(path="."))
        assert {"a", "a/deep"} <= set(await s.gallery.list_directories())
        assert len((await s.gallery.directory_page("a")).vids) >= 1

        status, out = await submit_and_run(s, MoveRequest(source=str(src), dest="b/from_a"))
        r = out["result"]
        assert status is JobStatus.SUCCEEDED, out["view"].job.error_message
        assert r["source_reindex"]["directories_removed"] == 1  # a/deep was emptied and removed

        dirs = set(await s.gallery.list_directories())
        assert "a/deep" not in dirs and "b/from_a" in dirs and "b/from_a/deep" in dirs
        assert (await s.gallery.directory_page("a")).vids == []
        assert len((await s.gallery.directory_page("b/from_a")).vids) >= 1
        log = [ln.message for ln in await s.job_manager.logs(out["view"].job.id, limit=1000)]
        assert any(m.startswith("Source is inside the gallery") for m in log)

    run_services(tree, body, site_copy_source_roots=[root])


def test_move_then_rescan(tree: dict[str, Path]):
    dest = tree["root"] / "trip" / "batch"

    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        await submit_and_run(s, ReindexRequest(path="."))

        status, out = await submit_and_run(s, MoveRequest(source=str(tree["batch"]), dest="trip/batch", workers=3))
        r = out["result"]
        assert status is JobStatus.SUCCEEDED, out["view"].job.error_message
        assert (r["moved"], r["deduplicated"], r["conflicts"]) == (2, 1, ["conflict.mp4"])
        assert r["source_empty"] is False and len(r["warnings"]) == 1
        assert sorted(p.name for p in tree["batch"].rglob("*")) == ["conflict.mp4"]
        assert (dest / "sub" / "new2.mp4").is_file() and (dest / "new1.mp4").is_file()
        assert (dest / "conflict.mp4").read_bytes() == b"different"
        assert "trip/batch/sub" in await s.gallery.list_directories()
        assert r["reindex"]["videos_new"] == 2

    run_services(tree, body)


def test_move_creates_new_folder_linked_into_parent(tree: dict[str, Path]):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        await submit_and_run(s, ReindexRequest(path="."))
        (tree["batch"] / "conflict.mp4").unlink()
        status, out = await submit_and_run(s, MoveRequest(source=str(tree["batch"]), dest="imported"))
        assert status is JobStatus.SUCCEEDED and out["result"]["source_empty"] is True
        assert list(tree["batch"].iterdir()) == []
        root_page = await s.gallery.directory_page(".")
        assert "imported" in [sp.page_path_rel for sp in root_page.subpages]
        root_doc = await s.gallery.dirs.find_by_path(tree["root"])
        assert root_doc is not None and "imported" in root_doc.subpaths

    run_services(tree, body)


@pytest.mark.skipif(os.geteuid() == 0, reason="permission checks are meaningless as root")
def test_move_refuses_sources_it_cannot_delete_from(tree: dict[str, Path]):
    batch = tree["batch"]

    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        batch.chmod(0o555)
        try:
            with pytest.raises(InvalidJobRequestError, match="sudo chown -R"):
                await s.media_jobs.submit(MoveRequest(source=str(batch), dest="imported"))
        finally:
            batch.chmod(0o755)

        (batch / "sub").chmod(0o555)
        try:
            status, out = await submit_and_run(s, MoveRequest(source=str(batch), dest="imported"))
        finally:
            (batch / "sub").chmod(0o755)
        job = out["view"].job
        assert status is JobStatus.FAILED and job.error_code == "permission_denied" and job.attempt_count == 1
        assert "sub" in job.error_message and "Nothing was moved" in job.error_message
        assert not (tree["root"] / "imported").exists()
        assert (batch / "new1.mp4").exists()

    run_services(tree, body)


def test_submission_validation(tree: dict[str, Path], tmp_path: Path):
    async def body(s: Services, client: pymongo.AsyncMongoClient, db: str) -> None:
        bad = [
            ReindexRequest(path="../incoming"),
            ReindexRequest(path="does/not/exist"),
            MoveRequest(source=str(tree["root"] / "a"), dest="x"),
            MoveRequest(source="/etc", dest="x"),
            MoveRequest(source="relative/path", dest="x"),
            MoveRequest(source=str(tree["batch"]), dest="../outside"),
        ]
        for req in bad:
            with pytest.raises(InvalidJobRequestError):
                await s.media_jobs.submit(req)
        assert (await s.media_jobs.list()).total == 0

    run_services(tree, body)


def test_cleanup_requires_a_selection():
    with pytest.raises(ValueError):
        CleanupRequest(path=".")


def test_api_end_to_end(tree: dict[str, Path]):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    db_name = f"test_media_api_{uuid.uuid4().hex[:8]}"
    settings = settings_for(tree, db_name, site_template_path=TEMPLATES_DIR / "gallery.html")
    try:
        with TestClient(create_app(settings)) as client:
            assert "text/html" in client.get("/jobs").headers["content-type"]
            assert client.get("/api/job-config").json()["copy_source_roots"] == [str(tree["incoming"].resolve())]
            bad = client.post("/api/jobs/reindex", json={"path": "../.."})
            assert bad.status_code == 422 and "outside" in bad.json()["detail"]
            assert client.post("/api/jobs/cleanup", json={"path": "."}).status_code == 422

            r = client.post("/api/jobs/reindex", json={"path": "."})
            assert r.status_code == 202
            accepted = r.json()
            assert accepted["status"] == "queued" and accepted["status_url"] == f"/v1/jobs/{accepted['job_id']}"

            deadline = time.monotonic() + 30
            while (job := client.get(accepted["status_url"]).json())["status"] in ("queued", "running"):
                assert time.monotonic() < deadline, job
                time.sleep(0.2)
            assert job["status"] == "succeeded" and job["progress_percent"] == 100
            assert "lease_token" not in job

            listing = client.get("/api/media-jobs").json()
            assert listing["total"] == 1 and listing["items"][0]["kind"] == "reindex"
            assert listing["items"][0]["result"]["directories"] == 6
            assert client.get("/v1/jobs", params={"status": "succeeded"}).json()["total"] == 1
            assert client.get("/v1/jobs/nope").status_code == 404
            log = client.get(f"/v1/jobs/{accepted['job_id']}/logs", params={"limit": 3}).json()
            assert [ln["message"] for ln in log["lines"]][-1] == "Finished" and log["last_id"] == log["lines"][-1]["id"]
            assert client.get(f"/v1/jobs/{accepted['job_id']}/logs", params={"after": log["last_id"]}).json()["lines"] == []
            assert client.get(f"/v1/jobs/{accepted['job_id']}/logs", params={"after": "bad"}).status_code == 422
            assert client.post(f"/v1/jobs/{accepted['job_id']}/cancel").json()["status"] == "succeeded"

            assert "/jobs?path=trip" in client.get("/page/trip").text
    finally:
        pymongo.MongoClient(MONGO_URL).drop_database(db_name)
