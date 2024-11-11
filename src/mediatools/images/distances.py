from __future__ import annotations
import pathlib
import dataclasses
import typing
from PIL import Image, ImageChops
import skimage
import numpy as np
import random

if typing.TYPE_CHECKING:
    from .image import Image

@dataclasses.dataclass
class Distances:
    image: Image
    def composit(self, other: Image) -> float:
        return self.euclid(other) + self.sobel(other)

    def euclid(self, other: Image) -> float:
        return np.linalg.norm(self.image.im - other.im)
            
    def sobel(self, other: Image) -> float:
        return np.linalg.norm(self.image.filter_sobel_image() - other.filter_sobel_image())
