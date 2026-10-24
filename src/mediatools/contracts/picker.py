from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PickerScope = Literal["gallery", "source"]


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PickerRoot(_Contract):
    scope: Annotated[PickerScope, Field(description="`gallery` for paths inside the gallery root, `source` for move sources.")]
    path: Annotated[str, Field(description="Absolute path of the root.")]


class PickerDir(_Contract):
    '''A subfolder shown in the folder picker.'''

    name: Annotated[str, Field(description="Folder name.")]
    path: Annotated[str, Field(description="Absolute path.")]
    rel: Annotated[str | None, Field(description="Path relative to the gallery root, or null if outside it.")]
    readable: Annotated[bool, Field(description="Whether the server can list this folder.")]
    is_symlink: Annotated[bool, Field(description="Whether this entry is a symbolic link to a folder (it is followed).")]
    link_target: Annotated[str | None, Field(description="Where the symbolic link points, if `is_symlink`.")]
    writable: Annotated[bool, Field(description="Whether the server can create and delete entries in this folder.")]
    owner: Annotated[str, Field(description="Owning user.")]
    num_files: Annotated[int, Field(description="Files directly inside (capped; see `more_files`).")]
    more_files: Annotated[bool, Field(description="True if counting stopped at the cap.")]
    has_subdirs: Annotated[bool, Field(description="Whether it contains subfolders.")]


class PickerListing(_Contract):
    '''One folder's subfolders, read live from disk.'''

    scope: Annotated[PickerScope, Field(description="Scope the listing was requested for.")]
    root: Annotated[str, Field(description="Absolute path of the scope root containing `path`.")]
    path: Annotated[str, Field(description="Absolute path of the listed folder.")]
    rel: Annotated[str | None, Field(description="`path` relative to the gallery root, or null if outside it.")]
    parent: Annotated[str | None, Field(description="Absolute path of the parent, or null at the scope root.")]
    writable: Annotated[bool, Field(description="Whether the server can create and delete entries in `path`.")]
    owner: Annotated[str, Field(description="Owning user of `path`.")]
    num_files: Annotated[int, Field(description="Files directly inside `path` (capped).")]
    dirs: Annotated[list[PickerDir], Field(description="Subfolders sorted by name.")]
