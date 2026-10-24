from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from mediatools.application.media_jobs import fileops
from mediatools.application.media_jobs.fileops import MoveOutcome


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    '''Record every command move_file runs (while still running it).'''
    seen: list[list[str]] = []
    real = fileops.run_command

    def spy(argv: list[str], tolerate: str | None = None) -> None:
        seen.append(list(argv))
        real(argv, tolerate)

    monkeypatch.setattr(fileops, "run_command", spy)
    return seen


@pytest.fixture(params=["same_filesystem", "cross_filesystem"])
def device_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    if request.param == "cross_filesystem":
        monkeypatch.setattr(fileops, "same_device", lambda a, b: False)
    return request.param


def test_move_file_outcomes(tmp_path: Path, device_mode: str, commands: list[list[str]]):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.bin").write_bytes(b"aaaa")
    (src / "same.bin").write_bytes(b"1234")
    (src / "diff.bin").write_bytes(b"1234")
    dst.mkdir()
    (dst / "same.bin").write_bytes(b"5678")
    (dst / "diff.bin").write_bytes(b"12345")

    assert fileops.move_file(src / "a.bin", dst / "nested" / "a.bin", "t").outcome is MoveOutcome.MOVED
    moved_commands = [c[0] for c in commands]
    assert moved_commands == (["mv"] if device_mode == "same_filesystem" else ["cp", "mv", "rm"])
    assert fileops.move_file(src / "same.bin", dst / "same.bin", "t").outcome is MoveOutcome.DEDUPLICATED
    assert commands[-1][:3] == ["rm", "-f", "--"]  # the source is removed with rm
    assert fileops.move_file(src / "diff.bin", dst / "diff.bin", "t").outcome is MoveOutcome.CONFLICT

    assert (dst / "nested" / "a.bin").read_bytes() == b"aaaa"
    assert (dst / "same.bin").read_bytes() == b"5678"
    assert sorted(p.name for p in src.iterdir()) == ["diff.bin"]
    assert not list(dst.rglob("*.partial"))


@pytest.mark.parametrize("name", [
    "-rf", "--help", "a b.txt", "semi;colon.txt", "$(touch pwned).txt", "`id`.txt", "quote'\"s.txt",
    "star*glob?.txt", "new\nline.txt", "caf\u00e9 \U0001f600.txt", "~tilde", "-",
])
def test_hostile_file_names_are_not_interpreted(tmp_path: Path, device_mode: str, name: str):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / name).write_bytes(b"payload")
    os.utime(src / name, (1_700_000_000, 1_700_000_000))
    sibling = src / "innocent.txt"
    sibling.write_bytes(b"keep")

    assert fileops.move_file(src / name, dst / "sub" / name, "t").outcome is MoveOutcome.MOVED
    assert (dst / "sub" / name).read_bytes() == b"payload"
    assert int((dst / "sub" / name).stat().st_mtime) == 1_700_000_000  # timestamps survive
    assert not (src / name).exists() and sibling.read_bytes() == b"keep"
    assert sorted(p.name for p in dst.rglob("*") if p.is_file()) == [name]
    assert not (tmp_path / "pwned").exists() and not Path("pwned").exists()


def test_failed_copy_leaves_source_and_no_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fileops, "same_device", lambda a, b: False)
    src = tmp_path / "a.bin"
    src.write_bytes(b"data")
    real = fileops.run_command

    def broken_cp(argv: list[str], tolerate: str | None = None) -> None:
        if argv[0] == "cp":
            Path(argv[-1]).write_bytes(b"da")  # a truncated copy
            raise OSError(errno.ENOSPC, "No space left on device")
        real(argv, tolerate)

    monkeypatch.setattr(fileops, "run_command", broken_cp)
    with pytest.raises(OSError, match="No space"):
        fileops.move_file(src, tmp_path / "out" / "a.bin", "t")
    assert src.read_bytes() == b"data"
    assert not (tmp_path / "out" / "a.bin").exists()
    assert not list((tmp_path / "out").glob(".*partial"))


def test_truncated_copy_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fileops, "same_device", lambda a, b: False)
    src = tmp_path / "a.bin"
    src.write_bytes(b"data")
    real = fileops.run_command

    def short_cp(argv: list[str], tolerate: str | None = None) -> None:
        if argv[0] == "cp":
            Path(argv[-1]).write_bytes(b"da")  # cp "succeeds" but wrote too little
            return
        real(argv, tolerate)

    monkeypatch.setattr(fileops, "run_command", short_cp)
    with pytest.raises(OSError, match="Size mismatch"):
        fileops.move_file(src, tmp_path / "out" / "a.bin", "t")
    assert src.read_bytes() == b"data" and not (tmp_path / "out" / "a.bin").exists()
    assert not list((tmp_path / "out").glob(".*partial"))


