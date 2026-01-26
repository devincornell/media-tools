
import pathlib
import subprocess
import typing
from pathlib import Path
import dataclasses
import tempfile

from .command import execute_subprocess, CommandExecutionResult, CommandExecutionError, CommandTimeoutError, CommandMissingFromPathError


def run_upscale(
    input_file: Path|str,
    output_file: Path|str,
) -> CommandExecutionResult:
    input_file = Path(input_file)
    #output_file = input_file.with_name(input_file.stem + "_upscaled.mp4")

    temp_output_filename = f"_temp_upscaled_{input_file.stem}.mp4"
    temp_output_path = input_file.parent / temp_output_filename

    command = [
        "docker", "run", "--rm",
        "--runtime=nvidia",
        "--gpus", "all",
        "--privileged",
        "-e", "NVIDIA_DRIVER_CAPABILITIES=all",
        "-v", "/usr/share/vulkan/icd.d:/usr/share/vulkan/icd.d:ro",
        "-v", f"{input_file.parent}:/host",
        "ghcr.io/k4yt3x/video2x:latest",
        "-i", f"/host/{input_file.name}",
        "-o", f"/host/{temp_output_filename}",
        "-p", "realesrgan",
        "--realesrgan-model", "realesr-animevideov3",
        "-s", "2", "-d", "0", "--thread-count", "0"
    ]

    with FileCleaner(temp_output_path):
        result = execute_subprocess(command)
        temp_output_path.rename(output_file)
    
    return result


class FileCleaner:
    def __init__(self, path: Path|str):
        self.path = Path(path)

    def __enter__(self) -> Path:
        return self.path
    
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete temporary file {self.path}: {e}")

