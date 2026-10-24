from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from mediatools.application.media_jobs import fileops
from mediatools.application.media_jobs.fileops import MoveOutcome


def _no_link(src: object, dst: object) -> None:
    raise OSError(errno.EXDEV, "Invalid cross-device link")


@pytest.fixture
def cross_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "link", _no_link)


@pytest.mark.parametrize("linkable", [True, False])
def test_move_file_outcomes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linkable: bool):
    if not linkable:
        monkeypatch.setattr(os, "link", _no_link)
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.bin").write_bytes(b"aaaa")
    (src / "same.bin").write_bytes(b"1234")
    (src / "diff.bin").write_bytes(b"1234")
    dst.mkdir()
    (dst / "same.bin").write_bytes(b"5678")
    (dst / "diff.bin").write_bytes(b"12345")

    assert fileops.move_file(src / "a.bin", dst / "nested" / "a.bin", "t") is MoveOutcome.MOVED
    assert fileops.move_file(src / "same.bin", dst / "same.bin", "t") is MoveOutcome.DEDUPLICATED
    assert fileops.move_file(src / "diff.bin", dst / "diff.bin", "t") is MoveOutcome.CONFLICT

    assert (dst / "nested" / "a.bin").read_bytes() == b"aaaa"
    assert (dst / "same.bin").read_bytes() == b"5678"
    assert sorted(p.name for p in src.iterdir()) == ["diff.bin"]
    assert not list(dst.rglob("*.partial"))


def test_failed_copy_leaves_source_and_no_partial(tmp_path: Path, cross_device: None, monkeypatch: pytest.MonkeyPatch):
    src = tmp_path / "a.bin"
    src.write_bytes(b"data")

    def broken_copy(a: object, b: Path) -> None:
        Path(b).write_bytes(b"da")
        raise OSError("disk full")

    monkeypatch.setattr(fileops.shutil, "copyfile", broken_copy)
    with pytest.raises(OSError, match="disk full"):
        fileops.move_file(src, tmp_path / "out" / "a.bin", "t")
    assert src.read_bytes() == b"data"
    assert not (tmp_path / "out" / "a.bin").exists()
    assert not list((tmp_path / "out").glob(".*partial"))


def test_remove_empty_dirs_and_symlinks(tmp_path: Path):
    root = tmp_path / "src"
    (root / "x" / "y").mkdir(parents=True)
    (root / "keep").mkdir()
    (root / "keep" / "f").write_text("f")
    (root / "link").symlink_to(tmp_path)
    files, links = fileops.list_source_files(root)
    assert files == [root / "keep" / "f"] and links == [root / "link"]
    assert fileops.remove_empty_dirs(root) is False
    assert sorted(p.name for p in root.iterdir()) == ["keep", "link"]
    (root / "link").unlink()
    (root / "keep" / "f").unlink()
    assert fileops.remove_empty_dirs(root) is True and root.is_dir()


def test_find_duplicates_keeps_longest_path(tmp_path: Path):
    (tmp_path / "a.mp4").write_bytes(b"same")
    (tmp_path / "a_longer.mp4").write_bytes(b"same")
    (tmp_path / "b.mp4").write_bytes(b"diff")
    pairs = fileops.find_duplicates(sorted(tmp_path.iterdir()))
    assert pairs == [(tmp_path / "a.mp4", tmp_path / "a_longer.mp4")]
