from __future__ import annotations
import typing
import datetime
import dataclasses
from contextlib import asynccontextmanager
from pathlib import Path
import pathlib

from fastapi import FastAPI, Header, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, PlainTextResponse
import jinja2
import pymongo
import pydantic_settings

import mediatools
from mediatools.index_db import MediaIndexDB, MediaDirIndexDoc, VideoIndexDoc, MediaDirIndexNotFoundError
from mediatools.index_db.mediadir_index_collection import IndexVideoFile, IndexImageFile


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file='.env', extra='ignore')
    montage_source_path: Path

settings = Settings()

if __name__ == '__main__':

    mdir = mediatools.scan_directory(settings.montage_source_path)

    for md in reversed(mdir.all_dirs()):
        video_paths = md.all_video_paths()
        output_path = md.path / "_compilation_random.mp4"
        if len(video_paths) <= 2 or (output_path.exists() and output_path.stat().st_size > 0):
            print(f"  Skipping montage (already exists): {output_path}")
            continue

        print(f"  Creating montage: {len(video_paths)} videos from {md.path}")
        result = mediatools.ffmpeg.create_montage(
            video_files=video_paths,
            output_filename=output_path,
            clip_ratio=10,
            clip_duration=0.75,
            random_seed=0,
            width=1920,
            height=1080,
            fps=30,
            verbose=True,
            shuffle_clips=True,
            overwrite=True,
        )
        print(f"  Done: {result}")

