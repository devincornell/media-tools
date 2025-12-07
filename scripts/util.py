import typing
import hashlib
import multiprocessing
import tqdm
from pathlib import Path

T = typing.TypeVar('T')
R = typing.TypeVar('R')



def get_hash_hex_THUMB(vid_path_abs: Path) -> str:
    '''Creates a hash from first 1000 kb chunks. Used for thumbnails filenames.'''
    return get_hash_hex(vid_path_abs, max_chunks=1000)

def get_hash_hex(file_path: Path, chunk_size: int = 1024, max_chunks: int|None = None) -> str:
    '''Creates a SHA256 hash from the file. Only uses up to max_chunks of chunk_size bytes.'''
    sha256_hash = hashlib.sha256()
    with Path(file_path).open("rb") as f:
        for i, byte_block in enumerate(iter(lambda: f.read(chunk_size), b"")):
            if max_chunks is not None and i >= max_chunks:
                break
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def parallel_map(
    func: typing.Callable[[T], R], 
    elements: list[T], 
    num_processes: int = 1, 
    use_tqdm: bool = False
) -> list[R]:
    '''Map function in parallel using multiprocessing.'''
    if use_tqdm:
        elements = tqdm.tqdm(elements, total=len(elements))
    if num_processes == 1:
        return list(map(func, elements))
    else:
        with multiprocessing.Pool(num_processes) as pool:
            return list(pool.map(func, elements))
        
def parallel_starmap(
    func: typing.Callable[..., R],
    elements: list[tuple[typing.Any, ...]], 
    num_processes: int = 1, 
    use_tqdm: bool = False
) -> list[R]:
    '''Map function in parallel using multiprocessing.'''
    if use_tqdm:
        elements = tqdm.tqdm(elements, total=len(elements))
    if num_processes == 1:
        return [func(*e) for e in elements]
    else:
        with multiprocessing.Pool(num_processes) as pool:
            return list(pool.starmap(func, elements))