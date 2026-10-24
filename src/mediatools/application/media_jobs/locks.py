from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path


@dataclasses.dataclass(eq=False)
class _Hold:
    paths: tuple[Path, ...]
    exclusive: bool


def _overlaps(a: Path, b: Path) -> bool:
    return a.is_relative_to(b) or b.is_relative_to(a)


class PathLocks:
    '''Reader/writer locks over directory trees, shared by the jobs running in one worker process.

    Shared holders of overlapping trees run together; an exclusive holder waits for every overlapping holder.
    '''

    def __init__(self) -> None:
        self._held: list[_Hold] = []
        self._changed = asyncio.Condition()

    def _blocker(self, want: _Hold) -> Path | None:
        for hold in self._held:
            if want.exclusive or hold.exclusive:
                for p in want.paths:
                    for q in hold.paths:
                        if _overlaps(p, q):
                            return q
        return None

    @contextlib.asynccontextmanager
    async def hold(
        self,
        paths: Sequence[Path],
        *,
        exclusive: bool,
        on_wait: Callable[[Path], Awaitable[None]],
        poll: float = 5.0,
    ) -> AsyncIterator[None]:
        '''Hold `paths`; while blocked, `on_wait(blocking_path)` is awaited every `poll` seconds.'''
        want = _Hold(tuple(paths), exclusive)
        async with self._changed:
            while (blocker := self._blocker(want)) is not None:
                await on_wait(blocker)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._changed.wait(), poll)
            self._held.append(want)
        try:
            yield
        finally:
            async with self._changed:
                self._held.remove(want)
                self._changed.notify_all()
