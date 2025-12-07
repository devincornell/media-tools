from __future__ import annotations
import typing
import pathlib
import dataclasses
from pathlib import Path
#from .siteconfig import SiteConfig
#from .siteconfig import SiteConfig
#from .vidinfo import VidInfo
#from .imginfo import ImgInfo
#from ..util import format_memory, format_time, multi_extension_glob
from .video import VideoFile, VideoFiles, VideoFilesDict
from .video import VideoInfo

from .images import ImageFile, ImageFiles, ImageFilesDict

from .util import build_file_tree, hash_file
from .constants import VIDEO_FILE_EXTENSIONS, IMAGE_FILE_EXTENSIONS
from .file_base import FileBase, JSONable

def scan_directory(
        root_path: pathlib.Path | str,
        use_absolute: bool = True,
        video_ext: typing.Iterable[str] = VIDEO_FILE_EXTENSIONS,
        image_ext: typing.Iterable[str] = IMAGE_FILE_EXTENSIONS,
        ignore_path: typing.Callable[[Path],bool] | None = None,
    ) -> MediaDir:
    '''Recursively scan a directory and return a MediaDir instance.'''
    return MediaDir.from_path(
        root_path=root_path,
        use_absolute=use_absolute,
        video_ext=video_ext,
        image_ext=image_ext,
        ignore_path=ignore_path,
    )

