from datetime import datetime
from pydantic import BaseModel, Field
import typing
import os


class FileStatInfo(BaseModel):
    """Commonly used attributes from a file stat call."""
    size: int = Field(..., description="Size of the file in bytes")
    
    # Timestamps
    modified_at: datetime = Field(..., )
    accessed_at: datetime = Field(...)
    created_at: datetime = Field(...)
    
    # System identifiers
    mode: int = Field(..., description="File protection mode")
    inode: int = Field(..., description="Inode number")

    @classmethod
    def from_file_stat(cls, stat: os.stat_result) -> typing.Self:        
        return cls(
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            accessed_at=datetime.fromtimestamp(stat.st_atime),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            mode=stat.st_mode,
            inode=stat.st_ino,
        )