def test_destination_appearing_mid_move_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fileops, "same_device", lambda a, b: False)
    src, dst = tmp_path / "a.bin", tmp_path / "out" / "a.bin"
    src.write_bytes(b"data")
    real = fileops.run_command

    def racing(argv: list[str], tolerate: str | None = None) -> None:
        real(argv, tolerate)
        if argv[0] == "cp":  # someone else creates the destination after the copy finished
            dst.write_bytes(b"theirs-different-size")

    monkeypatch.setattr(fileops, "run_command", racing)
    assert fileops.move_file(src, dst, "t").outcome is MoveOutcome.CONFLICT
    assert dst.read_bytes() == b"theirs-different-size" and src.read_bytes() == b"data"
    assert not list(dst.parent.glob(".*partial"))


@pytest.mark.skipif(not Path("/dev/shm").is_dir(), reason="needs a second filesystem")
def test_real_cross_filesystem_move(tmp_path: Path, commands: list[list[str]]):
    import tempfile

    with tempfile.TemporaryDirectory(dir="/dev/shm") as shm:
        src = Path(shm) / "big file (1).bin"
        src.write_bytes(os.urandom(3_000_000))
        os.utime(src, (1_700_000_000, 1_700_000_000))
        expected = src.read_bytes()
        if src.stat().st_dev == tmp_path.stat().st_dev:
            pytest.skip("/dev/shm and tmp are the same filesystem here")

        assert fileops.move_file(src, tmp_path / "dest" / src.name, "t").outcome is MoveOutcome.MOVED
        assert [c[0] for c in commands] == ["cp", "mv", "rm"]  # a real copy, not a rename
        assert (tmp_path / "dest" / src.name).read_bytes() == expected
        assert int((tmp_path / "dest" / src.name).stat().st_mtime) == 1_700_000_000
        assert not src.exists() and not list((tmp_path / "dest").glob(".*partial"))


def test_run_command_errors(tmp_path: Path):
    with pytest.raises(PermissionError):
        locked = tmp_path / "locked"
        locked.mkdir()
        (tmp_path / "f").write_text("x")
        locked.chmod(0o555)
        try:
            if os.geteuid() == 0:
                raise PermissionError  # root ignores modes
            fileops.run_command(["cp", "--", str(tmp_path / "f"), str(locked / "f")])
        finally:
            locked.chmod(0o755)
    with pytest.raises(OSError, match="cp failed"):
        fileops.run_command(["cp", "--", str(tmp_path / "missing"), str(tmp_path / "x")])


def test_conflicting_files_are_renamed_not_left_behind(tmp_path: Path, device_mode: str):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (dst / "clip.mp4").write_bytes(b"theirs!")
    (dst / "clip (1).mp4").write_bytes(b"also theirs")  # the first free name is (2)
    (dst / "notes").mkdir()  # a folder in the way of a file
    for name, data in [("clip.mp4", b"mine"), ("notes", b"a file"), (".hidden", b"h")]:
        (src / name).write_bytes(data)
    (dst / ".hidden").write_bytes(b"theirs-hidden")

    r1 = fileops.move_file(src / "clip.mp4", dst / "clip.mp4", "t", rename_on_conflict=True)
    r2 = fileops.move_file(src / "notes", dst / "notes", "t", rename_on_conflict=True)
    r3 = fileops.move_file(src / ".hidden", dst / ".hidden", "t", rename_on_conflict=True)
    assert [(r.outcome, r.path.name) for r in (r1, r2, r3)] == [
        (MoveOutcome.RENAMED, "clip (2).mp4"), (MoveOutcome.RENAMED, "notes (1)"), (MoveOutcome.RENAMED, ".hidden (1)"),
    ]
    assert (dst / "clip.mp4").read_bytes() == b"theirs!" and (dst / "clip (2).mp4").read_bytes() == b"mine"
    assert (dst / "notes (1)").read_bytes() == b"a file" and list(src.iterdir()) == []

    # Repeating the move after an interruption must not create yet another copy.
    (src / "clip.mp4").write_bytes(b"mine")
    again = fileops.move_file(src / "clip.mp4", dst / "clip.mp4", "t", rename_on_conflict=True)
    assert (again.outcome, again.path.name) == (MoveOutcome.DEDUPLICATED, "clip (2).mp4")
    assert not (dst / "clip (3).mp4").exists() and list(src.iterdir()) == []


