# MediaTools
This package contains tools for working with video and image files.

### Install

```bash
pip install git+ssh://git@github.com:devincornell/media-tools.git@main
```

```python
import mediatools
```


## Gallery server

`apps/api/` is a FastAPI app that serves an indexed media directory (see `mediatools.index_db`). It is not part of the installed package. Configure it with `SITE_*` environment variables or a `.env` file in the repo root:

| Variable | Required | Description |
|---|---|---|
| `SITE_ROOT_PATH` | yes | Media root. Must match the absolute paths stored in the index. |
| `SITE_THUMB_PATH` | yes | Directory of `<hash>.gif` thumbnails. |
| `SITE_MONGODB_URL` | yes | MongoDB connection URL. |
| `SITE_DATABASE_NAME` | yes | MongoDB database holding the index. |
| `SITE_PORT` | no | Port for `python -m apps.api` and the Compose host port (default 8000). |
| `SITE_MAX_CLIP_DURATION` | no | Videos shorter than this many seconds are listed as clips (default 0). |
| `SITE_COPY_SOURCE_ROOTS` | no | JSON list of directories move jobs may read from, e.g. `'["/mnt/incoming"]'`. Empty (default) disables move jobs. |
| `SITE_RUN_WORKER` | no | Run the job worker inside the server process (default `true`). |
| `SITE_WORKER_CONCURRENCY` | no | Jobs one worker runs at once (default 4). |
| `SITE_JOB_LEASE_SECONDS` | no | How long a job stays claimed without a heartbeat before another worker may resume it (default 60). |

Run locally from the repo root:

```bash
uv run --group api uvicorn apps.api.main:app --reload
# or, with CLI overrides of the SITE_* settings:
uv run --group api python -m apps.api --root-path /path/to/media -p 8000
```

Run in Docker (reads `SITE_*` from `.env`; runs as UID/GID 1000 by default, set `UID`/`GID` to match the owner of your media):

```bash
docker compose up -d --build
```

