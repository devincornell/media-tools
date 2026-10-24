from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pydantic_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    site_root_path: Path
    site_thumb_path: Path
    site_mongodb_url: str
    site_database_name: str
    site_template_path: Path = TEMPLATES_DIR / "gallery.html"
    site_reels_template_path: Path = TEMPLATES_DIR / "reels.html"
    site_port: int = 8000
    site_max_clip_duration: float = 0.0
    site_copy_source_roots: list[Path] = []
    site_run_worker: bool = True
    site_worker_concurrency: int = 4
    site_job_lease_seconds: float = 60.0


@dataclasses.dataclass(frozen=True)
class ServerConfig:
    root_path: Path
    thumb_path: Path
    template_path: Path
    reels_template_path: Path
    max_clip_duration: float
    mongodb_url: str
    database_name: str
    copy_source_roots: tuple[Path, ...] = ()
    run_worker: bool = True
    worker_concurrency: int = 4
    job_lease_seconds: float = 60.0

    @classmethod
    def from_settings(cls, settings: Settings) -> typing.Self:
        '''Resolve paths from settings, validating that they exist.'''
        paths = {
            "Root path": settings.site_root_path,
            "Thumbnail path": settings.site_thumb_path,
            "Template path": settings.site_template_path,
            "Reels template path": settings.site_reels_template_path,
        }
        resolved = {label: path.resolve() for label, path in paths.items()}
        for label, path in resolved.items():
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")
        copy_roots = tuple(p.resolve() for p in settings.site_copy_source_roots)
        for path in copy_roots:
            if not path.is_dir():
                raise FileNotFoundError(f"Copy source root not found: {path}")

        return cls(
            root_path=resolved["Root path"],
            thumb_path=resolved["Thumbnail path"],
            template_path=resolved["Template path"],
            reels_template_path=resolved["Reels template path"],
            max_clip_duration=settings.site_max_clip_duration,
            mongodb_url=settings.site_mongodb_url,
            database_name=settings.site_database_name,
            copy_source_roots=copy_roots,
            run_worker=settings.site_run_worker,
            worker_concurrency=max(1, settings.site_worker_concurrency),
            job_lease_seconds=settings.site_job_lease_seconds,
        )
