import hashlib
from pathlib import Path

def get_hash_hex(file_path: Path, chunk_size: int = 1024, max_chunks: int|None = None) -> str:
    sha256_hash = hashlib.sha256()
    with Path(file_path).open("rb") as f:
        for i, byte_block in enumerate(iter(lambda: f.read(chunk_size), b"")):
            if max_chunks is not None and i >= max_chunks:
                break
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

