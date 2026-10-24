from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VideoSummary(_Contract):
    '''A single indexed video shown on a directory page.'''

    vid_path_rel: Annotated[str, Field(description="Video path relative to the gallery root; also the `/video/{path}` URL suffix.")]
    thumb_exists: Annotated[bool, Field(description="Whether a GIF thumbnail exists for `hash` under the thumbnail directory.")]
    idx: Annotated[str, Field(description="HTML-safe identifier derived from the file name.")]
    vid_title: Annotated[str, Field(description="Human-readable title derived from the file name.")]
    vid_size: Annotated[int, Field(description="File size in bytes.")]
    vid_size_str: Annotated[str, Field(description="Human-readable file size.")]
    duration: Annotated[float, Field(description="Duration in seconds.")]
    duration_str: Annotated[str, Field(description="Human-readable duration.")]
    res_str: Annotated[str, Field(description="Resolution as `WIDTHxHEIGHT`, or empty if unknown.")]
    aspect: Annotated[float, Field(description="Width divided by height; 1.0 if unknown.")]
    hash: Annotated[str, Field(description="Index hash of the video file; key into the video index and `/thumb/{hash}` URL.")]
    is_clip: Annotated[bool, Field(description="True if the duration is below the server's configured clip threshold.")]
    created_ts: Annotated[float | None, Field(description="Creation time from container tags as a POSIX timestamp, if available.")]
    created: Annotated[str | None, Field(description="Creation time formatted as `YYYY-MM-DD HH:MM:SS`, if available.")]


class ImageSummary(_Contract):
    '''A single indexed image shown on a directory page.'''

    img_path_rel: Annotated[str, Field(description="Image path relative to the gallery root; also the `/file/{path}` URL suffix.")]
    title: Annotated[str, Field(description="Human-readable title derived from the file name.")]
    aspect: Annotated[float, Field(description="Width divided by height; 1.0 if unknown.")]


class SubdirectorySummary(_Contract):
    '''A direct subdirectory of the directory being displayed.'''

    page_path_rel: Annotated[str, Field(description="Subdirectory path relative to the gallery root; also the `/page/{path}` URL suffix.")]
    idx: Annotated[str, Field(description="HTML-safe identifier derived from the directory name.")]
    name: Annotated[str, Field(description="Human-readable directory name.")]
    num_vids: Annotated[int, Field(description="Number of videos directly in this subdirectory.")]
    num_imgs: Annotated[int, Field(description="Number of images directly in this subdirectory.")]
    num_subpages: Annotated[int, Field(description="Number of direct child directories of this subdirectory.")]
    subfolder_thumbs_all: Annotated[list[str], Field(description="Video hashes, recursively under this subdirectory, that have a thumbnail.")]


class DirectoryPage(_Contract):
    '''Everything needed to display one indexed directory.'''

    page_path_rel: Annotated[str, Field(description="Directory path relative to the gallery root (`.` for the root).")]
    idx: Annotated[str, Field(description="HTML-safe identifier derived from the directory name.")]
    name: Annotated[str, Field(description="Human-readable directory name.")]
    files_size_str: Annotated[str, Field(description="Human-readable total size of videos and images directly in this directory.")]
    vids: Annotated[list[VideoSummary], Field(description="Videos in this directory at or above the clip threshold, sorted by name.")]
    clips: Annotated[list[VideoSummary], Field(description="Videos in this directory shorter than the clip threshold, sorted by name.")]
    images: Annotated[list[ImageSummary], Field(description="Images in this directory, sorted by name.")]
    subpages: Annotated[list[SubdirectorySummary], Field(description="Direct subdirectories, sorted by name.")]
    num_vids: Annotated[int, Field(description="Number of indexed videos directly in this directory, including any missing from the video index.")]
    num_imgs: Annotated[int, Field(description="Number of images directly in this directory.")]
    num_subpages: Annotated[int, Field(description="Number of direct subdirectories.")]


class PathList(_Contract):
    '''A list of paths relative to the gallery root.'''

    paths: Annotated[list[str], Field(description="Paths relative to the gallery root.")]


class ErrorResponse(_Contract):
    '''Error body returned by the API for non-2xx responses.'''

    detail: Annotated[str, Field(description="Human-readable error message.")]
