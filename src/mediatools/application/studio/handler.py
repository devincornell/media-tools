from __future__ import annotations

import asyncio
import collections
import os
import shlex
import time
from pathlib import Path

from ...jobs import JobContext, PermanentJobError
from ...video.ffmpeg import FFMPEGError
from ...video.ffmpeg.core.probe import probe
from ...video.ffmpeg.filtergraph import CompiledGraph
from ..errors import PathOutsideRootError
from ..media_jobs.handlers import Result, _Base
from ..paths import resolve_allowed_source

LOGGED_LINES = 400


def parse_time(value: str) -> float | None:
    '''ffmpeg time duration (`90`, `1.5s`, `500ms`, `01:30`, `00:01:30.5`) in seconds.'''
    value = value.strip()
    try:
        if ":" in value:
            seconds = 0.0
            for part in value.lstrip("-").split(":"):
                seconds = seconds * 60 + float(part)
            return -seconds if value.startswith("-") else seconds
        for suffix, scale in (("ms", 1e-3), ("us", 1e-6), ("s", 1.0)):
            if value.endswith(suffix):
                return float(value[: -len(suffix)]) * scale
        return float(value)
    except ValueError:
        return None


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def compiled_from_params(params: dict) -> CompiledGraph:
    return CompiledGraph.model_validate(
        {**params["compiled"], "ok": True, "filter_complex_pretty": "", "issues": [], "pads": {}, "links": []}
    )


