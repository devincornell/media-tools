from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pydantic_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"


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


@dataclasses.dataclass(frozen=True)
class ServerConfig:
    root_path: Path
    thumb_path: Path
    template_path: Path
    reels_template_path: Path
    max_clip_duration: float
    mongodb_url: str
    database_name: str

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

        return cls(
            root_path=resolved["Root path"],
            thumb_path=resolved["Thumbnail path"],
            template_path=resolved["Template path"],
            reels_template_path=resolved["Reels template path"],
            max_clip_duration=settings.site_max_clip_duration,
            mongodb_url=settings.site_mongodb_url,
            database_name=settings.site_database_name,
        )
