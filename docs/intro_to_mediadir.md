# Managing Media Files

This notebook demonstrates the MediaDir functionality from `mediatools`, which provides a powerful recursive data structure for organizing and managing media files in filesystem directories.

**What you'll learn:**
- How to scan directories for media files (videos, images, other files)
- Navigate and work with nested directory structures
- Access and process media files at individual and batch levels
- Compare directories and detect changes
- Integration patterns with other mediatools modules

**Prerequisites:**
- Basic Python knowledge
- Familiarity with pathlib for file system operations
- Some media files to experiment with (we'll create mock examples)

**Key Concepts:**
- **MediaDir**: Recursive directory structure containing videos, images, and subdirectories
- **File Collections**: VideoFiles, ImageFiles, and other file containers
- **Metadata Integration**: Each file type provides rich metadata access
- **Path Flexibility**: Support for both absolute and relative path handling

## Import Section


```python
import pathlib
import tempfile
import shutil
from pathlib import Path
import mediatools
```

## Setup and Mock Data Creation

Since this is a demonstration notebook, we'll create a realistic directory structure with mock media files. This allows you to run the examples without needing your own media collection.


```python
# Create a temporary directory structure with mock media files
def create_mock_media_directory():
    """Create a realistic directory structure with mock media files for demonstration"""
    temp_dir = Path(tempfile.mkdtemp(prefix="mediatools_demo_"))
    print(f"Created demo directory: {temp_dir}")
    
    # Define all files to create (directories will be created automatically)
    mock_files = [
        # Videos
        "vacation_2023/beach/surfing.mp4", "vacation_2023/beach/sunset.mov",
        "vacation_2023/mountains/hiking.mp4", "vacation_2023/mountains/drone_footage.mp4", 
        "family_events/birthday/cake_ceremony.mp4", "family_events/birthday/kids_playing.avi",
        "projects/timelapse/construction.mkv",
        # Images  
        "vacation_2023/beach/group_photo.jpg", "vacation_2023/beach/shells.png",
        "vacation_2023/mountains/panorama.jpg", "vacation_2023/mountains/wildlife.jpg",
        "family_events/birthday/decorations.jpg", "family_events/family_portrait.png",
        "projects/timelapse/setup.jpg",
        # Other files
        "vacation_2023/itinerary.txt", "family_events/guest_list.xlsx", "projects/README.md"
    ]
    
    # Create all files (directories will be created automatically)
    for file_path in mock_files:
        full_path = temp_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.touch()
    
    return temp_dir

# Create our demo directory
demo_root = create_mock_media_directory()

print("\nDemo directory structure created:")
for item in sorted(demo_root.rglob("*")):
    if item.is_file():
        print(f"  {item.relative_to(demo_root)}")
```

    Created demo directory: /tmp/mediatools_demo_c5unehg_
    
    Demo directory structure created:
      family_events/birthday/cake_ceremony.mp4
      family_events/birthday/decorations.jpg
      family_events/birthday/kids_playing.avi
      family_events/family_portrait.png
      family_events/guest_list.xlsx
      projects/README.md
      projects/timelapse/construction.mkv
      projects/timelapse/setup.jpg
      vacation_2023/beach/group_photo.jpg
      vacation_2023/beach/shells.png
      vacation_2023/beach/sunset.mov
      vacation_2023/beach/surfing.mp4
      vacation_2023/itinerary.txt
      vacation_2023/mountains/drone_footage.mp4
      vacation_2023/mountains/hiking.mp4
      vacation_2023/mountains/panorama.jpg
      vacation_2023/mountains/wildlife.jpg


## Creating and Navigating `MediaDir` Instances

### Creating a MediaDir from a Directory

The primary way to create a MediaDir is by scanning a filesystem directory. MediaDir will automatically categorize files into videos, images, and other files based on their extensions.


```python
# Method 1: Using the scan_directory function (recommended)
media_dir = mediatools.scan_directory(demo_root)

print(f"MediaDir created for: {media_dir.path}")
print(f"Contains {len(media_dir.subdirs)} subdirectories, {len(media_dir.videos)} videos, {len(media_dir.images)} images, and {len(media_dir.other_files)} other files in total")
```

    MediaDir created for: /tmp/mediatools_demo_c5unehg_
    Contains 3 subdirectories, 0 videos, 0 images, and 0 other files in total



```python
# Method 2: Using the MediaDir class method directly
media_dir_alt = mediatools.MediaDir.from_path(demo_root)

# Both methods produce equivalent results
print(f"Same result: {media_dir.path == media_dir_alt.path}")
```

    Same result: True


You can use the `display` method to see an overview of the directory structure.


```python
print(media_dir.display())
```

    /tmp/mediatools_demo_c5unehg_/
    ├── family_events/
    │   ├── [I] family_portrait.png
    │   ├── [F] guest_list.xlsx
    │   └── birthday/
    │       ├── [V] cake_ceremony.mp4
    │       ├── [V] kids_playing.avi
    │       └── [I] decorations.jpg
    ├── projects/
    │   ├── [F] README.md
    │   └── timelapse/
    │       ├── [V] construction.mkv
    │       └── [I] setup.jpg
    └── vacation_2023/
        ├── [F] itinerary.txt
        ├── beach/
        │   ├── [V] sunset.mov
        │   ├── [V] surfing.mp4
        │   ├── [I] group_photo.jpg
        │   └── [I] shells.png
        └── mountains/
            ├── [V] drone_footage.mp4
            ├── [V] hiking.mp4
            ├── [I] panorama.jpg
            └── [I] wildlife.jpg


Either method accepts `video_ext` and `image_ext` parameters to control which file types are considered as video or images. From the `display` output see that the .mkv files are no longer seen as files (they show `F` instead of `V`).


```python
md = mediatools.scan_directory(
    demo_root,
    video_ext=['.mp4', '.mov'],  # Only MP4 and MOV files
    image_ext=['.jpg', '.jpeg']  # Only JPEG files
)
print(md.display())
```

    /tmp/mediatools_demo_c5unehg_/
    ├── family_events/
    │   ├── [F] family_portrait.png
    │   ├── [F] guest_list.xlsx
    │   └── birthday/
    │       ├── [V] cake_ceremony.mp4
    │       ├── [I] decorations.jpg
    │       └── [F] kids_playing.avi
    ├── projects/
    │   ├── [F] README.md
    │   └── timelapse/
    │       ├── [I] setup.jpg
    │       └── [F] construction.mkv
    └── vacation_2023/
        ├── [F] itinerary.txt
        ├── beach/
        │   ├── [V] sunset.mov
        │   ├── [V] surfing.mp4
        │   ├── [I] group_photo.jpg
        │   └── [F] shells.png
        └── mountains/
            ├── [V] drone_footage.mp4
            ├── [V] hiking.mp4
            ├── [I] panorama.jpg
            └── [I] wildlife.jpg


The `ignore_path` allows you to ignore particular paths. Note that this is applied recursively, so any matching path will be ignored as well as all of its subdirectories.

Here I ignore all directories that start with "b".


```python
md = mediatools.scan_directory(
    demo_root,
    ignore_path = lambda p: p.name.startswith('b'),
)
print(md.display())
```

    /tmp/mediatools_demo_c5unehg_/
    ├── family_events/
    │   ├── [I] family_portrait.png
    │   └── [F] guest_list.xlsx
    ├── projects/
    │   ├── [F] README.md
    │   └── timelapse/
    │       ├── [V] construction.mkv
    │       └── [I] setup.jpg
    └── vacation_2023/
        ├── [F] itinerary.txt
        └── mountains/
            ├── [V] drone_footage.mp4
            ├── [V] hiking.mp4
            ├── [I] panorama.jpg
            └── [I] wildlife.jpg


The `path` attribute allows you to access the path of a given `MediaDir`.


```python
media_dir.path
```




    PosixPath('/tmp/mediatools_demo_c5unehg_')



### Navigating Directory Trees

Directories are trees, so you can navigate them as such.

Access subdirectories using the `subdirs` attribute. This is a dictionary of subdir names mapped to `MediaDir` instances.


```python
print(f"{media_dir} has {len(media_dir.subdirs)} subdirectories:")
for subdir_name, subdir in media_dir.subdirs.items():
    print(f"  {subdir_name}: {subdir.path}")
```

    MediaDir("/tmp/mediatools_demo_c5unehg_") has 3 subdirectories:
      family_events: /tmp/mediatools_demo_c5unehg_/family_events
      vacation_2023: /tmp/mediatools_demo_c5unehg_/vacation_2023
      projects: /tmp/mediatools_demo_c5unehg_/projects


Each `MediaDir` also has a parent.


```python
for subdir in media_dir.subdirs.values():
    print(subdir.parent)
```

    MediaDir("/tmp/mediatools_demo_c5unehg_")
    MediaDir("/tmp/mediatools_demo_c5unehg_")
    MediaDir("/tmp/mediatools_demo_c5unehg_")


Note that the root instance parent is `None`.


```python
print(media_dir.parent)
```

    None


The fact that this is a recursive data structure means it is easy to write recursive functions.


```python
def print_tree(mdir: mediatools.MediaDir, level: int = 0):
    print(f"{'  ' * level}- {mdir.path.name}")
    for subdir in mdir.subdirs.values():
        print_tree(subdir, level + 1)

print_tree(media_dir)
```

    - mediatools_demo_c5unehg_
      - family_events
        - birthday
      - vacation_2023
        - mountains
        - beach
      - projects
        - timelapse



```python
def count_files(mdir: mediatools.MediaDir) -> int:
    count = len(mdir.videos) + len(mdir.images) + len(mdir.other_files)
    for subdir in mdir.subdirs.values():
        count += count_files(subdir)
    return count
count_files(media_dir)
```




    17



### Navigate Directories as Paths

There are also more path-centric methods for interacting with the media directories.

You can use subscripts to access child directories. Note that you cannot use this to access files - only subdirectories.


```python
media_dir["vacation_2023"]["mountains"]
```




    MediaDir("/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains")



You can also use the `subdir` method to access children. Note that it accepts a variable number of arguments.


```python
media_dir.subdir("vacation_2023"), media_dir.subdir("vacation_2023", "beach")
```




    (MediaDir("/tmp/mediatools_demo_c5unehg_/vacation_2023"),
     MediaDir("/tmp/mediatools_demo_c5unehg_/vacation_2023/beach"))



The `subdir` method also accepts full relative paths.


```python
media_dir.subdir(Path("family_events") / "birthday")
```




    MediaDir("/tmp/mediatools_demo_c5unehg_/family_events/birthday")



## Working with Media Files

`MediaDir` instances automatically track videos and images in `VideoFile` and `ImageFile` instances, and all other files are wrapped in `NonMediaFile` instances. You can access videos through `.videos`, images through `.images`, and other files through `.other_files`.

This is a set of methods and properties you can use to access files from a `MediaDir`:


**Properties for Current Directory**

- `videos` (`list[VideoFile]`): videos in the represented directory only.
- `images` (`list[ImageFile]`): images in the represented directory only.
- `other_files` (`list[NonMediaFile]`): all non-media files in the directory only.

**Path Methods for Current Directory**
- `video_paths()` (`list[Path]`): list of video file paths in the directory only.
- `image_paths()` (`list[Path]`): list of image file paths in the directory only.


```python
beach_dir = media_dir["vacation_2023"]["beach"]
beach_dir.videos
```




    [VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'), meta={})]




```python
beach_dir.images
```




    [ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'), meta={})]




```python
beach_dir.image_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png')]




```python
beach_dir.other_files
```




    []




```python
beach_dir.video_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov')]



**Get Specific Files by Path**
- `get_video(path)` (`VideoFile`): retrieve a specific video file by its path.
- `get_image(path)` (`ImageFile`): retrieve a specific image file by its path.
- `get_nonmedia(path)` (`NonMediaFile`): retrieve a specific non-media file by its path.


```python
media_dir.get_video(demo_root / "vacation_2023" / "beach" / "surfing.mp4")
```




    VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'), meta={})




```python
media_dir.get_image(demo_root / "vacation_2023" / "mountains" / "panorama.jpg")
```




    ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'), meta={})




```python
media_dir.get_nonmedia(demo_root / "vacation_2023" / "itinerary.txt")
```




    NonMediaFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/itinerary.txt'), meta={})



You can also retrieve all video or image files recursively from a media directory.

**Recursive Methods (Include Subdirectories)**
- `all_video_files()` (`list[VideoFile]`): all video files recursively across directory tree.
- `all_image_files()` (`list[ImageFile]`): all image files recursively across directory tree.
- `all_video_paths()` (`list[Path]`): all video file paths recursively across directory tree.
- `all_image_paths()` (`list[Path]`): all image file paths recursively across directory tree.
- `all_file_paths()` (`list[Path]`): all file paths (including non-media) recursively across directory tree.
- `all_media_paths()` (`list[Path]`): all media file paths (videos + images) recursively across directory tree.



```python
media_dir.all_image_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/family_portrait.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/wildlife.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/setup.jpg')]




```python
media_dir.all_file_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/cake_ceremony.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/hiking.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/construction.mkv'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/family_portrait.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/wildlife.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/setup.jpg')]




```python
media_dir.all_media_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/family_portrait.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/cake_ceremony.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/hiking.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/wildlife.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/construction.mkv'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/setup.jpg')]




```python
media_dir.all_video_files()
```




    [VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/cake_ceremony.mp4'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/kids_playing.avi'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/hiking.mp4'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'), meta={}),
     VideoFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/construction.mkv'), meta={})]




```python
media_dir.all_image_files()
```




    [ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/family_portrait.png'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/wildlife.jpg'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'), meta={}),
     ImageFile(path=PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/setup.jpg'), meta={})]




```python
media_dir.all_video_paths()
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/cake_ceremony.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/hiking.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/construction.mkv')]



All file instance types have a `stat` method that returns a `FileStatResult` type, which is essentially a `pydantic.BaseType` containing the same information as `os.stat_result` with some convenient methods.


```python
ex_vid = beach_dir.videos[0]
ex_vid.path
```




    PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4')




```python
stat = ex_vid.stat()
stat
```




    FileStatResult(st_mode=33204, st_ino=44434722, st_dev=66309, st_nlink=1, st_uid=1000, st_gid=1000, st_size=0, st_atime=1777145433.3239105, st_mtime=1777145433.3239105, st_ctime=1777145433.3239105, st_atime_ns=1777145433323910505, st_mtime_ns=1777145433323910505, st_ctime_ns=1777145433323910505, st_blksize=4096, st_blocks=0, st_rdev=0, st_birthtime=None)




```python
stat.size_str(), stat.modified_at_str(), stat.accessed_at_str(), stat.changed_at_str()
```




    ('0.00 Bytes',
     '2026-04-25 19:30:33 UTC',
     '2026-04-25 19:30:33 UTC',
     '2026-04-25 19:30:33 UTC')



## Directory Comparison and Synchronization

### Detecting Changes Between Directory States


```python
# Create a modified version of our directory for comparison
def create_modified_directory():
    """Create a slightly modified version of our demo directory"""
    modified_root = Path(tempfile.mkdtemp(prefix="mediatools_modified_"))
    
    # Copy the original structure
    shutil.copytree(demo_root, modified_root, dirs_exist_ok=True)
    
    # Make some changes:
    # 1. Remove a file
    (modified_root / "vacation_2023" / "beach" / "shells.png").unlink()
    
    # 2. Add a new file
    (modified_root / "vacation_2023" / "new_video.mp4").touch()
    
    # 3. Add a new directory with files
    new_dir = modified_root / "vacation_2023" / "city"
    new_dir.mkdir()
    (new_dir / "architecture.jpg").touch()
    (new_dir / "street_performance.mp4").touch()
    
    return modified_root
```


```python
# Create modified directory and scan it
modified_root = create_modified_directory()
modified_media_dir = mediatools.scan_directory(modified_root)
```


```python
# Compare file counts
len(media_dir.all_file_paths()), len(modified_media_dir.all_file_paths())
```




    (14, 16)




```python
# Compare the two directory structures
removed_files, added_files = media_dir.file_diff(modified_media_dir)
```


```python
# Files removed in modified version
removed_files
```




    {PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/cake_ceremony.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/family_portrait.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/construction.mkv'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/projects/timelapse/setup.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/shells.png'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/hiking.mp4'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/panorama.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/wildlife.jpg')}




