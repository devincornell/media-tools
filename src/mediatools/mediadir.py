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
from .util import build_file_tree

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
        video_ext: typing.Iterable[str] = ('.mp4', '.mov', '.avi', '.mkv', '.webm'),
        image_ext: typing.Iterable[str] = ('.jpg', '.jpeg', '.png', '.gif'),
        ingore_folder_names: typing.Iterable[str] = ('_thumbs',),
    ) -> typing.Self:
        '''Create a MediaDir instance from the current working directory.
        '''
        file_tree = build_file_tree(root_path)        
        return cls.from_dict(
            data=file_tree,
            fpath=root_path if use_absolute else None,
            video_ext=video_ext,
            image_ext=image_ext,
            check_exists=False,
        )

    @classmethod
    def from_dict(
        cls, 
        data: dict[str, dict|None],
        fpath: pathlib.Path | None = None,
        video_ext: typing.Iterable[str] = ('.mp4', '.mov', '.avi', '.mkv', '.webm'),
        image_ext: typing.Iterable[str] = ('.jpg', '.jpeg', '.png', '.gif'),
        check_exists: bool = True,
        ingore_folder_names: set[str] | None = None,
    ) -> typing.Self:
        '''Create a MediaDir instance from a dictionary representation.
        '''
        fpath = pathlib.Path(fpath) if fpath else pathlib.Path('.')
        video_ext = set([ext.lower() for ext in video_ext])
        image_ext = set([ext.lower() for ext in image_ext])
        ingore_folder_names = set(ingore_folder_names) if ingore_folder_names else set()

        videos = VideoFiles()
        images = ImageFiles()
        other_files = list()
        subdirs = list()
        for k,v in data.items():
            child_path = fpath / k

            if isinstance(v, dict) and k not in ingore_folder_names: # k represents a directory
                subdirs.append(cls.from_dict(
                    data=v, 
                    fpath=child_path,
                    video_ext=video_ext,
                    image_ext=image_ext, 
                    check_exists=check_exists,
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
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}("{self.fpath}")'
