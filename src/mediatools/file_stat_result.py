from __future__ import annotations
from datetime import datetime, timezone
import os
import stat
from pydantic import BaseModel, ConfigDict
from typing import Optional
from typing_extensions import Self # Use typing.Self for Python 3.11+
from .util import format_memory

class FileStatResult(BaseModel):
    # Core attributes
    st_mode: int
    st_ino: int
    st_dev: int
    st_nlink: int
    st_uid: int
    st_gid: int
    st_size: int
    
    # Timestamps (floats)
    st_atime: float
    st_mtime: float
    st_ctime: float
    
    # Nanosecond timestamps (integers)
    st_atime_ns: int
    st_mtime_ns: int
    st_ctime_ns: int
    
    # Platform specific (Optional to avoid crashes on different OS)
    st_blksize: Optional[int] = None
    st_blocks: Optional[int] = None
    st_rdev: Optional[int] = None
    st_birthtime: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def read_from_path(cls, path: str | os.PathLike) -> Self:
        """Factory constructor to build the model from a file path."""
        stat_result = os.stat(path)
        return cls.from_os_stat_result(stat_result)

    @classmethod
    def from_os_stat_result(cls, stat_result: os.stat_result) -> Self:
        """Factory constructor to build the model from an os.stat_result."""
        return cls(
            st_mode=stat_result.st_mode,
            st_ino=stat_result.st_ino,
            st_dev=stat_result.st_dev,
            st_nlink=stat_result.st_nlink,
            st_uid=stat_result.st_uid,
            st_gid=stat_result.st_gid,
            st_size=stat_result.st_size,
            st_atime=stat_result.st_atime,
            st_mtime=stat_result.st_mtime,
            st_ctime=stat_result.st_ctime,
            st_atime_ns=stat_result.st_atime_ns,
            st_mtime_ns=stat_result.st_mtime_ns,
            st_ctime_ns=stat_result.st_ctime_ns,
            # Use getattr for platform-specific fields to prevent AttributeErrors
            st_blksize=getattr(stat_result, 'st_blksize', None),
            st_blocks=getattr(stat_result, 'st_blocks', None),
            st_rdev=getattr(stat_result, 'st_rdev', None),
            st_birthtime=getattr(stat_result, 'st_birthtime', None),
        )

    @property
    def modified_at(self) -> datetime:
        """Returns the modification time as a UTC datetime object."""
        return datetime.fromtimestamp(self.st_mtime, tz=timezone.utc)

    @property
    def accessed_at(self) -> datetime:
        """Returns the last access time as a UTC datetime object."""
        return datetime.fromtimestamp(self.st_atime, tz=timezone.utc)

    @property
    def changed_at(self) -> datetime:
        """Returns the metadata change time (Unix) or creation time (Win)."""
        return datetime.fromtimestamp(self.st_ctime, tz=timezone.utc)

    def size_str(self) -> str:
        '''Get the size of the video file in bytes.'''
        return format_memory(self.st_size)

    @property
    def size(self) -> int:
        '''Get the size of the video file in bytes.'''
        return self.st_size


    # --- Mimicking os.stat_result methods/behaviors ---
    def is_dir(self) -> bool:
        """Check if the path is a directory."""
        return stat.S_ISDIR(self.st_mode)

    def is_reg(self) -> bool:
        """Check if the path is a regular file."""
        return stat.S_ISREG(self.st_mode)

    def is_symlink(self) -> bool:
        """Check if the path is a symbolic link."""
        return stat.S_ISLNK(self.st_mode)

    def get_permissions(self) -> str:
        """Returns the octal permission string (e.g., '0o644')."""
        return oct(stat.S_IMODE(self.st_mode))
    
