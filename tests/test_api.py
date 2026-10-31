"""Tests for the gallery use cases, the FastAPI app, and the HTTP SDK, using an in-memory index."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from apps.api.dependencies import get_browser, get_favorites, get_gallery, get_picker, get_renderer
from apps.api.main import create_app
from apps.api.rendering import PageRenderer
from mediatools.application.folder_picker import FolderPicker
from mediatools.application import (
    BrowserService,
    DirectoryNotIndexedError,
    FavoriteService,
    GalleryService,
    MediaFileNotFoundError,
    PathOutsideRootError,
)
from mediatools.client import GalleryClient
from mediatools.contracts import DirectoryPage
from mediatools.file_stat_result import FileStatResult
from mediatools.index_db import (
    DirectorySizeRow,
    MediaDirIndexDoc,
    VideoFileNotFoundError,
    VideoIndexDoc,
    path_prefix_regex,
)
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
        return [d for p, d in self.docs.items() if path_prefix_regex(prefix).match(p)]

    async def directory_sizes(self, prefix: Path) -> list[DirectorySizeRow]:
        return [
            DirectorySizeRow(
                path_str=d.path_str,
                bytes=sum(f.stat.size for g in (d.video_files, d.image_files, d.other_files) for f in g.values()),
                num_videos=len(d.video_files), num_images=len(d.image_files), num_other=len(d.other_files),
                num_subdirs=len(d.subpaths),
            )
            for d in await self.find_by_path_prefix(prefix)
        ]


class FakeVideos:
    def __init__(self, docs: list[VideoIndexDoc]):
        self.docs = {d.file_hash: d for d in docs}

    async def find_by_hash(self, file_hash: str) -> VideoIndexDoc:
        try:
            return self.docs[file_hash]
        except KeyError:
            raise VideoFileNotFoundError(file_hash)


class FakeFavorites:
    def __init__(self) -> None:
        self.hashes: list[str] = []

    async def add(self, file_hash: str) -> None:
        if file_hash not in self.hashes:
            self.hashes.insert(0, file_hash)

    async def remove(self, file_hash: str) -> None:
        if file_hash in self.hashes:
            self.hashes.remove(file_hash)

    async def among(self, file_hashes) -> set[str]:
        return set(file_hashes) & set(self.hashes)

    async def list_all(self) -> list[str]:
        return list(self.hashes)


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
def favorites() -> FakeFavorites:
    return FakeFavorites()


@pytest.fixture
def gallery(media_root: Path, favorites: FakeFavorites) -> GalleryService:
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
        favorites=favorites,
    )


@pytest.fixture
def browser(gallery: GalleryService) -> BrowserService:
    return BrowserService(root_path=gallery.root_path, dirs=gallery.dirs)  # type: ignore[arg-type]


@pytest.fixture
def client(gallery: GalleryService, browser: BrowserService, favorites: FakeFavorites) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_gallery] = lambda: gallery
    app.dependency_overrides[get_favorites] = lambda: FavoriteService(favorites, gallery.videos)
    app.dependency_overrides[get_browser] = lambda: browser
    app.dependency_overrides[get_picker] = lambda: FolderPicker(gallery.root_path, ())
    app.dependency_overrides[get_renderer] = lambda: PageRenderer()
    return TestClient(app)  # not entered as a context manager, so lifespan (MongoDB) is skipped


# ---------------------------------------------------------------------------
# Application layer
# ---------------------------------------------------------------------------

def test_browser_tree_rolls_up_sizes(browser: BrowserService):
    tree = asyncio.run(browser.tree())
    by_path = {f.path: f for f in tree.folders}
    # root: three video entries (4 bytes each) + photo.jpg (3); trip: beach.mp4 (5)
    assert tree.total_size == 20
    assert (by_path["."].size, by_path["."].direct_size, by_path["."].percent, by_path["."].files) == (20, 15, 100.0, 5)
    assert (by_path["trip"].size, by_path["trip"].percent, by_path["trip"].parent) == (5, 25.0, ".")
    assert by_path["."].parent is None


def test_browser_tree_skips_unindexed_gaps(tmp_path: Path):
    def doc(p: Path) -> MediaDirIndexDoc:
        return MediaDirIndexDoc(path_str=str(p), subpaths={}, video_files={}, image_files={}, other_files={})

    root = tmp_path / "lib"
    fake = FakeDirs([doc(root), doc(root / "x" / "y"), doc(tmp_path / "library2")])
    tree = asyncio.run(BrowserService(root_path=root, dirs=fake).tree())  # type: ignore[arg-type]
    assert {f.path: f.parent for f in tree.folders} == {".": None, "x/y": "."}
    assert tree.total_size == 0 and all(f.percent == 0 for f in tree.folders)


def test_browser_files(browser: BrowserService):
    listing = asyncio.run(browser.files("."))
    assert [(f.name, f.kind) for f in listing.files] == [
        ("long_video.mp4", "video"), ("missing.mp4", "video"), ("photo.jpg", "image"), ("short_clip.mp4", "video"),
    ]
    assert asyncio.run(browser.files("trip")).files[0].path == "trip/beach.mp4"
    with pytest.raises(DirectoryNotIndexedError):
        asyncio.run(browser.files("nope"))
    with pytest.raises(PathOutsideRootError):
        asyncio.run(browser.files(".."))


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


def test_folder_picker_endpoints(client: TestClient, media_root: Path):
    assert client.get("/api/fs/roots").json() == [{"scope": "gallery", "path": str(media_root)}]
    listing = client.get("/api/fs/dirs", params={"scope": "gallery"}).json()
    assert listing["rel"] == "." and [d["name"] for d in listing["dirs"]] == ["trip"]
    assert client.get("/api/fs/dirs", params={"scope": "gallery", "path": str(media_root.parent)}).status_code == 404
    assert client.get("/api/fs/dirs", params={"scope": "source"}).status_code == 422


def test_browse_endpoints(client: TestClient):
    assert "text/html" in client.get("/browse").headers["content-type"]
    tree = client.get("/api/browse/tree").json()
    assert tree["total_size"] == 20 and {f["path"] for f in tree["folders"]} == {".", "trip"}
    files = client.get("/api/browse/files", params={"path": "trip"}).json()
    assert files == {"path": "trip", "files": [files["files"][0]]} and files["files"][0]["name"] == "beach.mp4"
    assert client.get("/api/browse/files", params={"path": "nope"}).status_code == 404
    assert client.get("/api/browse/files", params={"path": "../.."}).status_code == 404


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
# Favorites
# ---------------------------------------------------------------------------

def test_favorite_videos_sort_first_and_survive_a_move(tmp_path: Path, favorites: FakeFavorites):
    stat = FileStatResult.read_from_path
    names = ["a.mp4", "b.mp4"]

    def service(root: Path) -> GalleryService:
        root.mkdir(exist_ok=True)
        for n in names:
            (root / n).write_bytes(b"x")
        doc = MediaDirIndexDoc(
            path_str=str(root), subpaths={},
            video_files={n: IndexVideoFile(path_str=str(root / n), stat=stat(root / n), file_hash=f"h_{n[0]}") for n in names},
            image_files={}, other_files={},
        )
        videos = FakeVideos([
            VideoIndexDoc(path_str=str(root / n), file_hash=f"h_{n[0]}", probe=_probe(root / n, 1.0), stat=stat(root / n))
            for n in names
        ])
        return GalleryService(root_path=root, thumb_path=tmp_path, max_clip_duration=10.0,
                              dirs=FakeDirs([doc]), videos=videos, favorites=favorites)

    old = service(tmp_path / "old")
    page = asyncio.run(old.directory_page("."))
    assert [c.vid_path_rel for c in page.clips] == ["a.mp4", "b.mp4"]

    asyncio.run(FavoriteService(favorites, old.videos).add("h_b"))
    page = asyncio.run(old.directory_page("."))
    assert [(c.vid_path_rel, c.is_favorite) for c in page.clips] == [("b.mp4", True), ("a.mp4", False)]

    # Same content under a different root: the star follows the hash, not the path.
    page = asyncio.run(service(tmp_path / "new").directory_page("."))
    assert [(c.vid_path_rel, c.is_favorite) for c in page.clips] == [("b.mp4", True), ("a.mp4", False)]


def test_favorite_endpoints(client: TestClient):
    r = client.put("/api/favorites/hash_short")
    assert r.status_code == 200 and r.json() == {"file_hash": "hash_short", "is_favorite": True}
    assert client.put("/api/favorites/hash_short").status_code == 200  # idempotent
    client.put("/api/favorites/hash_long")
    assert client.get("/api/favorites").json() == {"paths": ["hash_long", "hash_short"]}
    assert [v["is_favorite"] for v in client.get("/api/directory/.").json()["vids"]] == [True]
    assert "is_favorite" not in client.get("/api/directory/.").json()["images"][0]

    r = client.delete("/api/favorites/hash_long")
    assert r.json() == {"file_hash": "hash_long", "is_favorite": False}
    assert client.get("/api/favorites").json() == {"paths": ["hash_short"]}


def test_favorite_unknown_video_rejected_but_stale_favorite_removable(client: TestClient, favorites: FakeFavorites):
    assert client.put("/api/favorites/hash_nope").status_code == 404
    assert client.put("/api/favorites/..").status_code in (404, 405)
    assert favorites.hashes == []

    favorites.hashes.append("hash_gone")  # video no longer in the index
    assert client.delete("/api/favorites/hash_gone").status_code == 200
    assert favorites.hashes == []


def test_gallery_page_renders_favorite_state(client: TestClient):
    client.put("/api/favorites/hash_long")
    html = client.get("/page/").text
    assert 'data-favorite="true"' in html and 'data-favorite="false"' in html
    assert html.count('class="fav-btn') == 2  # videos only, no image stars


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