@pytest.mark.parametrize("cross", [False, True])
def test_move_entry_moves_links_as_links(tmp_path: Path, cross: bool):
    import tempfile

    if cross and not Path("/dev/shm").is_dir():
        pytest.skip("needs a second filesystem")
    with tempfile.TemporaryDirectory(dir="/dev/shm" if cross else tmp_path) as base_dir:
        base = Path(base_dir)
        if cross and base.stat().st_dev == tmp_path.stat().st_dev:
            pytest.skip("same filesystem here")
        target = tmp_path / "elsewhere"
        target.mkdir()
        (target / "precious").write_text("do not touch")
        link_to_dir, link_dangling = base / "dirlink", base / "dangling"
        link_to_dir.symlink_to(target)
        link_dangling.symlink_to("/no/such/place")
        dst = tmp_path / "dest"
        dst.mkdir()
        (dst / "dirlink").write_text("name taken")

        a = fileops.move_entry(link_to_dir, dst / "dirlink")
        b = fileops.move_entry(link_dangling, dst / "sub" / "dangling")
        assert (a.outcome, a.path.name) == (MoveOutcome.RENAMED, "dirlink (1)")
        assert b.outcome is MoveOutcome.MOVED
        assert (dst / "dirlink (1)").is_symlink() and os.readlink(dst / "dirlink (1)") == str(target)
        assert os.readlink(dst / "sub" / "dangling") == "/no/such/place"
        assert not os.path.lexists(link_to_dir) and not os.path.lexists(link_dangling)
        assert (target / "precious").read_text() == "do not touch"  # the link target was never followed


def test_list_source_files_separates_links_and_specials(tmp_path: Path):
    root = tmp_path / "src"
    (root / "d").mkdir(parents=True)
    (root / "d" / "f").write_text("f")
    (root / "link").symlink_to(tmp_path)
    (root / "d" / "filelink").symlink_to(root / "d" / "f")
    os.mkfifo(root / "pipe")
    files, others = fileops.list_source_files(root)
    assert files == [root / "d" / "f"]
    assert sorted(p.name for p in others) == ["filelink", "link", "pipe"]


def test_remove_source_tree(tmp_path: Path):
    root = tmp_path / "src"
    (root / "x" / "y").mkdir(parents=True)
    (root / "z").mkdir()
    assert fileops.remove_source_tree(root) == [] and not root.exists()  # empty folders and the root itself go

    (root / "x").mkdir(parents=True)
    (root / "x" / "left.txt").write_text("still here")
    (root / "empty").mkdir()
    remaining = fileops.remove_source_tree(root)
    assert remaining == [root / "x" / "left.txt"] and (root / "x" / "left.txt").exists()
    assert not (root / "empty").exists()


def test_remove_source_tree_removes_symlinked_source_and_its_target(tmp_path: Path):
    real = tmp_path / "real"
    (real / "sub").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real)
    assert fileops.remove_source_tree(link) == []
    assert not os.path.lexists(link) and not real.exists()

    real.mkdir()
    (real / "keep").write_text("x")
    link.symlink_to(real)
    assert fileops.remove_source_tree(link) == [real / "keep"]
    assert link.is_symlink() and real.exists()  # nothing is removed while content remains


def test_is_protected_root(tmp_path: Path):
    root, other = tmp_path / "incoming", tmp_path / "other"
    (root / "batch").mkdir(parents=True)
    other.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    assert fileops.is_protected_root(root, [root]) and fileops.is_protected_root(alias, [root])
    assert fileops.is_protected_root(root / ".." / "incoming", [root])
    assert not fileops.is_protected_root(root / "batch", [root]) and not fileops.is_protected_root(other, [root])


def test_find_duplicates_keeps_longest_path(tmp_path: Path):
    (tmp_path / "a.mp4").write_bytes(b"same")
    (tmp_path / "a_longer.mp4").write_bytes(b"same")
    (tmp_path / "b.mp4").write_bytes(b"diff")
    pairs = fileops.find_duplicates(sorted(tmp_path.iterdir()))
    assert pairs == [(tmp_path / "a.mp4", tmp_path / "a_longer.mp4")]
