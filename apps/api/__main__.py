from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .main import create_app
from .settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the media gallery server. Unset options fall back to SITE_* env vars / .env.")
    parser.add_argument("--root-path", type=Path, help="Root directory containing media files")
    parser.add_argument("--template-path", type=Path, help="Path to the gallery HTML template")
    parser.add_argument("--reels-template-path", type=Path, help="Path to the reels HTML template")
    parser.add_argument("--thumb-path", type=Path, help="Directory containing thumbnail GIFs")
    parser.add_argument("--mongodb-url", type=str, help="MongoDB connection URL")
    parser.add_argument("-d", "--database-name", type=str, help="MongoDB database name")
    parser.add_argument("-p", "--port", type=int, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Interface to bind")
    parser.add_argument("-m", "--max-clip-duration", type=float, help="Videos shorter than this (seconds) are shown as clips")
    parser.add_argument("--copy-source-root", dest="copy_source_roots", type=Path, action="append",
                        help="Directory move jobs may read from (repeatable)")
    parser.add_argument("--no-worker", dest="run_worker", action="store_const", const=False,
                        help="Don't run jobs in this process (use `python -m apps.worker`)")
    parser.add_argument("--worker-concurrency", type=int, help="Jobs to run at once")
    opts = vars(parser.parse_args())
    host = opts.pop("host")
    overrides = {f"site_{k}": v for k, v in opts.items() if v is not None}
    settings = Settings(**overrides)
    uvicorn.run(create_app(settings), host=host, port=settings.site_port)


if __name__ == "__main__":
    main()
