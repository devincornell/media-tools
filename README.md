# MediaTools
This package contains tools for working with video and image files.

### Install

```bash
pip install git+ssh://git@github.com:devincornell/media-tools.git@main
```

```python
import mediatools
```


## API Overview

Currently, the package provides tools for working with video and image files.

+ **Video files**: process videos using [ffmpeg-python](https://github.com/kkroening/ffmpeg-python).
    + Compress
    + Splice
    + Crop
    + Create thumbnails

+ **Image files**: interface for manipulating images using [skimage](https://scikit-image.org/).
    + Convert between GS/RGB/RGBA
    + Compute filter functions
    + Execute distance metrics
    + Crop
    + Resize

### Working with Videos

First create a `VideoFile` object from a file path.

```python
vf = mediatools.VideoFile.from_path('my_video.mp4)
```

Compress the video using the `compress` method.

```python
vf.ffmpeg.compress(td('totk_compressed.mp4'), crf=30, overwrite=True)
```


Splice the video using the `splice` method.

```python
result = vf.ffmpeg.splice(
    output_fname=td('totk_spliced.mp4'), 
    start_time=datetime.timedelta(seconds=0), 
    end_time=datetime.timedelta(seconds=5),
    overwrite=True
)
```

Crop the video using the `crop` method.
```python
result = vf.ffmpeg.crop(
    output_fname=td('totk_cropped.mp4'), 
    topleft_point=(0,0),
    size=(vf.probe().video.width//2, vf.probe().video.height//2),
    overwrite=True
)
```

Make a thumbnail using the `make_thumb` method.
```python
result = vf.ffmpeg.make_thumb(
    output_fname=td('totk_thumb.jpg'), 
    time_point=0.5,
    height=100,
    overwrite=True
)
```

### Working with Images

First create an `ImageFile` object from a file path.

```python
imf = mediatools.ImageFile.from_path('my_image.jpg')
```

You can read the image file using the `read` method. This will allow you to manipulate the data itself.

```python
imf.read()
```

You can also use the `transform` attribute to manipulate the image file. For example, you can convert the image to RGB using the `to_rgb` method.

```python
im.transform.to_rgb()
```

Resize the image.

```python
im.transform.resize((100,100))
```

Apply a filter to the image.

```python
im.filter.sobel()
```

Compute the distance between two images.

```python
im.dist.composit(im)
im.dist.euclid(im)
im.dist.sobel(im)
```


