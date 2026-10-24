"""Tests for the gallery use cases, the FastAPI app, and the HTTP SDK, using an in-memory index."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from apps.api.dependencies import get_gallery, get_renderer
from apps.api.main import create_app
from apps.api.rendering import PageRenderer
from apps.api.settings import TEMPLATES_DIR
from mediatools.application import (
    DirectoryNotIndexedError,
    GalleryService,
    MediaFileNotFoundError,
    PathOutsideRootError,
)
from mediatools.client import GalleryClient
from mediatools.contracts import DirectoryPage
from mediatools.file_stat_result import FileStatResult
from mediatools.index_db import MediaDirIndexDoc, VideoFileNotFoundError, VideoIndexDoc
from mediatools.index_db.mediadir_index_collection import IndexImageFile, IndexVideoFile
from mediatools.video.ffmpeg import ProbeInfo


class FakeDirs:
    def __init__(self, docs: list[MediaDirIndexDoc]):
        self.docs = {d.path_str: d for d in docs}

    async def find_by_path(self, path: Path) -> MediaDirIndexDoc | None:
        return self.docs.get(str(path))

    async def find_direct_subdirs(self, path: Path) -> list[MediaDirIndexDoc]:
        return [d for d in self.docs.values() if d.path.parent == Path(path)]

    async def find_by_path_prefix(self, prefix: Path) -> list[MediaDirIndexDoc]:
        return [d for p, d in self.docs.items() if p.startswith(str(prefix))]


class FakeVideos:
    def __init__(self, docs: list[VideoIndexDoc]):
        self.docs = {d.file_hash: d for d in docs}

    async def find_by_hash(self, file_hash: str) -> VideoIndexDoc:
        try:
            return self.docs[file_hash]
        except KeyError:
            raise VideoFileNotFoundError(file_hash)


def _probe(path: Path, duration: float) -> ProbeInfo:
    return ProbeInfo(
        fname=str(path), nb_streams=1, nb_programs=0, format_name="mp4", format_long_name="MP4",
        start_time="0", bit_rate=None, dur=str(duration), size=path.stat().st_size, probe_score=100,
        tags={"creation_time": "2024-05-01T12:30:00"}, video_streams=[], audio_streams=[], other_streams=[],
    )


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    (root / "trip").mkdir(parents=True)
    (root / "long_video.mp4").write_bytes(b"0123456789" * 100)
    (root / "short_clip.mp4").write_bytes(b"clip")
    (root / "photo.jpg").write_bytes(b"jpg")
    (root / "trip" / "beach.mp4").write_bytes(b"beach")
    (tmp_path / "secret.txt").write_text("outside root")
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "hash_long.gif").write_bytes(b"GIF89a")
    (thumbs / "hash_beach.gif").write_bytes(b"GIF89a")
    return root


@pytest.fixture
def gallery(media_root: Path) -> GalleryService:
    root = media_root
    stat = FileStatResult.read_from_path
    vids = {
        "long_video.mp4": ("hash_long", 120.0),
        "short_clip.mp4": ("hash_short", 3.0),
        "missing.mp4": ("hash_missing", 1.0),
    }
    root_doc = MediaDirIndexDoc(
        path_str=str(root),
        subpaths={"trip": str(root / "trip")},
        video_files={
            name: IndexVideoFile(path_str=str(root / name), stat=stat(root / "short_clip.mp4"), file_hash=h)
            for name, (h, _) in vids.items()
        },
        image_files={"photo.jpg": IndexImageFile(path_str=str(root / "photo.jpg"), stat=stat(root / "photo.jpg"), res=(400, 200))},
        other_files={},
    )
    trip_doc = MediaDirIndexDoc(
        path_str=str(root / "trip"),
        subpaths={},
        video_files={"beach.mp4": IndexVideoFile(path_str=str(root / "trip/beach.mp4"), stat=stat(root / "trip/beach.mp4"), file_hash="hash_beach")},
        image_files={},
        other_files={},
    )
    video_docs = [
        VideoIndexDoc(path_str=str(root / name), file_hash=h, probe=_probe(root / name, dur), stat=stat(root / name))
        for name, (h, dur) in vids.items() if name != "missing.mp4"
    ]
    return GalleryService(
        root_path=root,
        thumb_path=root.parent / "thumbs",
        max_clip_duration=10.0,
        dirs=FakeDirs([root_doc, trip_doc]),
        videos=FakeVideos(video_docs),
    )


@pytest.fixture
def client(gallery: GalleryService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_gallery] = lambda: gallery
    app.dependency_overrides[get_renderer] = lambda: PageRenderer(TEMPLATES_DIR / "gallery.html", TEMPLATES_DIR / "reels.html")
    return TestClient(app)  # not entered as a context manager, so lifespan (MongoDB) is skipped


# ---------------------------------------------------------------------------
# Application layer
# ---------------------------------------------------------------------------

def test_directory_page_splits_videos_and_clips(gallery: GalleryService):
    page = asyncio.run(gallery.directory_page("."))
    assert page.page_path_rel == "."
    assert [v.vid_path_rel for v in page.vids] == ["long_video.mp4"]
    assert [v.vid_path_rel for v in page.clips] == ["short_clip.mp4"]
    assert page.num_vids == 3  # missing video doc is skipped in lists but still counted
    assert page.vids[0].thumb_exists and not page.clips[0].thumb_exists
    assert page.vids[0].created == "2024-05-01 12:30:00"
    assert page.images[0].aspect == 2.0
    assert [s.page_path_rel for s in page.subpages] == ["trip"]
    assert page.subpages[0].subfolder_thumbs_all == ["hash_beach"]


def test_directory_page_not_indexed(gallery: GalleryService):
    with pytest.raises(DirectoryNotIndexedError):
        asyncio.run(gallery.directory_page("nope"))


@pytest.mark.parametrize("rel", ["../secret.txt", "trip/../../secret.txt", "/etc/passwd"])
def test_paths_cannot_escape_root(gallery: GalleryService, rel: str):
    with pytest.raises(PathOutsideRootError):
        gallery.media_file(rel)


@pytest.mark.parametrize("file_hash", ["..", "../x", "hash_short", "a.png"])
def test_thumbnail_rejects_invalid_or_missing(gallery: GalleryService, file_hash: str):
    with pytest.raises(MediaFileNotFoundError):
        gallery.thumbnail_file(file_hash)


def test_list_videos(gallery: GalleryService):
    assert sorted(asyncio.run(gallery.list_videos())) == sorted(["long_video.mp4", "short_clip.mp4", "missing.mp4", "trip/beach.mp4"])


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

def test_root_redirects(client: TestClient):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/page/"


@pytest.mark.parametrize("url", ["/page/", "/page/trip", "/reel/", "/reel/trip"])
def test_html_pages_render(client: TestClient, url: str):
    r = client.get(url)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_gallery_page_contains_media(client: TestClient):
    html = client.get("/page/").text
    assert "/video/long_video.mp4" in html
    assert "/file/photo.jpg" in html


def test_page_not_found(client: TestClient):
    r = client.get("/page/does/not/exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Page not found: does/not/exist"}


def test_file_traversal_blocked(client: TestClient):
    r = client.get("/file/..%2Fsecret.txt")
    assert r.status_code == 404
    assert "outside root" not in r.text


def test_video_range_request(client: TestClient):
    r = client.get("/video/long_video.mp4", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == b"0123456789"
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["content-range"] == "bytes 10-19/1000"


def test_video_full_and_unsatisfiable(client: TestClient):
    assert client.get("/video/long_video.mp4").content == b"0123456789" * 100
    assert client.get("/video/long_video.mp4", headers={"Range": "bytes=5000-"}).status_code == 416


def test_thumb(client: TestClient):
    assert client.get("/thumb/hash_long.gif").content == b"GIF89a"
    assert client.get("/thumb/hash_short.gif").status_code == 404


def test_plaintext_listings(client: TestClient):
    assert set(client.get("/list_directories").text.splitlines()) == {".", "trip"}
    assert "trip/beach.mp4" in client.get("/list_videos").text.splitlines()


# ---------------------------------------------------------------------------
# SDK <-> API contract
# ---------------------------------------------------------------------------

def test_sdk_matches_service(client: TestClient, gallery: GalleryService):
    sdk = GalleryClient(http_client=client)
    assert sdk.get_directory(".") == asyncio.run(gallery.directory_page("."))
    assert sdk.get_directory("trip") == asyncio.run(gallery.directory_page("trip"))
    assert isinstance(sdk.get_directory(), DirectoryPage)
    assert sorted(sdk.list_videos()) == sorted(asyncio.run(gallery.list_videos()))
    assert sorted(sdk.list_directories()) == sorted(asyncio.run(gallery.list_directories()))


def test_sdk_not_found(client: TestClient):
    with pytest.raises(DirectoryNotIndexedError, match="Page not found"):
        GalleryClient(http_client=client).get_directory("nope")
