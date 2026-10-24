from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from mediatools.application import (
    InvalidJobRequestError,
    MediaFileNotFoundError,
    PathOutsideRootError,
)
from mediatools.application.folder_picker import FolderPicker
from mediatools.application.media_jobs import fileops

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="permission checks are meaningless as root")


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    gallery, incoming, outside = tmp_path / "gallery", tmp_path / "incoming", tmp_path / "outside"
    for d in (gallery / "trips" / "italy", gallery / ".hidden", incoming / "batch" / "sub", incoming / "locked" / "inner", outside):
        d.mkdir(parents=True)
    (gallery / "trips" / "a.mp4").write_bytes(b"x")
    (incoming / "batch" / "f1").write_bytes(b"1")
    (incoming / "batch" / "f2").write_bytes(b"2")
    (incoming / "escape").symlink_to(outside)
    (incoming / "locked").chmod(0o555)
    yield {"gallery": gallery, "incoming": incoming, "outside": outside}
    (incoming / "locked").chmod(0o755)


def listing(picker: FolderPicker, scope: str, path: str | None = None):  # type: ignore[no-untyped-def]
    return asyncio.run(picker.list(scope, path))  # type: ignore[arg-type]


def test_gallery_scope(layout: dict[str, Path]):
    picker = FolderPicker(layout["gallery"], (layout["incoming"],))
    root = listing(picker, "gallery")
    assert root.path == str(layout["gallery"]) and root.parent is None and root.rel == "."
    assert [d.name for d in root.dirs] == [".hidden", "trips"]
    trips = next(d for d in root.dirs if d.name == "trips")
    assert (trips.rel, trips.num_files, trips.has_subdirs, trips.writable) == ("trips", 1, True, True)
    italy = listing(picker, "gallery", str(layout["gallery"] / "trips" / "italy"))
    assert italy.parent == str(layout["gallery"] / "trips") and italy.rel == "trips/italy"


def test_source_scope_hides_escaping_symlinks_and_reports_permissions(layout: dict[str, Path]):
    picker = FolderPicker(layout["gallery"], (layout["incoming"],))
    src = listing(picker, "source")
    by_name = {d.name: d for d in src.dirs}
    assert set(by_name) == {"batch", "locked"}  # "escape" points outside every root
    assert by_name["batch"].rel is None and by_name["batch"].num_files == 2
    assert by_name["locked"].writable is False and by_name["locked"].readable is True


def test_paths_outside_roots_are_rejected(layout: dict[str, Path]):
    picker = FolderPicker(layout["gallery"], (layout["incoming"],))
    for scope, path in [("gallery", str(layout["incoming"])), ("source", str(layout["outside"])),
                        ("source", str(layout["incoming"] / "escape")), ("gallery", str(layout["gallery"] / ".."))]:
        with pytest.raises(PathOutsideRootError):
            listing(picker, scope, path)
    with pytest.raises(MediaFileNotFoundError):
        listing(picker, "gallery", str(layout["gallery"] / "nope"))
    with pytest.raises(InvalidJobRequestError):
        listing(FolderPicker(layout["gallery"], ()), "source")


def test_unwritable_dirs_and_message(layout: dict[str, Path]):
    incoming = layout["incoming"]
    assert fileops.unwritable_dirs(incoming / "batch") == []
    blocked = fileops.unwritable_dirs(incoming)
    assert blocked == [incoming / "locked"]
    msg = fileops.permission_message(incoming, blocked)
    assert "can't delete files in 1 source folder" in msg and f"sudo chown -R {fileops.user_name(os.getuid())} '{incoming}'" in msg
