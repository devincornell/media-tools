"""Write OpenCV (BGR uint8) frames to a widely playable H.264 MP4 through ffmpeg.

OpenCV's pip build can only write MPEG-4 Part 2 ("mp4v"), which browsers, QuickTime and
most built-in players reject. This pipes raw frames into ffmpeg/libx264 instead, producing
yuv420p H.264 with the index at the front of the file (faststart).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

# Most hardware H.264 decoders cannot play frames wider than about 4096 pixels.
DEFAULT_MAX_WIDTH = 3840


class H264Writer:
    """Encode frames with `writer.write(frame)`; call `close()` (e.g. in `finally`) to finish.

    Frames must all be `size` (width, height). Output wider than `max_width` is scaled
    down with its aspect ratio kept, and dimensions are rounded to even numbers as
    yuv420p requires. Closing after an error still leaves a playable partial file.
    """

    def __init__(
        self,
        output: Path,
        fps: float,
        size: tuple[int, int],
        crf: int = 20,
        preset: str = "fast",
        max_width: int = DEFAULT_MAX_WIDTH,
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg not found on PATH; it is needed to encode H.264 output")
        self._output = output
        self._shape = (size[1], size[0], 3)
        # Quotes protect the comma inside min() from the filtergraph parser.
        scale = f"scale='min({max_width // 2 * 2},trunc(iw/2)*2)':-2"
        command = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}", "-framerate", f"{fps:.6f}",
            "-i", "-",
            "-vf", scale,
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]  # fmt: skip
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        if frame.shape != self._shape or frame.dtype != np.uint8:
            raise ValueError(f"expected a {self._shape} uint8 frame, got {frame.shape} {frame.dtype}")
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(np.ascontiguousarray(frame).tobytes())
        except BrokenPipeError as e:
            raise RuntimeError(f"ffmpeg exited early while writing {self._output}") from e

    def close(self) -> None:
        if self._process.stdin is not None and not self._process.stdin.closed:
            try:
                self._process.stdin.close()
            except BrokenPipeError:
                pass
        code = self._process.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg failed with exit code {code} while writing {self._output}")
