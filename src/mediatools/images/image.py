from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
import pathlib

#from .imagegrid import ImageGrid
from .distances import Distances

class Height(int):
    pass

class Width(int):
    pass

@dataclasses.dataclass(frozen=True)
class Image:
    im: np.ndarray

    #def copy(self, **new_values) -> Image:
    #    '''Copy all but provided attributes.'''
    #    return self.__class__(**{**dataclasses.asdict(self), **new_values})
    
    def copy(self, new_type: typing.Optional[typing.Type[Image]] = None, **additional_data) -> Image:
        use_type = new_type if new_type is not None else self.__class__
        return use_type(**{**dataclasses.asdict(self), **additional_data})

    ################ Dunder ################
    def __getitem__(self, ind: typing.Union[slice, typing.Tuple[slice, ...]]) -> Image:
        '''Get image at index or (y,x) index.'''
        return self.copy(im=self.im[ind])
    
    #def slice(self, y: int, x: int, h: int, w: int) -> Image:
    #    '''Get image at index or (y,x) index.'''
    #    return self[x:x+w, y:y+h]

    ################ Properties ################
    @property
    def dist(self) -> Distances:
        return Distances(self)

    @property
    def size(self) -> typing.Tuple[Height, Width]:
        '''Height, width.'''
        return self.im.shape[:2] # type: ignore    
    
    @property
    def shape(self) -> typing.Tuple[Height, Width, int]:
        '''Shape of image.'''
        return self.im.shape # type: ignore

    ################ Read/Writing ################
    @classmethod
    def read(cls, path: pathlib.Path) -> Image:
        return cls(im = skimage.io.imread(str(path)))

    #def write_ubyte(self, path: pathlib.Path) -> None:
    #    '''Writes image as uint8.'''
    #    return self.as_ubyte().write(path)
    
    def write(self, path: pathlib.Path, **kwargs) -> None:
        '''Writes image as float.'''
        return skimage.io.imsave(str(path), self.im, **kwargs)

    ################ Transforms ################

    def filter_sobel(self) -> Image:
        return self.copy(im=skimage.filters.sobel(self.im))
    
    def filter_sobel_image(self) -> Image:
        return skimage.filters.sobel(self.im)
    
    def resize(self, resize_shape: typing.Tuple[Height, Width], **kwargs) -> Image:
        return self.copy(im=skimage.transform.resize(self.im, resize_shape, **kwargs))

    def transform_color_rgb(self) -> Image:
        '''Transform image to be rgb.'''
        if len(self.im.shape) < 3:
            im = skimage.color.gray2rgb(self.im)
        elif self.im.shape[2] > 3:
            im = skimage.color.rgba2rgb(self.im)
        else:
            im = self.im
        return self.copy(im=im)

    
    ################ Conversions ################
    def as_ubyte(self) -> Image:
        return self.copy(im=skimage.img_as_ubyte(self.im))
    
    def as_float(self) -> Image:
        return self.copy(im=skimage.img_as_float(self.im))



