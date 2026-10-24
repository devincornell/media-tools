from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from apps.api.dependencies import get_uploads
from apps.api.main import create_app
from mediatools.application import (
    InvalidUploadError,
    UploadConflictError,
    UploadIncompleteError,
)
from mediatools.application.uploads import UploadService, clean_relative_path
from mediatools.contracts.uploads import UploadFileSpec


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "media"
    r.mkdir()
    return r


@pytest.fixture
def service(root: Path) -> UploadService:
    return UploadService(root_path=root)


@pytest.fixture
def client(service: UploadService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_uploads] = lambda: service
    return TestClient(app)  # lifespan (MongoDB) is skipped


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for p in parts:
        yield p


def store(service: UploadService, dest: str, rel: str, *parts: bytes, **kw):  # type: ignore[no-untyped-def]
    return asyncio.run(service.store(dest, rel, chunks(*parts), **kw))


def leftovers(root: Path) -> list[Path]:
    return [p for p in root.rglob(".upload-*")]


# --------------------------------------------------------------------------- path validation

@pytest.mark.parametrize("rel", [
    "", "/etc/passwd", "../x", "a/../../x", "a/./b", "a//b", "a/", "..", ".", "a/\x00b", "a/b\nc", "x" * 256,
])
def test_clean_relative_path_rejects(rel: str):
    with pytest.raises(InvalidUploadError):
        clean_relative_path(rel)


def test_clean_relative_path_accepts_normal_names():
    assert clean_relative_path("Trips/Italy 2024/clip (1).mp4") == ("Trips", "Italy 2024", "clip (1).mp4")
    assert clean_relative_path("naïve/😀.jpg") == ("naïve", "😀.jpg")
    assert clean_relative_path("..hidden/.dot") == ("..hidden", ".dot")


# --------------------------------------------------------------------------- service

def test_store_preserves_structure_and_mtime(service: UploadService, root: Path):
    r = store(service, "imports/batch1", "Trips/Italy/clip.mp4", b"abc", b"def" * 1000, expected_size=3003, mtime_ms=1_700_000_000_000)
    assert (r.path, r.size, r.replaced) == ("imports/batch1/Trips/Italy/clip.mp4", 3003, False)
    f = root / "imports/batch1/Trips/Italy/clip.mp4"
    assert f.read_bytes() == b"abc" + b"def" * 1000 and int(f.stat().st_mtime) == 1_700_000_000
    assert leftovers(root) == []


def test_large_streamed_body_is_written_in_full(service: UploadService, root: Path):
    big = [os.urandom(100_000) for _ in range(60)]  # 6 MB, several write buffers
    r = store(service, ".", "big.bin", *big, expected_size=6_000_000)
    assert r.size == 6_000_000 and (root / "big.bin").read_bytes() == b"".join(big)


def test_conflict_overwrite_and_race_safety(service: UploadService, root: Path):
    store(service, ".", "a/f.txt", b"one")
    with pytest.raises(UploadConflictError):
        store(service, ".", "a/f.txt", b"two")
    assert (root / "a/f.txt").read_bytes() == b"one" and leftovers(root) == []
    r = store(service, ".", "a/f.txt", b"three", overwrite=True)
    assert r.replaced and (root / "a/f.txt").read_bytes() == b"three"
    (root / "a/dir").mkdir()
    with pytest.raises(InvalidUploadError):
        store(service, ".", "a/dir", b"x", overwrite=True)
    with pytest.raises(UploadConflictError):  # "a/f.txt" is a file, so it can't be a parent folder
        store(service, ".", "a/f.txt/inner", b"x")


def test_incomplete_and_failed_uploads_leave_nothing_behind(service: UploadService, root: Path):
    with pytest.raises(UploadIncompleteError):
        store(service, ".", "short.bin", b"12345", expected_size=10)
    assert not (root / "short.bin").exists() and leftovers(root) == []

    async def broken() -> AsyncIterator[bytes]:
        yield b"partial"
        raise ConnectionError("client went away")

    with pytest.raises(ConnectionError):
        asyncio.run(service.store(".", "broken.bin", broken()))
    assert not (root / "broken.bin").exists() and leftovers(root) == []


