"""
CR3 (Canon Raw version 3) conversion utilities.

This module provides tools for converting CR3 files to standard image formats
like PNG and JPG using various backends.
"""

from __future__ import annotations
from pathlib import Path

# Optional imports - will be checked at runtime
import rawpy
import imageio
import multiprocessing
import tqdm


def convert_cr3_to_png_rawpy(cr3_path: Path, output_path: Path, make_path: bool = False, ignore_if_exists: bool = True) -> None:
    """Convert CR3 to PNG using rawpy."""
    if ignore_if_exists and output_path.exists():
        return
    if make_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    with rawpy.imread(str(cr3_path)) as raw:
        rgb = raw.postprocess()        
        imageio.imwrite(output_path, rgb)

def _convert_cr3_to_png_wrapper(paths: tuple[Path, Path]) -> None:
    cr3_path, output_path = paths
    return convert_cr3_to_png_rawpy(cr3_path, output_path, make_path=True)

def convert_cr3_to_png_folders(cr3_source_path: Path, target_path: Path, num_processes: int = 1, verbose: bool = True) -> None:
    """Convert CR3 to PNG using folder structure."""
    cr3_source_path, target_path = Path(cr3_source_path), Path(target_path)
    
    files_to_convert = list()
    for cr3_file in cr3_source_path.rglob("*.CR3"):
        relative_path = cr3_file.relative_to(cr3_source_path)
        output_file = target_path / relative_path.with_suffix(".png")
        files_to_convert.append((cr3_file, output_file))
    
    if verbose:
        files_to_convert = tqdm.tqdm(files_to_convert, total=len(files_to_convert), desc="Converting CR3 to PNG")

    if num_processes == 1:
        list(map(_convert_cr3_to_png_wrapper, files_to_convert))
    else:
        with multiprocessing.Pool(num_processes) as pool:
            list(pool.map(_convert_cr3_to_png_wrapper, files_to_convert))

    

if __name__ == "__main__":
    convert_cr3_to_png_folders(
        cr3_source_path='/mnt/MoStorage/wedding_photos/all_photos_cr3/', 
        target_path='/mnt/MoStorage/wedding_photos/all_photos_png/', 
        num_processes=10,
        verbose=True,
    )