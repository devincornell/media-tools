from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UploadFileSpec(_Contract):
    path: Annotated[str, Field(description="Path of the file relative to the destination folder, with `/` separators (folder structure to preserve).")]
    size: Annotated[int, Field(ge=0, description="File size in bytes.")]


class UploadCheckRequest(_Contract):
    dest: Annotated[str, Field(description="Destination folder relative to the gallery root; created if missing.")]
    files: Annotated[list[UploadFileSpec], Field(max_length=2000, description="Files about to be uploaded.")]


class UploadCheckItem(_Contract):
    path: Annotated[str, Field(description="Echo of the checked file's relative path.")]
    state: Annotated[
        Literal["new", "same", "conflict", "invalid"],
        Field(description="`new`: nothing there. `same`: a file of the same size exists. `conflict`: something else exists. `invalid`: the path is not acceptable."),
    ]
    existing_size: Annotated[int | None, Field(description="Size of the existing file, if any.")]
    detail: Annotated[str | None, Field(description="Why the path is invalid or in conflict.")]


class UploadCheckResponse(_Contract):
    items: Annotated[list[UploadCheckItem], Field(description="One entry per requested file, in request order.")]


class UploadResult(_Contract):
    path: Annotated[str, Field(description="Stored path relative to the gallery root.")]
    size: Annotated[int, Field(description="Bytes written.")]
    replaced: Annotated[bool, Field(description="True if an existing file was overwritten.")]
