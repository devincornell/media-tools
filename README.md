# MediaTools

Tools for working with video, audio, and image files: an ffmpeg wrapper, image processing, a scanned media-directory model, a MongoDB-backed media index with background jobs, a gallery web server, and optional AI components (transcription, object tracking).

## Prerequisites

- Python 3.11 or newer.
- `ffmpeg` and `ffprobe` on `PATH` for the video features (for example `apt install ffmpeg`).
- MongoDB, only for the media index, jobs, and gallery server.

## Install

```bash
pip install "git+ssh://git@github.com/devincornell/media-tools.git@main"
```

From a local checkout, use `uv sync` (or `uv pip install -e .`).

```python
import mediatools
```

### Optional components

Components with heavy dependencies are optional extras. They are not imported by `import mediatools`; importing one without its extra raises an `ImportError` that names the extra to install.

| Extra | Installs | Enables |
|---|---|---|
| `transcribe` | `openai-whisper` | `mediatools.ai.transcribe_video_openai` |
| `vision` | `ultralytics`, `opencv-python-headless`, `torch`, `torchvision` | `mediatools.vision` (object tracking, optical flow) |

```bash
# from git
pip install "mediatools[vision] @ git+ssh://git@github.com/devincornell/media-tools.git@main"

# from a checkout
uv sync --extra vision
uv sync --extra transcribe --extra vision   # several extras
```

Notes on `vision`:

- It pulls in PyTorch, so the install is large. A CUDA GPU is used automatically when PyTorch can see one.
- `ultralytics` itself depends on `opencv-python` (the GUI build), which needs the system library `libGL`. In this repo a `[tool.uv]` override replaces it with `opencv-python-headless`, so `uv sync` in a checkout needs no extra system packages. A plain `pip install` of the extra does not get that override: if `import cv2` fails with `libGL.so.1: cannot open shared object file`, either `apt install libgl1`, or run `pip uninstall opencv-python` followed by `pip install --force-reinstall opencv-python-headless`.

The gallery server's dependencies are a dependency group, not an extra, and are available only from a checkout (`uv sync --group api`); see [Gallery server](#gallery-server).

## Package overview

| Module | Purpose | Needs |
|---|---|---|
| `mediatools` | `VideoFile`, `ImageFile`, `MediaDir`, `scan_directory`, and file helpers | |
| `mediatools.ffmpeg` | ffmpeg/ffprobe wrapper: probe, compress, splice, crop, thumbnails, compilations | `ffmpeg` |
| `mediatools.ai` | `transcribe_video_openai` (Whisper), `run_upscale` (video2x upscaling in Docker), and subprocess helpers | `transcribe` extra for transcription; Docker with the NVIDIA runtime for upscaling |
| `mediatools.vision` | Typed object tracking on `ultralytics` (`ObjectTracker`, `TrackedFrame`, `TrackedObject`, `BoundingBox`) and dense optical flow (`FarnebackFlow`, `DisFlow`, `RaftFlow`, `FlowField`) | `vision` extra |
| `mediatools.index_db` | MongoDB index of a media directory: directories, videos, favorites, job records | MongoDB |
| `mediatools.jobs` | Generic job system: `JobManager`, `JobWorker`, repository, and log store | MongoDB |
| `mediatools.application` | Services behind the gallery server: browsing, favorites, uploads, folder picker, media job handlers | MongoDB |
| `mediatools.contracts` | Pydantic request and response models shared by the server and client | |
| `mediatools.client` | Typed HTTP client for the gallery API (`GalleryClient`) | |

### Examples

Notebooks in [examples/](examples/):

| Notebook | Topic |
|---|---|
| [0-managing_media_files.ipynb](examples/0-managing_media_files.ipynb) | Working with media files and directories |
| [1-image_processing.ipynb](examples/1-image_processing.ipynb) | Loading, transforming, and comparing images |
| [3-ffmpeg_interface.ipynb](examples/3-ffmpeg_interface.ipynb) | Probing and processing video with ffmpeg |
| [4_media_index_database.ipynb](examples/4_media_index_database.ipynb) | Indexing media into MongoDB |
| [5-object_tracking.ipynb](examples/5-object_tracking.ipynb) | Object tracking with `mediatools.vision` (needs the `vision` extra) |

Notebooks that download sample videos read the archive URL from the `TEST_ZIP_FILE_URL` environment variable (or a `.env` file).


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