```python
# Files added in modified version
added_files
```




    {PosixPath('/tmp/mediatools_modified_5f8_eqsp/family_events/birthday/cake_ceremony.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/family_events/family_portrait.png'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/projects/timelapse/construction.mkv'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/projects/timelapse/setup.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/beach/group_photo.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/beach/surfing.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/city/architecture.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/city/street_performance.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/mountains/drone_footage.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/mountains/hiking.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/mountains/panorama.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/mountains/wildlife.jpg'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/new_video.mp4')}




```python
# Find directories that have changes
changed_dirs = media_dir.get_changed_dirs(modified_media_dir)
```


```python
# Show directories with changes
[changed_dir.path.relative_to(demo_root) for changed_dir in changed_dirs]
```




    []



## Serialization and Data Export

### Converting MediaDir to Dictionary Formats


```python
# Convert to dictionary representation
media_dict = media_dir.to_dict()
```


```python
# Show top-level dictionary structure
{k: (list(v.keys()) if k == 'subdirs' and isinstance(v, dict) 
     else len(v) if isinstance(v, list) 
     else v) for k, v in media_dict.items()}
```




    {'path': '/tmp/mediatools_demo_c5unehg_',
     'videos': 0,
     'images': 0,
     'other_files': 0,
     'subdirs': 3,
     'meta': {}}



## Practical Use Cases and Workflows

### 1. Media Library Organization


```python
def analyze_media_library(media_dir):
    """Generate a comprehensive analysis of a media library"""
    
    analysis = {
        'total_directories': len(list(media_dir.path.rglob('*'))) if media_dir.path.exists() else 0,
        'total_videos': len(media_dir.all_video_files()),
        'total_images': len(media_dir.all_image_files()),
        'total_other_files': len(media_dir.all_file_paths()) - len(media_dir.all_media_paths()),
        'directory_breakdown': {}
    }
    
    # Analyze each subdirectory
    for subdir_name, subdir in media_dir.subdirs.items():
        analysis['directory_breakdown'][subdir_name] = {
            'videos': len(subdir.all_video_files()),
            'images': len(subdir.all_image_files()),
            'subdirectories': len(subdir.subdirs)
        }
    
    return analysis
```


```python
# Analyze our demo library
analysis = analyze_media_library(media_dir)
```


```python
# Show total counts
analysis['total_videos'], analysis['total_images'], analysis['total_other_files']
```




    (7, 7, 0)




```python
# Show directory breakdown
analysis['directory_breakdown']
```




    {'family_events': {'videos': 2, 'images': 2, 'subdirectories': 1},
     'vacation_2023': {'videos': 4, 'images': 4, 'subdirectories': 2},
     'projects': {'videos': 1, 'images': 1, 'subdirectories': 1}}



### 2. Batch Processing Preparation


```python
def prepare_batch_processing_list(media_dir, file_type='video'):
    """Prepare a list of files for batch processing with organized metadata"""
    
    if file_type == 'video':
        files = media_dir.all_video_files()
    elif file_type == 'image':
        files = media_dir.all_image_files()
    else:
        raise ValueError("file_type must be 'video' or 'image'")
    
    processing_list = []
    for file_obj in files:
        # Get relative path for organization
        rel_path = file_obj.path.relative_to(media_dir.path)
        
        # Determine category based on directory structure
        path_parts = rel_path.parts
        category = path_parts[0] if len(path_parts) > 1 else 'root'
        subcategory = path_parts[1] if len(path_parts) > 2 else None
        
        processing_list.append({
            'file_object': file_obj,
            'full_path': file_obj.path,
            'relative_path': rel_path,
            'category': category,
            'subcategory': subcategory,
            'filename': file_obj.path.name,
            'extension': file_obj.path.suffix.lower()
        })
    
    return processing_list
```


```python
# Prepare video processing list
video_batch = prepare_batch_processing_list(media_dir, 'video')
```


```python
# Show batch structure (first few items)
[(item['category'], item['subcategory'], item['filename']) for item in video_batch[:3]]
```




    [('family_events', 'birthday', 'cake_ceremony.mp4'),
     ('family_events', 'birthday', 'kids_playing.avi'),
     ('vacation_2023', 'mountains', 'drone_footage.mp4')]




```python
# Group by category for organized processing
by_category = {}
for item in video_batch:
    category = item['category']
    if category not in by_category:
        by_category[category] = []
    by_category[category].append(item)
```


```python
# Show files grouped by category
{category: len(items) for category, items in by_category.items()}
```




    {'family_events': 2, 'vacation_2023': 4, 'projects': 1}



### 3. Change Detection and Backup Verification


```python
def create_backup_verification_report(source_dir, backup_dir):
    """Create a detailed report comparing source and backup directories"""
    
    removed, added = source_dir.file_diff(backup_dir)
    
    report = {
        'backup_complete': len(removed) == 0 and len(added) == 0,
        'missing_from_backup': removed,
        'extra_in_backup': added,
        'source_stats': {
            'total_files': len(source_dir.all_file_paths()),
            'videos': len(source_dir.all_video_files()),
            'images': len(source_dir.all_image_files())
        },
        'backup_stats': {
            'total_files': len(backup_dir.all_file_paths()),
            'videos': len(backup_dir.all_video_files()),
            'images': len(backup_dir.all_image_files())
        }
    }
    
    return report
```


```python
# Compare original with modified directory (simulating backup check)
verification = create_backup_verification_report(media_dir, modified_media_dir)
```


```python
# Show backup verification results
verification['backup_complete'], verification['source_stats'], verification['backup_stats']
```




    (False,
     {'total_files': 14, 'videos': 7, 'images': 7},
     {'total_files': 16, 'videos': 9, 'images': 7})




```python
# Show missing files (first few)
list(verification['missing_from_backup'])[:3]
```




    [PosixPath('/tmp/mediatools_demo_c5unehg_/family_events/birthday/decorations.jpg'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/beach/sunset.mov'),
     PosixPath('/tmp/mediatools_demo_c5unehg_/vacation_2023/mountains/drone_footage.mp4')]




```python
# Show extra files (first few)
list(verification['extra_in_backup'])[:3]
```




    [PosixPath('/tmp/mediatools_modified_5f8_eqsp/family_events/birthday/kids_playing.avi'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/new_video.mp4'),
     PosixPath('/tmp/mediatools_modified_5f8_eqsp/vacation_2023/mountains/wildlife.jpg')]



## Cleanup

Let's clean up our temporary directories.


```python
# Clean up temporary directories
try:
    shutil.rmtree(demo_root)
    shutil.rmtree(modified_root)
    "Temporary directories cleaned up successfully."
except Exception as e:
    f"Cleanup warning: {e}"
```

## Summary

This notebook demonstrated the core functionality of the MediaDir system:

**Key Features Covered:**
- **Directory Scanning**: Automatically categorize media files by type
- **Recursive Navigation**: Easy access to nested directory structures
- **File Collections**: Organized access to videos, images, and other files
- **Batch Operations**: Process all files across directory trees
- **Change Detection**: Compare directory states for synchronization
- **Flexible Configuration**: Custom extensions and filtering options

**Integration Points:**
- VideoFile objects provide FFmpeg integration for video processing
- ImageFile objects enable image manipulation and analysis
- Serialization support for persistence and data export
- Path flexibility for both development and production scenarios

**Common Use Cases:**
1. **Media Library Management**: Organize and catalog large collections
2. **Batch Processing**: Process files systematically across directory trees
3. **Backup Verification**: Ensure completeness of media backups
4. **Change Monitoring**: Detect additions, removals, and modifications
5. **Website Generation**: Build galleries from filesystem structure

MediaDir serves as the foundational data structure that makes complex media workflows simple and intuitive, providing the organizational backbone for the entire mediatools ecosystem.
