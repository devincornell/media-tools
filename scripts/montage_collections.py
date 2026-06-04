from __future__ import annotations

import dateutil.parser
import dateutil.tz
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml

#DATETIME_FORMAT = "%Y/%m/%d %H:%M:%S"


@dataclass
class Period:
    start: datetime
    end: datetime

    @staticmethod
    def from_dict(data: dict[str, Any], tz=None) -> Period:
        start = dateutil.parser.parse(str(data["start"]))
        end = dateutil.parser.parse(str(data["end"]))
        if tz is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=tz)
            if end.tzinfo is None:
                end = end.replace(tzinfo=tz)
        return Period(start=start, end=end)


@dataclass
class Collection:
    title: str
    slug: str
    periods: list[Period] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any], tz=None) -> Collection:
        return Collection(
            title=data["title"],
            slug=data["slug"],
            periods=[Period.from_dict(p, tz=tz) for p in data.get("periods", [])],
        )


@dataclass
class CollectionsConfig:
    updated: str
    timezone: str = 'UTC'
    collections: list[Collection] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CollectionsConfig:
        tz_str = data.get('timezone', 'UTC')
        tz = dateutil.tz.gettz(tz_str)
        if tz is None:
            raise ValueError(f"Unknown timezone: {tz_str!r}")
        return CollectionsConfig(
            updated=data["updated"],
            timezone=tz_str,
            collections=[Collection.from_dict(c, tz=tz) for c in data.get("collections", [])],
        )

    @staticmethod
    def from_yaml(path: str) -> CollectionsConfig:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return CollectionsConfig.from_dict(data)