Browse `/page/`, `/reel/`, `/browse` (a Finder-style tree of every indexed folder and file, with each folder's recursive size and share of the library), or the JSON API under `/api` (docs at `/docs`). A typed client is included in the package:

```python
from mediatools.client import GalleryClient

with GalleryClient("http://localhost:8000") as client:
    page = client.get_directory("some/subdir")
```

Tests: `uv run --group api pytest tests/test_api.py tests/test_fileops.py`.

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

To run jobs outside the web server, start the server with `--no-worker` (or `SITE_RUN_WORKER=false`) and run `make worker` / `uv run --group api python -m apps.worker`. The standalone worker reads its settings from `SITE_*` / `.env` only. HTTP API: `POST /api/jobs/{reindex,thumbnails,cleanup,convert-mp4,move,move-item,delete-item}` returns `202` with a job ID; poll `GET /v1/jobs/{id}`; list with `GET /v1/jobs` or `GET /api/media-jobs`; cancel with `POST /v1/jobs/{id}/cancel`.

The server has no authentication. Anyone who can reach it can start jobs, including deletes. Keep it on a trusted network.

Job tests need a disposable MongoDB (never a real one): `make test_mongo_up && make test_jobs && make test_mongo_down`.


## Usage

### Working with Videos

First create a `VideoFile` object from a file path.

```python
import datetime
import mediatools

vf = mediatools.VideoFile.from_path('my_video.mp4')
```

Compress the video using the `compress` method.

```python
vf.ffmpeg.compress('totk_compressed.mp4', crf=30, overwrite=True)
```


Splice the video using the `splice` method.

```python
result = vf.ffmpeg.splice(
    output_fname='totk_spliced.mp4', 
    start_time=datetime.timedelta(seconds=0), 
    end_time=datetime.timedelta(seconds=5),
    overwrite=True
)
```

Crop the video using the `crop` method.
```python
result = vf.ffmpeg.crop(
    output_fname='totk_cropped.mp4', 
    topleft_point=(0,0),
    size=(vf.probe().video.width//2, vf.probe().video.height//2),
    overwrite=True
)
```

Make a thumbnail using the `make_thumb` method.
```python
result = vf.ffmpeg.make_thumb(
    output_fname='totk_thumb.jpg', 
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
im = imf.read()
```

You can also use the `transform` attribute on the loaded image to manipulate it. For example, you can convert the image to RGB using the `to_rgb` method.

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

### Object Tracking

Requires the `vision` extra (see [Optional components](#optional-components)). `ObjectTracker` wraps a YOLO model and a tracker; results are immutable, typed objects rather than raw `ultralytics` output.

```python
from mediatools.vision import ObjectTracker

tracker = ObjectTracker(
    model="yolo11m.pt",        # weights are downloaded on first use
    tracker="botsort.yaml",    # compensates for camera motion; "bytetrack.yaml" is the default
    imgsz=1280,                # detector input size; larger finds smaller objects
    classes=[0],               # optional filter; COCO class 0 is person
)
for frame in tracker.track_video("my_video.mp4"):   # one TrackedFrame per video frame
    for obj in frame:
        print(obj.track_id, obj.class_name, obj.confidence, obj.bounding_box)
```

`track_frame` tracks frames you read yourself. Create one `ObjectTracker` per video or stream, because track identities persist between calls. Tracking errors raise subclasses of `TrackingDomainError`. See [5-object_tracking.ipynb](examples/5-object_tracking.ipynb) for tuning tracks, custom tracker configurations, GPU use, and visualization.

### Optical Flow

Requires the `vision` extra. Every algorithm implements the `OpticalFlowEstimator` strategy interface (`estimate(frame1, frame2) -> FlowField`), so they are interchangeable. Frames are BGR `uint8` arrays of identical shape, as returned by OpenCV.

| Strategy | Kind | Notes |
|---|---|---|
| `FarnebackFlow` | OpenCV, classical | CPU, no downloads |
| `DisFlow` | OpenCV, classical | CPU, much faster than Farneback; presets `ultrafast`, `fast`, `medium` |
| `RaftFlow` | RAFT (torchvision), deep learning | GPU recommended; weights download on first use |

```python
from mediatools.vision import RaftFlow, estimate_video_flow

estimator = RaftFlow(max_height=360)    # or FarnebackFlow() / DisFlow()
for flow in estimate_video_flow("my_video.mp4", estimator):   # one FlowField per frame pair
    dx, dy = flow.vectors                                      # (2, H, W) float32, in pixels
    preview = flow.to_bgr()                                    # HSV color-wheel visualization
```

`FlowField.vectors` is read-only, with channel 0 the horizontal and channel 1 the vertical displacement from frame 1 to frame 2. `RaftFlow` is memory-safe for ~8GB GPUs: RAFT's memory use grows with the square of the pixel count (all-pairs correlation volume), so it downscales frames to at most `max_height` rows, runs in fp16 on CUDA, then upscales the flow to the input resolution and rescales the vectors to match. Raise `max_height` for more detail if memory allows, or use `variant="large"` for accuracy. Running out of memory raises `DeviceMemoryError`; other errors derive from `OpticalFlowError`.

## Development

```bash
uv sync --extra vision --group api   # dev group is included by default
make test                                           # video, image, media, and API tests (needs ffmpeg)
```

Job tests need a disposable MongoDB; see [Jobs](#jobs).


