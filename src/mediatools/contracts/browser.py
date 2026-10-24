from __future__ import annotations

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FolderNode(_Contract):
    '''One indexed folder with recursive size totals.'''

    path: Annotated[str, Field(description="Folder path relative to the gallery root (`.` for the root).")]
    name: Annotated[str, Field(description="Folder name (the root's own name for `.`).")]
    parent: Annotated[str | None, Field(description="`path` of the nearest indexed ancestor, or null for the top folder.")]
    size: Annotated[int, Field(description="Bytes of all indexed files in this folder and its subfolders.")]
    direct_size: Annotated[int, Field(description="Bytes of indexed files directly in this folder.")]
    percent: Annotated[float, Field(description="`size` as a percentage of the whole library (the root's `size`).")]
    files: Annotated[int, Field(description="Indexed files in this folder and its subfolders.")]
    num_videos: Annotated[int, Field(description="Videos directly in this folder.")]
    num_images: Annotated[int, Field(description="Images directly in this folder.")]
    num_other: Annotated[int, Field(description="Other files directly in this folder.")]
    num_subdirs: Annotated[int, Field(description="Direct subfolders recorded in the index.")]


class FolderTree(_Contract):
    '''Every indexed folder, for building a tree view.'''

    total_size: Annotated[int, Field(description="Bytes of all indexed files in the library.")]
    folders: Annotated[list[FolderNode], Field(description="All indexed folders; link them into a tree via `parent`.")]


class FileEntry(_Contract):
    '''One indexed file directly inside a folder.'''

    name: Annotated[str, Field(description="File name.")]
    path: Annotated[str, Field(description="Path relative to the gallery root; also the `/file/{path}` URL suffix.")]
    kind: Annotated[Literal["video", "image", "other"], Field(description="How the indexer classified the file.")]
    size: Annotated[int, Field(description="Size in bytes when indexed.")]
    modified: Annotated[datetime.datetime, Field(description="Modification time when indexed (UTC).")]


class FolderFiles(_Contract):
    '''Files directly inside one folder (subfolders come from FolderTree).'''

    path: Annotated[str, Field(description="Folder path relative to the gallery root.")]
    files: Annotated[list[FileEntry], Field(description="Files sorted by name.")]