class StudioRenderHandler(_Base):
    '''Runs one compiled studio graph with ffmpeg, writing every output atomically, then indexes the outputs.'''

    async def execute(self, job_id: str, ctx: JobContext) -> str | None:
        record = await self.deps.records.get(job_id)
        if record is None:
            raise PermanentJobError(f"No studio job record for {job_id}", code="missing_record")
        params = record.params
        compiled = compiled_from_params(params)
        inputs: dict[str, Path] = {}
        for node, raw in params["input_paths"].items():  # type: ignore[union-attr]
            try:
                path = resolve_allowed_source(str(raw), (self.deps.root_path, *self.deps.copy_source_roots))
            except PathOutsideRootError as e:
                raise PermanentJobError(str(e), code="invalid_path") from e
            if not path.is_file():
                raise PermanentJobError(f"Input file not found: {raw}", code="not_found")
            inputs[node] = path
        outputs = {node: self._target(str(rel)) for node, rel in params["outputs"].items()}  # type: ignore[union-attr]
        overwrite = bool(params.get("overwrite"))
        for node, path in outputs.items():
            if path.exists() and not overwrite:
                raise PermanentJobError(f"Output already exists: {self._rel(path)}", code="output_exists")
        parents = sorted({p.parent for p in outputs.values()})
        # Renders into one folder may run side by side; only the rescan needs the folder to itself.
        async with self._locked(ctx, parents, exclusive=False):
            result = await self._render(job_id, compiled, inputs, outputs, ctx)
        dirs = sorted({await self._outermost_unindexed(p.parent) for p in outputs.values()})
        dirs = [d for d in dirs if not any(d != o and d.is_relative_to(o) for o in dirs)]
        async with self._locked(ctx, dirs, exclusive=True):
            for i, d in enumerate(dirs):
                ctx.log(f"Rescanning {self._rel(d)}")
                result["reindex"] = await self._reindex(d, ctx, 95 + 5 * i / len(dirs), 95 + 5 * (i + 1) / len(dirs))
        await self.deps.records.set_result(job_id, result)
        return None

    async def _render(
        self, job_id: str, compiled: CompiledGraph, inputs: dict[str, Path], outputs: dict[str, Path], ctx: JobContext,
    ) -> Result:
        for parent in {p.parent for p in outputs.values()}:
            parent.mkdir(parents=True, exist_ok=True)
        tmp = {node: out.with_name(f".{out.stem}.{job_id[:8]}.tmp{out.suffix}") for node, out in outputs.items()}
        expected = await asyncio.to_thread(self._expected_duration, compiled, inputs)
        cmd = compiled.ffmpeg_command(
            {n: str(p) for n, p in inputs.items()}, {n: str(p) for n, p in tmp.items()}, overwrite=True, progress="pipe:1",
        )
        argv = cmd.build_command()
        ctx.log("$ " + " ".join(shlex.quote(a) for a in argv))
        if expected:
            ctx.log(f"Expected output length: about {_fmt(expected)}")
        await ctx.checkpoint(0, "Starting ffmpeg", force=True)
        started = time.monotonic()
        try:
            code, tail = await self._run(argv, expected, ctx)
            if code != 0:
                reason = next((ln for ln in reversed(tail) if ln and not ln.startswith(" ")), f"exit code {code}")
                raise PermanentJobError(f"ffmpeg failed: {reason}", code="ffmpeg_failed")
            for node, path in tmp.items():
                if not path.exists() or path.stat().st_size == 0:
                    raise PermanentJobError(f"ffmpeg wrote nothing to {self._rel(outputs[node])}", code="empty_output")
            for node, path in tmp.items():
                os.replace(path, outputs[node])
        finally:
            for path in tmp.values():
                path.unlink(missing_ok=True)
        elapsed = time.monotonic() - started
        written = [self._rel(p) for p in outputs.values()]
        ctx.log(f"Wrote {', '.join(written)} in {_fmt(elapsed)}")

        result: Result = {
            "outputs": list(written),
            "sizes": {self._rel(p): p.stat().st_size for p in outputs.values()},
            "elapsed_seconds": round(elapsed, 2),
            "expected_seconds": round(expected, 2) if expected else None,
        }
        return result

    @staticmethod
    def _expected_duration(compiled: CompiledGraph, inputs: dict[str, Path]) -> float | None:
        '''Rough output length for progress: the longest (trimmed) input, or their sum for concat.'''
        lengths = []
        for inp in compiled.inputs:
            try:
                length = probe(inputs[inp.node]).duration
            except (FFMPEGError, KeyError, ValueError, TypeError):
                continue
            opts = dict(inp.args)
            if "ss" in opts and (ss := parse_time(opts["ss"])) is not None:
                length = max(0.0, length - ss)
            if "t" in opts and (t := parse_time(opts["t"])) is not None:
                length = min(length, t)
            lengths.append(length)
        if not lengths:
            return None
        total = sum(lengths) if "concat=" in compiled.filter_complex else max(lengths)
        for out in compiled.outputs:
            if (t := parse_time(dict(out.args).get("t", ""))) is not None:
                total = min(total, t)
        return total or None

    async def _run(self, argv: list[str], expected: float | None, ctx: JobContext) -> tuple[int, list[str]]:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        tail: collections.deque[str] = collections.deque(maxlen=40)

        async def read_stderr() -> None:
            assert proc.stderr is not None
            logged = 0
            async for raw in proc.stderr:
                line = raw.decode(errors="replace").rstrip()
                if not line:
                    continue
                tail.append(line)
                if logged < LOGGED_LINES:
                    ctx.log(line)
                    logged += 1
                elif logged == LOGGED_LINES:
                    ctx.log("... (further ffmpeg output omitted)")
                    logged += 1

        stderr_task = asyncio.create_task(read_stderr())
        try:
            assert proc.stdout is not None
            stats: dict[str, str] = {}
            async for raw in proc.stdout:
                key, _, value = raw.decode(errors="replace").strip().partition("=")
                stats[key] = value
                if key != "progress":
                    continue
                done = parse_time(f"{stats.get('out_time_us', '0')}us") or 0.0
                speed = stats.get("speed", "").strip()
                if expected:
                    pct: float | None = min(99.0, 100 * done / expected)
                    stage = f"Rendering {_fmt(done)} / {_fmt(expected)}"
                else:
                    pct, stage = None, f"Rendering {_fmt(done)}"
                await ctx.checkpoint(pct, f"{stage} ({speed})" if speed and speed != "N/A" else stage)
            code = await proc.wait()
            await stderr_task
            return code, list(tail)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            stderr_task.cancel()
