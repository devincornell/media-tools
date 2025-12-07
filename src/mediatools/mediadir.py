from __future__ import annotations
import typing
import pathlib
import dataclasses

#from .siteconfig import SiteConfig
#from .siteconfig import SiteConfig
#from .vidinfo import VidInfo
#from .imginfo import ImgInfo
#from ..util import format_memory, format_time, multi_extension_glob
from .video import VideoFile, VideoFiles
from .images import ImageFile, ImageFiles
from .util import build_file_tree, hash_file
from .constants import VIDEO_FILE_EXTENSIONS, IMAGE_FILE_EXTENSIONS

def scan_directory(
        root_path: pathlib.Path | str,
        use_absolute: bool = True,
        video_ext: typing.Iterable[str] = VIDEO_FILE_EXTENSIONS,
        image_ext: typing.Iterable[str] = IMAGE_FILE_EXTENSIONS,
        ingore_folder_names: set[str] | None = None,
    ) -> MediaDir:
    '''Recursively scan a directory and return a MediaDir instance.'''
    return MediaDir.from_path(
        root_path=root_path,
        use_absolute=use_absolute,
        video_ext=video_ext,
        image_ext=image_ext,
        ingore_folder_names=ingore_folder_names,
    )

@dataclasses.dataclass(repr=False)
class MediaDir:
    '''Stores information about a directory of media files (recursive data structure).
    Note: this type can represent either absolute or relative paths. When using absolute paths,
        the tree only spans a part of the full path.
    '''
    fpath: pathlib.Path
    videos: VideoFiles
    images: ImageFiles
    other_files: list[NonMediaFile]
    subdirs: dict[str, typing.Self]
    parent: MediaDir | None = None
    meta: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def from_path(
        cls,
        root_path: pathlib.Path | str,
        use_absolute: bool = True,
        video_ext: typing.Iterable[str] = VIDEO_FILE_EXTENSIONS,
        image_ext: typing.Iterable[str] = IMAGE_FILE_EXTENSIONS,
        ingore_folder_names: set[str] | None = None,
        meta: dict | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from the current working directory.
        '''
        root_path = pathlib.Path(root_path)
        if not root_path.is_dir():
            raise FileNotFoundError(f'Root path not found: {root_path}')

        file_tree = build_file_tree(root_path)
        return cls.from_file_tree(
            data=file_tree,
            fpath=root_path if use_absolute else pathlib.Path('.'),
            video_ext=set([ext.lower() for ext in video_ext]),
            image_ext=set([ext.lower() for ext in image_ext]),
            check_exists=False,
            ingore_folder_names=set(ingore_folder_names) if ingore_folder_names is not None else set(),
            meta=meta if meta is not None else dict(),
        )

    @classmethod
    def from_file_tree(
        cls, 
        data: dict[str, dict|None],
        fpath: pathlib.Path | None,
        video_ext: typing.Iterable[str],
        image_ext: typing.Iterable[str],
        check_exists: bool = False,
        ingore_folder_names: set[str] | None = None,
        meta: dict | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from a dictionary tree representation.
        '''
        videos = VideoFiles()
        images = ImageFiles()
        other_files = list()
        subdirs = dict()
        for k,v in data.items():
            child_path = fpath / k
            if isinstance(v, dict): # k represents a directory
                if str(k) not in ingore_folder_names:
                    subdirs[k] = cls.from_file_tree(
                        data=v, 
                        fpath=child_path,
                        video_ext=video_ext,
                        image_ext=image_ext, 
                        check_exists=check_exists,
                        ingore_folder_names=ingore_folder_names,
                    )

            elif v is None: # k is a file
                ext = child_path.suffix.lower()
                if ext in video_ext:
                    videos.append(VideoFile.from_path(child_path, check_exists=check_exists))
                elif ext in image_ext:
                    images.append(ImageFile.from_path(child_path, check_exists=check_exists))
                else:
                    other_files.append(child_path)

            else:
                raise ValueError(f'Unexpected value type in data: {v}')
        
        o = cls(
            fpath = fpath,
            videos = videos,
            images = images,
            other_files = other_files,
            subdirs = subdirs,
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
            tree[vf.fpath.name] = None
        for imf in self.images:
            tree[imf.fpath.name] = None
        for of in self.other_files:
            tree[of.name] = None
        return tree
    
    @classmethod
    def from_dict(cls, data: dict) -> typing.Self:
        '''Create a MediaDir instance from a dictionary representation.
        '''
        videos = VideoFiles([VideoFile.from_dict(vfd) for vfd in data['videos']])
        images = ImageFiles([ImageFile.from_dict(imfd) for imfd in data['images']])
        other_files = [NonMediaFile(pathlib.Path(of)) for of in data['other_files']]
        subdirs = {k: cls.from_dict(vd) for k,vd in data['subdirs'].items()}
        meta = data['meta']

        o = cls(
            fpath = pathlib.Path(data['fpath']),
            videos = videos,
            images = images,
            other_files = other_files,
            subdirs = subdirs,
            meta = meta,
        )
        for subdir in o.subdirs.values():
            subdir.parent = o

        return o
    
    def to_dict(self) -> dict:
        '''Convert the MediaDir instance to a dictionary representation.
        '''
        return {
            'fpath': str(self.fpath),
            'videos': [vf.to_dict() for vf in self.videos],
            'images': [imf.to_dict() for imf in self.images],
            'other_files': [str(of) for of in self.other_files],
            'subdirs': {k: v.to_dict() for k,v in self.subdirs.items()},
            'meta': self.meta,
        }

    def get_changed_dirs(self,
        other: typing.Self,
    ) -> list[typing.Self]:
        '''Compare this MediaDir to another and return a list of MediaDir instances that have changes.
        Changes include added or removed files in the directory or any of its subdirectories.
        '''
        this_fps = {fp.relative_to(self.fpath).parent for fp in self.all_file_paths()}
        other_fps = {fp.relative_to(other.fpath).parent for fp in other.all_file_paths()}
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
    
    def all_file_paths(self) -> list[pathlib.Path]:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        files = self.video_paths() + self.image_paths() + self.other_files
        for subdir in self.subdirs.values():
            files.extend(subdir.all_file_paths())
        return files
    
    def all_media_files(self) -> list[pathlib.Path]:
        '''Get a list of all media files in the directory, including subdirectories.
        '''
        files = self.video_paths() + self.image_paths()
        for subdir in self.subdirs.values():
            files.extend(subdir.all_file_paths())
        return files

    def all_video_files(self) -> VideoFiles:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        videos = VideoFiles(self.videos)
        for subdir in self.subdirs.values():
            videos.extend(subdir.all_video_files())
        return videos
    
    def all_image_files(self) -> ImageFiles:
        '''Get a list of all image files in the directory, including subdirectories.
        '''
        images = ImageFiles(self.images)
        for subdir in self.subdirs.values():
            images.extend(subdir.all_image_files())
        return images
    
    def all_video_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of all video files.'''
        return [vf.fpath for vf in self.all_video_files()]
    
    def all_image_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of all image files.'''
        return [ifp.fpath for ifp in self.all_image_files()]
    
    def video_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of video files in this directory.'''
        return [vf.fpath for vf in self.videos]

    def image_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of image files in this directory.'''
        return [ifp.fpath for ifp in self.images]

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
                    raise KeyError(f'Subdirectory "{kp}" not found in the media directory.') from e
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
        return f'{self.__class__.__name__}("{self.fpath}")'


@dataclasses.dataclass(frozen=True)
class NonMediaFile:
    fpath: pathlib.Path