@dataclasses.dataclass(repr=False)
class MediaDir:
    '''Stores information about a directory of media files (recursive data structure).
    Note: this type can represent either absolute or relative paths. When using absolute paths,
        the tree only spans a part of the full path.
    '''
    path: pathlib.Path
    _videos: VideoFilesDict
    _images: ImageFilesDict
    _other_files: NonMediaFileDict
    _subdirs: dict[str, typing.Self]
    parent: MediaDir | None = None
    meta: dict[str, JSONable] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_path(
        cls,
        root_path: pathlib.Path | str,
        use_absolute: bool = True,
        video_ext: typing.Iterable[str] = VIDEO_FILE_EXTENSIONS,
        image_ext: typing.Iterable[str] = IMAGE_FILE_EXTENSIONS,
        ignore_path: typing.Callable[[Path],bool] | None = None,
        #ingore_folder_names: set[str] | None = None,
        meta: dict | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from the current working directory.
        Args:
            root_path (pathlib.Path | str): The root directory path to scan.
            use_absolute (bool): Whether to use absolute paths. Defaults to True.
            video_ext (typing.Iterable[str]): Iterable of video file extensions to consider.
            image_ext (typing.Iterable[str]): Iterable of image file extensions to consider.
            ignore_path (typing.Callable[[Path],bool] | None): Optional function to ignore certain directories.
            meta (dict | None): Optional metadata dictionary to associate with the MediaDir.
        Returns:
            MediaDir: The created MediaDir instance.
        '''
        root_path = pathlib.Path(root_path)
        if not root_path.is_dir():
            raise FileNotFoundError(f'Root path not found: {root_path}')
        

        file_tree = build_file_tree(root_path)
        return cls.from_file_tree(
            data=file_tree,
            path=root_path if use_absolute else pathlib.Path('.'),
            video_ext=set([ext.lower() for ext in video_ext]),
            image_ext=set([ext.lower() for ext in image_ext]),
            check_exists=False,
            ignore_path=ignore_path,
            meta=meta if meta is not None else dict(),
        )

    @classmethod
    def from_file_tree(
        cls, 
        data: dict[str, dict|None],
        path: pathlib.Path | None,
        video_ext: typing.Iterable[str],
        image_ext: typing.Iterable[str],
        check_exists: bool = False,
        ignore_path: typing.Callable[[Path],bool] | None = None,
        meta: dict | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from a dictionary tree representation.
        '''

        videos = VideoFilesDict()
        images = ImageFilesDict()
        other_files = NonMediaFileDict()
        subdirs = dict()
        for k,v in data.items():
            child_path = path / k
            if isinstance(v, dict): # k represents a directory
                if ignore_path is None or not ignore_path(child_path):
                    subdirs[k] = cls.from_file_tree(
                        data=v, 
                        path=child_path,
                        video_ext=video_ext,
                        image_ext=image_ext, 
                        check_exists=check_exists,
                        ignore_path=ignore_path,
                    )

            elif v is None: # k is a file
                ext = child_path.suffix.lower()
                if ext in video_ext:
                    videos[child_path.name] = VideoFile.from_path(child_path, check_exists=check_exists)
                elif ext in image_ext:
                    images[child_path.name] = ImageFile.from_path(child_path, check_exists=check_exists)
                else:
                    other_files[child_path.name] = NonMediaFile.from_path(child_path, check_exists=check_exists)
            else:
                raise ValueError(f'Unexpected value type in data: {v}')
        
        o: typing.Self = cls(
            path = path,
            _videos = videos,
            _images = images,
            _other_files = other_files,
            _subdirs = subdirs,
            meta = meta if meta is not None else dict(),
        )
        for subdir in o.subdirs.values():
            subdir.parent = o

        return o

    def to_file_tree(self) -> dict[str, dict|None]:
        '''UNTESTED. Convert the MediaDir instance to a dictionary tree representation.
        '''
        tree: dict[str, dict|None] = dict()
        for subdir_name, subdir in self.subdirs.items():
            tree[subdir_name] = subdir.to_file_tree()
        for vf in self.videos:
            tree[vf.path.name] = None
        for imf in self.images:
            tree[imf.path.name] = None
        for of in self.other_files:
            tree[of.name] = None
        return tree
    
    @classmethod
    def from_dict(cls, data: dict) -> typing.Self:
        '''Create a MediaDir instance from a dictionary representation.
        '''
        o = cls(
            path = pathlib.Path(data.get('path', data.get('fpath'))),  # support both for backward compatibility
            _videos = VideoFilesDict.from_jsonable(data['videos']),
            _images = ImageFilesDict.from_jsonable(data['images']),
            _other_files = NonMediaFileDict.from_jsonable(data['other_files']),
            _subdirs = {(sdf := cls.from_dict(vd)).path.name: sdf for vd in data['subdirs']},
            meta = data['meta'],
        )
        for subdir in o.subdirs.values():
            subdir.parent = o

        return o
    
    def to_dict(self) -> dict:
        '''Convert the MediaDir instance to a dictionary representation.
        '''
        return {
            'path': str(self.path),
            'videos': self._videos.to_jsonable(),
            'images': self._images.to_jsonable(),
            'other_files': self._other_files.to_jsonable(),
            'subdirs': [v.to_dict() for k,v in self.subdirs.items()],
            'meta': self.meta,
        }


    def get_changed_dirs(self,
        other: typing.Self,
    ) -> list[typing.Self]:
        '''Compare this MediaDir to another and return a list of MediaDir instances that have changes.
        Changes include added or removed files in the directory or any of its subdirectories.
        '''
        this_fps = {fp.relative_to(self.path).parent for fp in self.all_file_paths()}
        other_fps = {fp.relative_to(other.path).parent for fp in other.all_file_paths()}
        diff = this_fps.symmetric_difference(other_fps)
        return [self._subdir(d) for d in diff if d in this_fps]

        changed_dirs = []
        for this_dir, other_dir in zip(self.all_dirs_iter(), other.all_dirs_iter()):
            this_fps, other_fps = set(this_dir.all_file_paths()), set(other_dir.all_file_paths())
            if this_fps != other_fps:
                changed_dirs.append(this_dir)
        return changed_dirs

    def file_diff(self,
        other: typing.Self,
    ) -> tuple[set[pathlib.Path],set[pathlib.Path]]:
        '''Compare this MediaDir to another and return sets of removed and added file paths (removed, added).
        Returns:
            tuple[set[pathlib.Path], set[pathlib.Path]]: A tuple containing two sets:
                - The first set contains file paths that are present in this MediaDir but not in the other (removed files).
                - The second set contains file paths that are present in the other MediaDir but not in this one (added files).
        '''
        this_fps, other_fps = set(self.all_file_paths()), set(other.all_file_paths())
        removed = this_fps - other_fps
        added = other_fps - this_fps
        return removed, added
    
    def all_file_paths(self) -> list[pathlib.Path]:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        return self.all_video_paths() + self.all_image_paths() + [of.path for of in self.other_files]
    
    def all_media_paths(self) -> list[pathlib.Path]:
        '''Get a list of all media files in the directory, including subdirectories.
        '''
        files = self.video_paths() + self.image_paths()
        for subdir in self.subdirs.values():
            files.extend(subdir.all_media_paths())
        return files
    
    def all_video_paths(self) -> list[pathlib.Path]:
        '''Get the paths of all video files.'''
        return [vf.path for vf in self.all_videos()]
    
    def all_image_paths(self) -> list[pathlib.Path]:
        '''Get the paths of all image files.'''
        return [ifp.path for ifp in self.all_images()]

    def all_dirs(self) -> list[typing.Self]:
        '''Get a list of all directories in the tree, including subdirectories.
        '''
        dirs = [self]
        for subdir in self.subdirs.values():
            dirs.extend(subdir.all_dirs())
        return dirs
    
    def all_dirs_iter(self) -> typing.Generator[typing.Self]:
        '''Get a list of all directories in the tree, including subdirectories.
        '''
        for subdir in self.subdirs.values():
            yield from subdir.all_dirs_iter()
        yield self

    def all_videos(self) -> VideoFiles:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        videos = self._videos.to_list()
        for subdir in self.subdirs.values():
            videos.extend(subdir.all_videos())
        return videos
    
    def all_images(self) -> ImageFiles:
        '''Get a list of all image files in the directory, including subdirectories.
        '''
        images = self._images.to_list()
        for subdir in self.subdirs.values():
            images.extend(subdir.all_images())
        return images
    
    def video_paths(self) -> list[pathlib.Path]:
        '''Get the paths of video files in this directory.'''
        return [vf.path for vf in self._videos.values()]

    def image_paths(self) -> list[pathlib.Path]:
        '''Get the paths of image files in this directory.'''
        return [ifp.path for ifp in self._images.values()]
    
    @property
    def videos(self) -> VideoFiles:
        '''Get the video files in this directory.'''
        return self._videos.to_list()
    
    @property
    def images(self) -> ImageFiles:
        '''Get the image files in this directory.'''
        return self._images.to_list()
    
    @property
    def other_files(self) -> list[NonMediaFile]:
        '''Get the non-media files in this directory.'''
        return list(self._other_files.values())
    
    @property
    def subdirs(self) -> dict[str, typing.Self]:
        '''Get the subdirectories in this directory.'''
        return self._subdirs
    
    def get_nonmedia(self, path: Path) -> NonMediaFile:
        '''Get a non-media file by filename.'''
        path = self._resolve_relative_path(path)
        try:
            return self._subdir(path.parent)._other_files[path.name]
        except KeyError:
            raise NonMediaFileNotFoundError(f'Non-media file "{path.name}" not found in directory "{path.parent}".')

    def get_image(self, path: Path) -> ImageFile:
        '''Get an image file by filename.'''
        path = self._resolve_relative_path(path)
        try:
            return self._subdir(path.parent)._images[path.name]
        except KeyError:
            raise ImageNotFoundError(f'Image file "{path.name}" not found in directory "{path.parent}".')

    def get_video(self, path: Path) -> VideoFile:
        '''Get a video file by filename.'''
        path = self._resolve_relative_path(path)
        try:
            return self._subdir(path.parent)._videos[path.name]
        except KeyError:
            raise VideoNotFoundError(f'Video file "{path.name}" not found in directory "{path.parent}".')
        
    def _resolve_relative_path(self, path: str|pathlib.Path) -> pathlib.Path:
        '''Resolve a path to be relative to this MediaDir's path.'''
        path = pathlib.Path(path)
        if self.path.is_absolute():
            if not path.is_absolute():
                raise ValueError(f'Path {path} is not absolute, but MediaDir path {self.path} is absolute.')
            elif not path.is_relative_to(self.path):
                raise ValueError(f'Path {path} is not relative to MediaDir path {self.path}.')
        else:
            if path.is_absolute():
                raise ValueError(f'Path {path} is not relative, but MediaDir path {self.path} is relative.')
            if not path.is_relative_to(self.path):
                raise ValueError(f'Path {path} is not relative to MediaDir path {self.path}.')
        return path.relative_to(self.path)

    def __getitem__(self, subdir_path: str|pathlib.Path) -> typing.Self:
        '''Get a subdirectory by key.'''
        return self._subdir(subdir_path)
        
    def subdir(self, *subdir_paths: str|pathlib.Path) -> typing.Self:
        '''Get a nested subdirectory by specifying a relative path or sequence of keys.'''
        return self._subdir(*subdir_paths)

    def _subdir(self, *subdir_paths: str|pathlib.Path) -> typing.Self:
        '''Get a nested subdirectory by specifying a relative path or sequence of keys.'''
        current = self
        for key in subdir_paths:
            key = pathlib.Path(key)
            for kp in key.parts:
                try:
                    current = current.subdirs[kp]
                except KeyError as e:
                    raise DirectoryNotFoundError(f'Subdirectory "{kp}" not found in the media directory.') from e
        return current
    
    def parents(self) -> list[typing.Self]:
        '''Get a list of parent MediaDir instances, starting from the immediate parent up to the root.'''
        parents = []
        current = self.parent
        while current is not None:
            parents.append(current)
            current = current.parent
        return parents
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.path}")'


