from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import yaml

DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S"


@dataclass
class Period:
    start: datetime
    end: datetime

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Period:
        return Period(
            start=datetime.strptime(str(data["start"]), DATETIME_FORMAT),
            end=datetime.strptime(str(data["end"]), DATETIME_FORMAT),
        )


@dataclass
class Collection:
    title: str
    slug: str
    periods: list[Period] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Collection:
        return Collection(
            title=data["title"],
            slug=data["slug"],
            periods=[Period.from_dict(p) for p in data.get("periods", [])],
        )


@dataclass
class CollectionsConfig:
    updated: str
    collections: list[Collection] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CollectionsConfig:
        return CollectionsConfig(
            updated=data["updated"],
            collections=[Collection.from_dict(c) for c in data.get("collections", [])],
        )

    @staticmethod
    def from_yaml(path: str) -> CollectionsConfig:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return CollectionsConfig.from_dict(data)
