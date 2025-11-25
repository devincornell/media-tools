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
    other_files: list[pathlib.Path]
    subdirs: list[typing.Self]
    parent: MediaDir | None = None

    @classmethod
    def from_path(
        cls,
        root_path: pathlib.Path | str,
        use_absolute: bool = True,
        video_ext: typing.Iterable[str] = VIDEO_FILE_EXTENSIONS,
        image_ext: typing.Iterable[str] = IMAGE_FILE_EXTENSIONS,
        ingore_folder_names: set[str] | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from the current working directory.
        '''
        root_path = pathlib.Path(root_path)
        if not root_path.is_dir():
            raise FileNotFoundError(f'Root path not found: {root_path}')

        file_tree = build_file_tree(root_path)        
        return cls.from_dict(
            data=file_tree,
            fpath=root_path if use_absolute else pathlib.Path('.'),
            video_ext=set([ext.lower() for ext in video_ext]),
            image_ext=set([ext.lower() for ext in image_ext]),
            check_exists=False,
            ingore_folder_names=set(ingore_folder_names) if ingore_folder_names is not None else set(),
        )

    @classmethod
    def from_dict(
        cls, 
        data: dict[str, dict|None],
        fpath: pathlib.Path | None,
        video_ext: typing.Iterable[str],
        image_ext: typing.Iterable[str],
        check_exists: bool = False,
        ingore_folder_names: set[str] | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from a dictionary tree representation.
        '''
        videos = VideoFiles()
        images = ImageFiles()
        other_files = list()
        subdirs = list()
        for k,v in data.items():
            child_path = fpath / k
            if isinstance(v, dict): # k represents a directory
                if str(k) not in ingore_folder_names:
                    subdirs.append(cls.from_dict(
                        data=v, 
                        fpath=child_path,
                        video_ext=video_ext,
                        image_ext=image_ext, 
                        check_exists=check_exists,
                        ingore_folder_names=ingore_folder_names,
                    ))

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
        )
        for subdir in o.subdirs:
            subdir.parent = o

        return o
    
    def all_dirs(self) -> list[typing.Self]:
        '''Get a list of all directories in the tree, including subdirectories.
        '''
        dirs = [self]
        for subdir in self.subdirs:
            dirs.extend(subdir.all_dirs())
        return dirs
    
    def all_files(self) -> list[pathlib.Path]:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        files = self.video_paths() + self.image_paths() + self.other_files
        for subdir in self.subdirs:
            files.extend(subdir.all_files())
        return files
    
    def all_media_files(self) -> list[pathlib.Path]:
        '''Get a list of all media files in the directory, including subdirectories.
        '''
        files = self.video_paths() + self.image_paths()
        for subdir in self.subdirs:
            files.extend(subdir.all_files())
        return files

    def all_video_files(self) -> VideoFiles:
        '''Get a list of all files in the directory, including subdirectories.
        '''
        videos = VideoFiles(self.videos)
        for subdir in self.subdirs:
            videos.extend(subdir.all_video_files())
        return videos
    
    def all_image_files(self) -> ImageFiles:
        '''Get a list of all image files in the directory, including subdirectories.
        '''
        images = ImageFiles(self.images)
        for subdir in self.subdirs:
            images.extend(subdir.all_image_files())
        return images
    
    def video_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of all video files.'''
        return [vf.fpath for vf in self.all_video_files()]
    
    def image_paths(self) -> list[pathlib.Path]:
        '''Get the fpaths of all image files.'''
        return [ifp.fpath for ifp in self.all_image_files()]


    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.fpath}")'
