from __future__ import annotations
import jinja2
import typing
import pathlib
import dataclasses
import pprint
import subprocess
import os
import tqdm
import ffmpeg
import sys
import html
import urllib.parse
import PIL

from .siteconfig import SiteConfig
from .vidinfo import VidInfo
from .imginfo import ImgInfo
from ..util import format_memory, format_time

from ..video import ProbeError, FFMPEGError


from .util import *

@dataclasses.dataclass
class PageInfo:
    folder_fpath: pathlib.Path
    config: SiteConfig
    vid_infos: typing.List[VidInfo]
    img_infos: typing.List[ImgInfo]
    subpages: typing.List[PageInfo]
    
    ############################################ Constructors ############################################
    @classmethod
    def from_fpath(cls, fpath: pathlib.Path, config: SiteConfig, verbose: bool = False) -> PageInfo:
        '''Recursively create pageinfo tree starting at fpath.'''

        if verbose:
            print(f'entering {str(fpath)}')

        if not fpath.is_dir():
            raise ValueError(f'The provided path is not a directory: {fpath}')

        return cls(
            folder_fpath = fpath, 
            config = config,
            vid_infos = cls.scan_vid_infos(fpath, config),
            img_infos = cls.scan_img_infos(fpath, config),
            subpages = cls.scan_subpages(fpath, config=config, verbose=verbose),
        )
    
    @classmethod
    def scan_vid_infos(cls, fpath: pathlib.Path, config: SiteConfig) -> list[VidInfo]:
        img_infos = list()
        for fp in cls.base_get_fpaths(fpath, extensions=config.vid_extensions):
            try:
                img_infos.append(VidInfo.from_fpath(fp, config))
            except ProbeError as e:
                pass
        return img_infos
    
    @classmethod
    def scan_img_infos(cls, fpath: pathlib.Path, config: SiteConfig) -> list[ImgInfo]:
        img_infos = list()
        for fp in cls.base_get_fpaths(fpath, extensions=config.img_extensions):
            try:
                img_infos.append(ImgInfo.from_fpath(fp, config))
            except (ValueError, PIL.UnidentifiedImageError) as e:
                pass
        return img_infos

    @classmethod
    def scan_subpages(cls, fpath: pathlib.Path, config: SiteConfig, verbose: bool = False) -> list[PageInfo]:
        subpages = list()
        for cp in sorted(fpath.iterdir()):
            if cp.is_dir() and not cp.is_relative_to(config.thumb_base_path):
                try:
                    subpages.append(cls.from_fpath(fpath=cp, config=config, verbose=verbose))
                except ValueError:
                    print(f'Could not parse subdir {str(cp)}')
        return subpages

    @staticmethod
    def base_get_fpaths(fpath: pathlib.Path, extensions: tuple[str]|list[str]) -> typing.List[pathlib.Path]:
        all_paths = list()
        for ext in extensions:
            all_paths += list(sorted(fpath.glob(f'*.{ext}')))
        return all_paths

    ############################################ getting sorted and filtered infos ############################################
    def get_vid_info_dicts(self, 
        filter_cond: typing.Callable[[VidInfo],bool] = lambda x: True,
        sort_key: typing.Optional[typing.Callable[[VidInfo],float|str|int]] = None,
    ) -> list[VidInfo]:
        return self._iter_filter_sort_dict(
            elements=self.vid_infos,
            filter_cond=filter_cond,
            sort_key=sort_key,
        )
    
    def get_img_info_dicts(self, 
        filter_cond: typing.Callable[[ImgInfo],bool] = lambda x: True,
        sort_key: typing.Optional[typing.Callable[[ImgInfo],float|str|int]] = None,
    ) -> list[dict]:
        return self._iter_filter_sort_dict(
            elements=self.img_infos,
            filter_cond=filter_cond,
            sort_key=sort_key,
        )
    
    def get_subpages_dicts(self, 
        filter_cond: typing.Callable[[PageInfo],bool] = lambda x: True,
        sort_key: typing.Optional[typing.Callable[[PageInfo],float|str|int]] = None,
    ) -> list[dict]:
        return self._iter_filter_sort_dict(
            elements=self.subpages,
            filter_cond=filter_cond,
            sort_key=sort_key,
        )

    def _iter_filter_sort_dict(self, 
        elements: list[VidInfo] | list[ImgInfo] | list[PageInfo],
        filter_cond: typing.Callable[[VidInfo|ImgInfo|PageInfo],bool] = lambda x: True,
        sort_key: typing.Optional[typing.Callable[[VidInfo|ImgInfo|PageInfo],float|str|int]] = None,
    ) -> list[dict]:
        els = elements
        if filter_cond is not None:
            els = [vi for vi in els if filter_cond(vi)]
        if sort_key is not None:
            els = list(sorted(els, key=sort_key))
        return [e.info_dict() for e in els]

    ############################################ getting information ############################################
    def info_dict(self) -> typing.Dict[str, float]:
        '''Information about this page as a dictionary.'''
        return {
            'path': f'/{str(self.page_path_rel())}', 
            'path_rel': f'{str(self.page_path_rel())}', 
            'name': self.title, 
            'subfolder_thumb': parse_url('/'+str(self.get_best_thumb())),
            'num_vids': len(self.vid_infos),
            'num_imgs': len(self.img_infos),
            'num_subfolders': len(self.subpages),
            'files_size_str': format_memory(self.total_size()),
            'idx': fname_to_id(self.folder_fpath.name),
        }
    
    def page_path(self) -> pathlib.Path:
        return self.folder_fpath.joinpath(self.config.page_fname)
    
    def page_path_rel(self) -> pathlib.Path:
        '''Get the relative page path for use in links.'''
        return self.folder_fpath_rel.joinpath(self.config.page_fname)
    
    @property
    def title(self) -> str:
        return fname_to_title(self.folder_fpath.name)
    
    @property
    def folder_fpath_rel(self) -> pathlib.Path:
        return self.folder_fpath.relative_to(self.config.base_path)
    
    @property
    def has_childs(self) -> bool:
        return any([self.total_vids > 0, self.total_imgs > 0, self.num_subpages > 0])
    
    def total_vids(self) -> int:
        '''Recursively count videos in this and all subdirectories.'''
        return len(self.vid_infos) + sum([sp.total_vids() for sp in self.subpages])
    
    def total_imgs(self) -> int:
        '''Recursively count videos in this and all subdirectories.'''
        return len(self.img_infos) + sum([sp.total_imgs() for sp in self.subpages])
    
    def total_size(self) -> int:
        '''Recursively count size of all media files.'''
        return self.data_size() + sum([sp.total_size() for sp in self.subpages])
    
    def data_size(self) -> int:
        '''Size of all videos and images in this directory.'''
        return sum(v.file_size() for v in self.vid_infos) + sum(im.file_size() for im in self.img_infos)
    
    def all_vid_infos(self) -> typing.List[VidInfo]:
        '''Get video infos of this directory and all subdirectories.'''
        return self.vid_infos + [vi for sp in self.subpages for vi in sp.all_vid_infos()]

    def all_img_infos(self) -> typing.List[ImgInfo]:
        '''Get image infos of this directory and all subdirectories.'''
        return self.img_infos + [ii for sp in self.subpages for ii in sp.all_img_infos()]

    def make_thumbs(self, verbose: bool = False) -> None:
        vis = self.vid_infos
        if verbose:
            print(f'making thumbns in {self.folder_fpath}')
            vis = tqdm.tqdm(vis, ncols=80)
        
        for vi in vis:
            try:
                vi.make_thumb()
            except FFMPEGError as e:
                pass
        
    def get_best_thumb(self) -> pathlib.Path:
        '''Get best thumbnail from videos in all fubfolders.'''
        vis = self.all_vid_infos()
        if len(vis) == 0:
            imgs = self.all_img_infos()
            if len(imgs):
                return imgs[0].path_rel()
            else:
                return None
        mvi = min(vis, key=lambda sp: abs(sp.aspect() - self.config.ideal_aspect))
        return mvi.thumb_path_rel()
    
    ################################## DEPRICATED ##################################
    def depric_vid_info_dicts(self) -> typing.List[typing.Dict[str, str]]:
        '''Get information dictionaries of all videos.'''
        infos = list()
        for vi in self.vid_infos:
            try:
                infos.append(vi.info_dict())
            except FileNotFoundError:
                pass
        return infos

    def depric_img_info_dicts(self) -> typing.List[typing.Dict[str, str]]:
        '''Get information dictionaries of all videos.'''
        return [ii.info_dict() for ii in self.img_infos]

    def depric_subpage_info_dicts(self) -> typing.List[typing.Dict[str, str]]:
        '''Get information dictionaries of all subpages.'''
        return [sp.info_dict() for sp in self.subpages]

