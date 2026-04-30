# Image Processing

This notebook demonstrates the image processing functionality from `mediatools`, which provides powerful tools for loading, manipulating, analyzing, and comparing images using the scikit-image library as its core processing engine.

**What you'll learn:**
- How to load and work with individual images and image collections
- Basic image transformations (resize, color conversion, filtering)
- Image comparison and distance calculations
- Batch processing workflows for image collections
- Integration with file system operations and metadata extraction
- Practical workflows for image analysis and processing

**Prerequisites:**
- Basic Python knowledge
- Familiarity with numpy arrays (helpful but not required)
- Understanding of basic image concepts (resolution, color channels)

**Key Concepts:**
- **ImageFile**: Represents an image file on disk with metadata capabilities
- **Image**: In-memory representation supporting transformations and analysis
- **ImageFiles/ImageFilesDict**: Collections for batch operations
- **Transform, Filter, and Distance Calculators**: Organized APIs for image operations
- **Integration with MediaDir**: How images fit into larger media workflows


```python
import tempfile
import numpy as np
from pathlib import Path
import requests
import mediatools
```

### Setup and Sample Image Creation

Since this is a demonstration notebook, we'll download some sample images and create a realistic directory structure for testing. This allows you to run the examples without needing your own image collection.


```python
def download_sample_image(url: str, filename: str, temp_dir: Path) -> Path:
    response = requests.get(url)
    response.raise_for_status()
    file_path = temp_dir / filename
    with open(file_path, 'wb') as f:
        f.write(response.content)
    return file_path

def create_sample_image_directory():
    temp_dir = Path(tempfile.mkdtemp(prefix="mediatools_images_"))
    (temp_dir / "nature").mkdir()
    (temp_dir / "processed").mkdir()
    (temp_dir / "comparisons").mkdir()
    
    sample_url = "https://storage.googleapis.com/public_data_09324832787/blogpost_filecol_select_payload_time.png"
    sample_paths = [
        download_sample_image(sample_url, "sample_chart.png", temp_dir),
        download_sample_image(sample_url, "nature/landscape.png", temp_dir),
        download_sample_image(sample_url, "nature/mountains.png", temp_dir),
    ]
    return temp_dir

temp_dir = create_sample_image_directory()
```

## Working with Image Files

### `ImageFile` Instances

The `ImageFile` class represents an image file on disk. It provides convenient stat methods and the ability to load images into memory for processing.


```python
image_file = mediatools.ImageFile.from_path(temp_dir / "sample_chart.png")
image_file
```




    ImageFile(path=PosixPath('/tmp/mediatools_images_xwc847gi/sample_chart.png'), meta={})




```python
image_file.path
```




    PosixPath('/tmp/mediatools_images_xwc847gi/sample_chart.png')



Get the equivalent of a file stat using `stat`.


```python
image_file.stat()
```




    FileStatResult(st_mode=33204, st_ino=44435265, st_dev=66309, st_nlink=1, st_uid=1000, st_gid=1000, st_size=46726, st_atime=1777205459.0926836, st_mtime=1777205459.0931644, st_ctime=1777205459.0931644, st_atime_ns=1777205459092683467, st_mtime_ns=1777205459093164340, st_ctime_ns=1777205459093164340, st_blksize=4096, st_blocks=96, st_rdev=0, st_birthtime=None)



You can also get additional metadata from the image file by reading it. Here, we get the file stat and the image resolution.


```python
image_meta = image_file.read_meta()
image_meta
```




    ImageMeta(path=PosixPath('/tmp/mediatools_images_xwc847gi/sample_chart.png'), res=(2187, 1350), stat=FileStatResult(st_mode=33204, st_ino=44435265, st_dev=66309, st_nlink=1, st_uid=1000, st_gid=1000, st_size=46726, st_atime=1777205459.0926836, st_mtime=1777205459.0931644, st_ctime=1777205459.0931644, st_atime_ns=1777205459092683467, st_mtime_ns=1777205459093164340, st_ctime_ns=1777205459093164340, st_blksize=4096, st_blocks=96, st_rdev=0, st_birthtime=None), meta={})



### `ImageFiles` Collection

The `ImageFiles` collection is simply a list of `ImageFile` instances, and you can use `from_rglob` or `from_glob` to search for them within a directory.

You can also use the `ImageFiles` class to retrieve images.


```python
image_collection = mediatools.ImageFiles.from_rglob(temp_dir)
len(image_collection)
```




    6




```python
nature_images = mediatools.ImageFiles.from_glob(temp_dir / "nature")
[img.path.name for img in nature_images]
```




    ['landscape.png', 'landscape.png', 'mountains.png', 'mountains.png']



You can also use `scan_directory` coupled with `all_image_files` to get a collection of all images in a directory recursively.


```python
image_files = mediatools.scan_directory(temp_dir).all_image_files()
image_files
```




    [ImageFile(path=PosixPath('/tmp/mediatools_images_xwc847gi/sample_chart.png'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_images_xwc847gi/nature/mountains.png'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_images_xwc847gi/nature/landscape.png'), meta={})]



## Working with Image Data

Now we discuss the in-memory image manipulation methods

### Reading and Writing Images

`Image` instances maintain an image loaded into memory as a numpy array, with convenient methods for processing. Use the `ImageFile.read` method to load the image into memory.


```python
image = image_file.read()
image
```




    Image(shape=(1350, 2187, 3))




```python
image.shape, image.size, image.im.dtype
```




    ((1350, 2187, 3), (1350, 2187), dtype('uint8'))




```python
image.write(temp_dir / "processed" / "sample_chart_copy.png")
```

