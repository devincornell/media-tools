from __future__ import annotations
import dataclasses
import typing
import skimage # type: ignore
import numpy as np
import pathlib

#from .imagegrid import ImageGrid
#from .distances import Distances

Height = int
Width = int

@dataclasses.dataclass(frozen=True)
class Image:
    '''Represents an image loaded into memory.'''
    im: np.ndarray

    @classmethod
    def from_file(cls, path: pathlib.Path) -> typing.Self:
        return cls(
            im=skimage.io.imread(str(path))
        )
    def clone(self, **new_attrs) -> Image:
        return self.__class__(**{**dataclasses.asdict(self), **new_attrs})

    ################ Dunder ################
    def __getitem__(self, ind: slice | tuple[slice, ...]) -> typing.Self:
        '''Get image at index or (y,x) index.'''
        return self.clone(im=self.im[ind])
    
    ################ Properties ################
    @property
    def dist(self) -> DistanceCalculator:
        return DistanceCalculator(self)
    
    @property
    def filter(self) -> FilterCalculator:
        return FilterCalculator(self)
    
    @property
    def transform(self) -> TransformCalculator:
        return TransformCalculator(self)

    @property
    def size(self) -> typing.Tuple[Height, Width]:
        '''Height, width.'''
        return self.im.shape[:2] # type: ignore    
    
    @property
    def shape(self) -> typing.Tuple[Height, Width, int]:
        '''Shape of image.'''
        return self.im.shape # type: ignore

    ################ Read/Writing ################

    #def write_ubyte(self, path: pathlib.Path) -> None:
    #    '''Writes image as uint8.'''
    #    return self.as_ubyte().write(path)
    
    def write(self, path: pathlib.Path, **kwargs) -> None:
        '''Writes image as float.'''
        return skimage.io.imsave(str(path), self.im, **kwargs)

    ################ Transforms ################

    #def filter_sobel(self) -> Image:
    #    return self.clone(im=skimage.filters.sobel(self.im))
    
    #def filter_sobel_image(self) -> Image:
    #    return skimage.filters.sobel(self.im)
    
    #def resize(self, resize_shape: typing.Tuple[Height, Width], **kwargs) -> Image:
    #    return self.clone(im=skimage.transform.resize(self.im, resize_shape, **kwargs))

    #def transform_color_rgb(self) -> Image:
    #    '''Transform image to be rgb.'''
    #    if len(self.im.shape) < 3:
    #        im = skimage.color.gray2rgb(self.im)
    #    elif self.im.shape[2] > 3:
    #        im = skimage.color.rgba2rgb(self.im)
    #    else:
    #        im = self.im
    #    return self.clone(im=im)

    
    ################ Conversions ################
    def as_ubyte(self) -> Image:
        return self.clone(im=skimage.img_as_ubyte(self.im))
    
    def as_float(self) -> Image:
        return self.clone(im=skimage.img_as_float(self.im))


@dataclasses.dataclass
class TransformCalculator:
    '''Calculates distances between images.'''
    image: Image
    
    def to_rgb(self) -> Image:
        '''Transform image to be rgb.'''
        if len(self.image.im.shape) < 3:
            im = skimage.color.gray2rgb(self.im)
        elif self.image.im.shape[2] > 3:
            im = skimage.color.rgba2rgb(self.im)
        else:
            im = self.image.im
        return self.image.clone(im=im)
    
    def resize(self, resize_shape: typing.Tuple[Height, Width], **kwargs) -> Image:
        '''Resize image.'''
        return self.image.clone(im=skimage.transform.resize(self.image.im, resize_shape, **kwargs))

@dataclasses.dataclass
class FilterCalculator:
    '''Calculates distances between images.'''
    image: Image
    
    def sobel(self) -> Image:
        '''Sobel filtered image.'''
        return self.image.clone(im=skimage.filters.sobel(self.image.im))

@dataclasses.dataclass
class DistanceCalculator:
    '''Calculates distances between images.'''
    image: Image

    def composit(self, other: Image) -> float:
        '''Composite distance between images.'''
        return self.euclid(other) + self.sobel(other)

    def euclid(self, other: Image) -> float:
        '''Euclidean distance between images.'''
        return np.linalg.norm(self.image.im - other.im)
            
    def sobel(self, other: Image) -> float:
        '''Distances between sobel filtered images.'''
        return np.linalg.norm(self.image.filter.sobel().im - other.filter.sobel().im)