Browse `/page/`, `/reel/`, `/browse` (a Finder-style tree of every indexed folder and file, with each folder's recursive size and share of the library), or the JSON API under `/api` (docs at `/docs`). A typed client is available with the `client` extra:

```python
from mediatools.client import GalleryClient

with GalleryClient("http://localhost:8000") as client:
    page = client.get_directory("some/subdir")
```

Tests: `uv run --group api --extra client pytest tests/test_api.py tests/test_fileops.py`.

### Uploading

`/upload` sends files or whole folders from your browser into the gallery. Choose or drop one or more folders (or individual files); each file is stored at `<destination>/<its relative path>`, so folder structure is preserved exactly. Folders are created as needed, but empty folders are not (browsers don't expose them).

- **Large batches:** files are sent one request each with a few in parallel, streamed straight to disk under a temporary name and renamed into place only when complete, so a cancelled or dropped upload never leaves a partial file. Modification times are kept.
- **Resuming:** before uploading, the page asks the server which files already exist. Files with the same size are skipped, so repeating an interrupted upload picks up where it stopped. Files that exist with a different size are skipped or replaced, as you choose.
- **After uploading:** optionally queues a rescan (and thumbnail generation) of the destination.
- Paths are validated on the server (no absolute paths, `..`, or control characters) and can only land inside the gallery root. API: `POST /api/uploads/check` and `PUT /api/uploads/file?dest=…&path=…`.
- Like everything else, uploads are unauthenticated: anyone who can reach the server can write files into the gallery.

### Jobs

Long-running maintenance runs as background jobs, tracked in MongoDB, viewable and startable at `/jobs` (the sync icon in the gallery sidebar opens it for the current folder). Each job targets one directory, so subdirectories can be processed independently:

| Task | What it does |
|---|---|
| Rescan | Re-indexes a directory tree: updates changed folders, removes deleted ones, probes new videos. |
| Thumbnails | Creates missing animated GIF thumbnails (optionally regenerates all). |
| Cleanup | Finds empty, unprobable, or same-folder duplicate videos. **Dry run by default**; turn it off to delete, after which the folder is rescanned. |
| Convert to MP4 | Converts other video formats to MP4 next to the originals, then rescans. |
| Move + rescan | Moves a directory (from a `SITE_COPY_SOURCE_ROOTS` location) into the gallery in parallel, then rescans the destination. **The source folder is guaranteed to be gone afterwards**, or the job fails and says what is left. A file already at the destination with the same size is treated as the same file and just removed from the source; a file whose name clashes with a *different* file is kept under a numbered name (`clip (1).mp4`) rather than skipped. Symlinks and special files are moved as themselves, never followed (a relative link may then point elsewhere). Empty subfolders and the source folder itself are removed (for a symlinked source, the link and the folder behind it). The transfer is done by `mv` (a rename on the same filesystem) or, across filesystems, `cp -p --reflink=auto` to a temporary name, a size check, `mv` into place and `rm` of the source; commands run without a shell, so file names are never interpreted. If something cannot be moved (for example, a file sits where a destination folder must go, or the disk fills up), the job is retried and then fails, leaving only those entries. The server user must be able to delete files in every source folder; if it can't, the move is refused before anything is copied, with the `chown` command to fix it. A copy source root itself can't be a source, since removing it would stop the server from starting. |

Every path field on the jobs page has a **Browse…** button that opens a folder picker. It lists folders live from disk, but only inside the gallery root (for targets and destinations) or the copy source roots (for move sources), and marks folders the server can't write to. Symbolic links to folders are followed and shown with a link icon, even when they point outside those roots, so a symlink you place inside a copy source root makes its target movable. Links inside a move source are still skipped, never followed.

Jobs survive restarts: an interrupted job is resumed by the next worker once its lease expires, and every handler skips work that is already done. Cancelling stops a running job at its next checkpoint.

Jobs run in parallel (`SITE_WORKER_CONCURRENCY`, default 4). Jobs that change the index or files (rescan, convert, move, and cleanup with deletes) wait for any other job in the same worker that touches an overlapping folder (the same folder, a parent, or a child). Thumbnails and dry-run cleanups only read, so they run alongside each other. Each job writes a live log (the per-directory output of a rescan, every file moved, and so on), shown under **Details** and available at `GET /v1/jobs/{id}/logs`. Logs are kept for 30 days.

To run jobs outside the web server, start the server with `--no-worker` (or `SITE_RUN_WORKER=false`) and run `make worker` / `uv run --group api python -m apps.worker`. The standalone worker reads its settings from `SITE_*` / `.env` only. HTTP API: `POST /api/jobs/{reindex,thumbnails,cleanup,convert-mp4,move,move-item}` returns `202` with a job ID; poll `GET /v1/jobs/{id}`; list with `GET /v1/jobs` or `GET /api/media-jobs`; cancel with `POST /v1/jobs/{id}/cancel`.

The server has no authentication. Anyone who can reach it can start jobs, including deletes. Keep it on a trusted network.

Job tests need a disposable MongoDB (never a real one): `make test_mongo_up && make test_jobs && make test_mongo_down`.


## API Overview

Currently, the package provides tools for working with video and image files.

+ **Video files**: process videos using [ffmpeg-python](https://github.com/kkroening/ffmpeg-python).
    + Compress
    + Splice
    + Crop
    + Create thumbnails

+ **Image files**: interface for manipulating images using [skimage](https://scikit-image.org/).
    + Convert between GS/RGB/RGBA
    + Compute filter functions
    + Execute distance metrics
    + Crop
    + Resize

### Working with Videos

First create a `VideoFile` object from a file path.

```python
vf = mediatools.VideoFile.from_path('my_video.mp4)
```

Compress the video using the `compress` method.

```python
vf.ffmpeg.compress(td('totk_compressed.mp4'), crf=30, overwrite=True)
```


Splice the video using the `splice` method.

```python
result = vf.ffmpeg.splice(
    output_fname=td('totk_spliced.mp4'), 
    start_time=datetime.timedelta(seconds=0), 
    end_time=datetime.timedelta(seconds=5),
    overwrite=True
)
```

Crop the video using the `crop` method.
```python
result = vf.ffmpeg.crop(
    output_fname=td('totk_cropped.mp4'), 
    topleft_point=(0,0),
    size=(vf.probe().video.width//2, vf.probe().video.height//2),
    overwrite=True
)
```

Make a thumbnail using the `make_thumb` method.
```python
result = vf.ffmpeg.make_thumb(
    output_fname=td('totk_thumb.jpg'), 
    time_point=0.5,
    height=100,
    overwrite=True
)
```

### Working with Images

First create an `ImageFile` object from a file path.

```python
imf = mediatools.ImageFile.from_path('my_image.jpg')
```

You can read the image file using the `read` method. This will allow you to manipulate the data itself.

```python
imf.read()
```

You can also use the `transform` attribute to manipulate the image file. For example, you can convert the image to RGB using the `to_rgb` method.

```python
im.transform.to_rgb()
```

Resize the image.

```python
im.transform.resize((100,100))
```

Apply a filter to the image.

```python
im.filter.sobel()
```

Compute the distance between two images.

```python
im.dist.composit(im)
im.dist.euclid(im)
im.dist.sobel(im)
```


