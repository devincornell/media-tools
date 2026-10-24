from __future__ import annotations

import asyncio
from pathlib import Path

from mediatools.application.media_jobs.locks import PathLocks


async def _never(_: Path) -> None:
    pass


def _run_pair(first: tuple[list[str], bool], second: tuple[list[str], bool]) -> bool:
    '''Return True if `second` acquired while `first` was still held.'''

    async def main() -> bool:
        locks = PathLocks()
        held, release = asyncio.Event(), asyncio.Event()
        got_second = asyncio.Event()

        async def a() -> None:
            async with locks.hold([Path(p) for p in first[0]], exclusive=first[1], on_wait=_never):
                held.set()
                await release.wait()

        async def b() -> None:
            await held.wait()
            async with locks.hold([Path(p) for p in second[0]], exclusive=second[1], on_wait=_never, poll=0.05):
                got_second.set()

        ta, tb = asyncio.create_task(a()), asyncio.create_task(b())
        await held.wait()
        try:
            await asyncio.wait_for(got_second.wait(), 0.3)
            concurrent = True
        except TimeoutError:
            concurrent = False
        release.set()
        await asyncio.wait_for(asyncio.gather(ta, tb), 2)
        assert got_second.is_set()
        return concurrent

    return asyncio.run(main())


def test_disjoint_and_sibling_paths_run_together():
    assert _run_pair((["/r/a"], True), (["/r/b"], True))
    assert _run_pair((["/r/trip"], True), (["/r/trip2"], True))


def test_overlapping_exclusive_waits():
    assert not _run_pair((["/r/a"], True), (["/r/a/sub"], True))
    assert not _run_pair((["/r/a/sub"], True), (["/r"], True))
    assert not _run_pair((["/r/a"], False), (["/r/a"], True))
    assert not _run_pair((["/src", "/r/dest"], True), (["/r"], False))


def test_shared_holders_overlap():
    assert _run_pair((["/r/a"], False), (["/r"], False))


def test_wait_callback_reports_blocker():
    async def main() -> list[Path]:
        locks = PathLocks()
        seen: list[Path] = []

        async def on_wait(p: Path) -> None:
            seen.append(p)

        async with locks.hold([Path("/r/a")], exclusive=True, on_wait=on_wait):
            waiter = asyncio.create_task(_acquire(locks, on_wait))
            await asyncio.sleep(0.1)
        await asyncio.wait_for(waiter, 1)
        return seen

    async def _acquire(locks: PathLocks, on_wait) -> None:  # type: ignore[no-untyped-def]
        async with locks.hold([Path("/r")], exclusive=True, on_wait=on_wait, poll=0.02):
            pass

    seen = asyncio.run(main())
    assert seen and all(p == Path("/r/a") for p in seen)
