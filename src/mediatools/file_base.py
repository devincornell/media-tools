
from __future__ import annotations
import pathlib
import typing
from pathlib import Path
import shutil
import hashlib
import pydantic

from .file_stat_result import FileStatResult
from .util import multi_extension_glob



class FileBase:
    """Base class for all file types (ImageFile, VideoFile, NonMediaFile)."""
    path: Path
    meta: dict[str, pydantic.JsonValue]
    
    @classmethod
    def from_path(cls,
        path: str | Path,
        check_exists: bool = True,
        meta: dict[str, pydantic.JsonValue] | None = None,
    ) -> typing.Self:
        """Create a file instance from a path."""
        fp = Path(path)
        if check_exists and not fp.exists():
            raise FileNotFoundError(f'The file "{fp}" was not found.')
        return cls(path=fp, meta=meta or {})
    
    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> typing.Self:
        """Create a file instance from a dictionary representation."""
        return cls(
            path=Path(data['path']),  # support both for backward compatibility
            meta=data['meta'],
        )
    
    def to_dict(self) -> dict[str, typing.Any]:
        """Convert to dictionary representation."""
        return {
            'path': str(self.path),
            'meta': self.meta,
        }

    def hash(self, chunk_size: int = 1024, max_chunks: int|None = None, hash_func: typing.Callable = hashlib.sha256) -> str:
        '''Creates a SHA256 hash from the file. Only uses up to max_chunks of chunk_size bytes.'''
        sha256_hash = hash_func()
        with self.path.open("rb") as f:
            for i, byte_block in enumerate(iter(lambda: f.read(chunk_size), b"")):
                if max_chunks is not None and i >= max_chunks:
                    break
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def copy(
        self, 
        new_path: Path, 
        overwrite: bool = False, 
        follow_symlinks: bool = True
    ) -> typing.Self:
        '''Copy the file to a new location.'''
        new_path = Path(new_path)
        if new_path.exists() and not overwrite:
            raise FileExistsError(f'The file "{new_path}" already exists. ')
        shutil.copy2(self.path, new_path, follow_symlinks=follow_symlinks)
        return self.__class__.from_path(new_path, meta=self.meta.copy())

    def move(self, new_path: Path, overwrite: bool = False) -> typing.Self:
        '''Move the file to a new location.'''
        if overwrite:
            self.path.replace(target=new_path)
        else:
            self.path.rename(target=new_path)
        return self.__class__.from_path(new_path, meta=self.meta.copy())

    def size(self) -> int:
        """Get the file size in bytes."""
        return self.path.stat().st_size
    
    def stat(self) -> FileStatResult:
        """Get the file's stat result."""
        return FileStatResult.read_from_path(self.path)

    def exists(self) -> bool:
        """Check if the file exists."""
        return self.path.exists()
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.path}")'



class FileListBase(list[FileBase]):
    '''Collection of file base objects.'''

    @classmethod
    def from_rglob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...],
        base_name_pattern: str = '*',
    ) -> typing.Self:
        raise NotImplementedError()

    @classmethod
    def from_glob(cls, 
        root: str | Path, 
        extensions: typing.Tuple[str, ...],
        base_name_pattern: str = '*',
    ) -> typing.List[typing.Self]:
        raise NotImplementedError()
    