class ImageNotFoundError:
    '''Raised when an image file is not found in a MediaDir.'''
    pass

class NonMediaFileNotFoundError:
    '''Raised when a non-media file is not found in a MediaDir.'''
    pass

class VideoNotFoundError:
    '''Raised when a video file is not found in a MediaDir.'''
    pass

class DirectoryNotFoundError:
    '''Raised when a directory is not found in a MediaDir.'''
    pass

@dataclasses.dataclass(frozen=True, repr=True, slots=True)
class NonMediaFile(FileBase):
    '''Represents a non-media file.'''
    path: pathlib.Path
    meta: dict[str, JSONable] = dataclasses.field(default_factory=dict)


class NonMediaFileDict(dict[Path, NonMediaFile]):
    '''Collection of non-media files.'''

    @classmethod
    def from_jsonable(cls, data: typing.List[dict]) -> typing.Self:
        '''Create NonMediaFileDict from JSONable list.'''
        return cls({(nmf := NonMediaFile.from_dict(nmfd)).path.name: nmf for nmfd in data})
    
    def to_jsonable(self) -> list[dict]:
        '''Convert NonMediaFileDict to JSONable list.'''
        return [nmf.to_dict() for nmf in self.values()]

    @classmethod
    def from_non_media_files(cls, non_media_files: typing.Iterable[NonMediaFile]) -> typing.Self:
        '''Create NonMediaFileDict from NonMediaFile list.'''
        return cls({nmf.path: nmf for nmf in non_media_files})

