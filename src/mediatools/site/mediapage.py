from __future__ import annotations
import typing
import pathlib
import dataclasses

#from .siteconfig import SiteConfig
from .siteconfig import SiteConfig
from .vidinfo import VidInfo
from .imginfo import ImgInfo
from ..util import format_memory, format_time, multi_extension_glob
 
#from ..vtools import ProbeError, FFMPEGCommandError


@dataclasses.dataclass(repr=False)
class MediaPage:
    '''Stores information about a directory of media files (recursive data structure).
    Properties:
        local_path: path to media page on filesystem
        config: configuration for site
        videos: info about videos
        clips: list of VidInfo objects
        images: list of ImgInfo objects
        subpages: list of MediaPage
    '''
    local_path: pathlib.Path
    config: SiteConfig
    videos: list[VidInfo]
    clips: list[VidInfo]
    images: list[ImgInfo]
    subpages: list[typing.Self] | None

    @classmethod
    def scan_directory(
        cls, 
        path: pathlib.Path, 
        config: SiteConfig, 
        recursive: bool = True, 
        verbose: bool = False,
        read_media: bool = True,
        i: int = 0, 
    ) -> VidInfo:
        '''Recursively scan a directory to collect information about the media files and subfolders.'''
        if verbose: print(path)

        if read_media:
            if verbose: print('\tscanning images')
            images = ImgInfo.scan_directory(path, config)
            if config.image_sort_key:
                images.sort(key=config.image_sort_key)
            if verbose: print(f'\t{len(images)=}')

            if verbose: print('\tscanning videos')
            vidinfo = VidInfo.scan_directory(path, config)
            if config.max_clip_duration is not None:
                clips = [vi for vi in vidinfo if vi.is_clip()]
                videos = [vi for vi in vidinfo if not vi.is_clip()]
            else:
                clips = []
                videos = vidinfo
            if config.video_sort_key:
                clips.sort(key=config.clip_sort_key)
                videos.sort(key=config.video_sort_key)
            if verbose: print(f'\t{len(videos)=}, {len(clips)=}')

        else:
            images = []
            videos = []
            clips = []

        if verbose: print('\tscanning subpages')
        if recursive and (config.max_depth is None or i < config.max_depth):
            subpages = list()
            for p in path.iterdir():
                if p.is_dir() and p != config.thumb_path:
                    page = cls.scan_directory(
                        path=p, 
                        config=config, 
                        verbose=verbose, 
                        read_media=read_media, 
                        i=i+1
                    )
                    subpages.append(page)

            if config.subpage_sort_key:
                subpages.sort(key=config.subpage_sort_key)
            if verbose: print(f'{len(subpages)=}')
        else:
            subpages = None

        return cls(
            local_path = path,
            config = config,
            videos = videos,
            clips = clips,
            images = images,
            subpages = subpages,
        )
    
    ############################################ writing the actual page ############################################
    def render_and_write(self, recursive: bool = True, verbose: bool = False) -> None:
        '''Render the page and write it to disk.'''
        if recursive and self.subpages is not None:
            for sp in self.subpages:
                sp.render_and_write(
                    recursive=recursive, 
                    verbose=verbose,
                )

        html_str = self.config.template.render(
            vid_thumbs = vid_thumbs,
            vids = vids, 
            clips = clips,
            imgs = imgs,
            child_paths = subpages, 
            video_width = self.config.video_width, 
            clip_width = self.config.clip_width,
            name = self.local_path.name,
        )

        # write the template
        pp = self.page_path()
        if verbose: print(f'saving {pp} with {len(self.images)} images, {len(self.videos)} vids, and {len(self.subpages)} subfolders')
        with pp.open('w') as f:
            f.write(html_str)
    
    ############################################ extract info ############################################
    def page_count(self) -> int:
        '''Count all media files in this page and subpages.'''
        if self.subpages is not None:
            return 1 + sum([sp.page_count() for sp in self.subpages])
        else:
            return 1

    ############################################ Dunder methods ############################################
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(videos={len(self.videos)}, clips={len(self.clips)}, images={len(self.images)}, subpages={len(self.subpages)})'