### Underlying Data Types

Under the hood, images can take on many different formats. In the future, I will write distinct types for each type of image, but for now the `Image` type is agnostic to the underlying data, with the caveat that some methods (such as those based on file I/O) may raise exceptions if the data is not in the proper format.


```python
float_image = image.as_float()
ubyte_image = image.as_ubyte()
image.im.dtype, float_image.im.dtype, ubyte_image.im.dtype
```




    (dtype('uint8'), dtype('float64'), dtype('uint8'))



Convert to RGB (handles grayscale and RGBA automatically):


```python
rgb_image = image.to_rgb()
image.shape, rgb_image.shape
```




    ((1350, 2187, 3), (1350, 2187, 3))



### Image Array Operations

`Image` instances implement `__getitem__` in a way that is very similar to the underlying array data, except that it returns a new `Image` instance. One consequence is that you can use standard array indexing and slicing operations.


```python
h, w = image.shape[:2]
crop_size = min(h, w) // 3
start_h = (h - crop_size) // 2
start_w = (w - crop_size) // 2

cropped = image[start_h:start_h + crop_size, start_w:start_w + crop_size]
```


```python
f"Cropped from {image.shape} to {cropped.shape}"
```




    'Cropped from (1350, 2187, 3) to (450, 450, 3)'



### Transformation Methods

The `transform` property provides access to various image transformation operations.


```python
resized_large = image.transform.resize((400, 600))
resized_small = image.transform.resize((100, 150))
```


```python
image.size, resized_large.size, resized_small.size
```




    ((1350, 2187), (400, 600), (100, 150))



Aspect-preserving resize (use -1 for auto-calculated dimension):


```python
aspect_resize = image.transform.resize((-1, 200))
aspect_resize.size
```




    (123, 200)



### Filter Methods

The `filter` property provides access to various image filtering operations.

Apply Sobel edge detection filter:


```python
sobel_filtered = image.filter.sobel()
sobel_filtered.shape
```




    (1350, 2187, 3)



### Distance Metrics

We can also use several distance metrics.


```python
image.dist.euclid(sobel_filtered)
```




    728347.6578505074




```python
image.dist.composit(sobel_filtered)
```




    728481.5659748459




```python
image.dist.sobel(sobel_filtered)
```




    133.90812433852807



## Advanced Workflows and Use Cases

### 1. Image Similarity Analysis


```python
def analyze_image_similarities(image_files: mediatools.ImageFiles, comparison_size=(100, 100)):
    if len(image_files) < 2:
        return "Need at least 2 images for similarity analysis"
    
    images = []
    for img_file in image_files:
        img = img_file.read().transform.resize(comparison_size)
        images.append((img_file.path.name, img))
    
    n = len(images)
    distances = np.zeros((n, n))
    
    for i, (name_i, img_i) in enumerate(images):
        for j, (name_j, img_j) in enumerate(images):
            if i != j:
                distances[i, j] = img_i.dist.composit(img_j)
    
    return distances, images

if len(image_collection) >= 2:
    distance_matrix, analyzed_images = analyze_image_similarities(image_collection)
    distance_matrix
else:
    "Need more images for similarity analysis"
```

### 2. Image Quality Assessment


```python
def assess_image_quality(image_files: mediatools.ImageFiles):
    quality_metrics = []
    
    for img_file in image_files:
        meta = img_file.read_meta()
        stat = img_file.stat()
        image = img_file.read()
        
        edges = image.filter.sobel()
        edge_density = np.mean(edges.im)
        
        if len(image.shape) == 3:
            gray = np.mean(image.im, axis=2)
        else:
            gray = image.im
        dynamic_range = np.max(gray) - np.min(gray)
        
        quality_metrics.append({
            'filename': img_file.path.name,
            'resolution': meta.res,
            'file_size_mb': stat.size / (1024 * 1024),
            'edge_density': edge_density,
            'dynamic_range': dynamic_range,
        })
    
    return quality_metrics

quality_results = assess_image_quality(image_collection)
```

View quality assessment results:


```python
for result in quality_results:
    print(f"{result['filename']}: {result['resolution']} - {result['edge_density']:.3f} edge density")
```

    landscape.png: (2187, 1350) - 0.010 edge density
    landscape.png: (2187, 1350) - 0.010 edge density
    mountains.png: (2187, 1350) - 0.010 edge density
    mountains.png: (2187, 1350) - 0.010 edge density
    sample_chart.png: (2187, 1350) - 0.010 edge density
    sample_chart.png: (2187, 1350) - 0.010 edge density


### 3. Computing Organizational Statistics


```python
# First define the organization function
def organize_images_by_properties(image_files: mediatools.ImageFiles):
    organization_stats = {
        'by_resolution': {},
        'by_aspect_ratio': {},
        'by_file_size': {}
    }
    
    for img_file in image_files:
        meta = img_file.read_meta()
        stat = img_file.stat()
        
        width, height = meta.res
        aspect_ratio = width / height
        file_size_mb = stat.size / (1024 * 1024)
        
        # Categorize by resolution
        if width >= 1920 and height >= 1080:
            resolution_category = "high_res"
        elif width >= 800 and height >= 600:
            resolution_category = "medium_res"
        else:
            resolution_category = "low_res"
        
        # Update statistics
        organization_stats['by_resolution'][resolution_category] = \
            organization_stats['by_resolution'].get(resolution_category, 0) + 1
    
    return organization_stats

# Apply the organization function
org_stats = organize_images_by_properties(image_collection)
org_stats
```




    {'by_resolution': {'high_res': 6}, 'by_aspect_ratio': {}, 'by_file_size': {}}