@pytest.mark.parametrize("dest", ["..", "../x", "a/../../x"])
def test_destination_cannot_escape_root(service: UploadService, root: Path, dest: str):
    with pytest.raises(InvalidUploadError):
        store(service, dest, "f.txt", b"x")
    assert not list(root.parent.glob("*.txt")) and not list(root.parent.glob("x"))


def test_check_states(service: UploadService, root: Path):
    store(service, "d", "same.bin", b"1234")
    store(service, "d", "diff.bin", b"1234")
    (root / "d/folder").mkdir()
    specs = [UploadFileSpec(path=p, size=s) for p, s in [
        ("same.bin", 4), ("diff.bin", 9), ("new/one.bin", 1), ("folder", 1), ("../bad", 1), ("same.bin/inner", 1),
    ]]
    items = asyncio.run(service.check("d", specs))
    assert [(i.state, i.existing_size) for i in items] == [
        ("same", 4), ("conflict", 4), ("new", None), ("conflict", None), ("invalid", None), ("conflict", None),
    ]


@pytest.mark.skipif(os.geteuid() == 0, reason="permission checks are meaningless as root")
def test_unwritable_destination_reports_permission_error(service: UploadService, root: Path):
    from mediatools.application import UploadPermissionError

    locked = root / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        with pytest.raises(UploadPermissionError, match="locked"):
            store(service, "locked", "f.txt", b"x")
    finally:
        locked.chmod(0o755)


# --------------------------------------------------------------------------- HTTP

def test_http_upload_streaming_body_and_metadata(client: TestClient, root: Path):
    def body() -> Iterator[bytes]:
        yield b"hello "
        yield b"world"

    r = client.put("/api/uploads/file", params={"dest": "in/box", "path": "Folder/sub/a.txt", "mtime": 1_600_000_000_000}, content=body())
    assert r.status_code == 200 and r.json() == {"path": "in/box/Folder/sub/a.txt", "size": 11, "replaced": False}
    assert (root / "in/box/Folder/sub/a.txt").read_bytes() == b"hello world"

    again = client.put("/api/uploads/file", params={"dest": "in/box", "path": "Folder/sub/a.txt"}, content=b"zzz")
    assert again.status_code == 409 and "already exists" in again.json()["detail"]
    ok = client.put("/api/uploads/file", params={"dest": "in/box", "path": "Folder/sub/a.txt", "overwrite": "true"}, content=b"zzz")
    assert ok.json()["replaced"] is True and (root / "in/box/Folder/sub/a.txt").read_bytes() == b"zzz"


@pytest.mark.parametrize("params", [
    {"dest": ".", "path": "../escape.txt"},
    {"dest": "..", "path": "x.txt"},
    {"dest": ".", "path": "/abs.txt"},
    {"dest": ".", "path": "a//b.txt"},
])
def test_http_rejects_traversal(client: TestClient, root: Path, params: dict[str, str]):
    r = client.put("/api/uploads/file", params=params, content=b"x")
    assert r.status_code == 422
    assert not (root.parent / "escape.txt").exists() and not (root.parent / "x.txt").exists() and leftovers(root) == []


def test_http_check(client: TestClient, root: Path):
    client.put("/api/uploads/file", params={"path": "have.bin"}, content=b"1234")
    body = {"dest": ".", "files": [{"path": "have.bin", "size": 4}, {"path": "new.bin", "size": 1}, {"path": "../x", "size": 1}]}
    r = client.post("/api/uploads/check", json=body)
    assert [i["state"] for i in r.json()["items"]] == ["same", "new", "invalid"]
    assert client.post("/api/uploads/check", json={"dest": ".", "files": [{"path": "f", "size": 1}] * 2001}).status_code == 422


def test_upload_page_and_static_files(client: TestClient):
    assert "text/html" in client.get("/upload").headers["content-type"]
    assert client.get("/static/picker.js").status_code == 200
