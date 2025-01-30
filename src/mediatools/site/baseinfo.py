from __future__ import annotations
import pathlib
from .siteconfig import SiteConfig



class BaseInfo:
    fpath: pathlib.Path
    config: SiteConfig

    #@classmethod
    #def from_path(self, *args, **kwargs):
    #    raise NotImplementedError(f'This method should have been implemented by subclass.')
    
    #def get_rel_path(self) -> pathlib.Path:
    #    '''Path relative to the original base path.'''
    #    return self.fpath.relative_to(self.config.base_path)    

    def rel_path(self) -> pathlib.Path:
        '''Path relative to the original base path.'''
        return self.config.abs_to_rel(self.fpath)#self.fpath.relative_to(self.config.base_path)

    def file_size(self) -> int:
        return self.fpath.stat().st_size



