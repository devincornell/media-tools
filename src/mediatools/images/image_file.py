from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
import pathlib

from .image import Image

@dataclasses.dataclass(frozen=True)
class ImageFile(Image):
    path: pathlib.Path

    @classmethod
    def read(cls, path: pathlib.Path) -> typing.Self:
        return cls(
            path=pathlib.Path(path),
            im=skimage.io.imread(str(path))
        )
