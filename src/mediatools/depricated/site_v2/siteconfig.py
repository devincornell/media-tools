from __future__ import annotations
import pathlib
import dataclasses
import typing
import jinja2

if typing.TYPE_CHECKING:
    from .vidinfo import VidInfo
    from .imginfo import ImgInfo

DEFAULT_VIDEO_EXTENSIONS = ('mp4', 'mov', 'm4v', 'flv', 'ts', 'webm', 'mkv', 'avi', 'wmv', 'm4v', 'vob', '3gp', '3g2', 'm2ts', 'mts', 'mxf', 'ogv', 'ogg', 'rm', 'rmvb', 'flv', 'f4v', 'asf', 'webm', 'wtv', 'dvr-ms', 'm1v', 'm2v', 'm2t', 'm2ts', 'mpg', 'mpeg', 'mpe', 'mpv', 'mp2v', 'mp2', 'm2p', 'mp4v', 'mp4', 'm4p', 'm4v', 'mpg', 'mpeg', 'm2v', 'mp2v', 'mp2', 'm2p', 'mp4v', 'mp4', 'm4p', 'm4v', 'avi', 'wmv', 'asf', 'qt', 'mov', 'rm', 'rmvb', 'flv', 'f4v', 'swf', 'avchd', 'webm', 'wtv', 'dvr-ms', 'm1v', 'm2v', 'm2t', 'm2ts', 'mts', 'mxf', 'ogg', 'ogv', 'ogm', 'rm', 'rmvb', 'flv', 'f4v', 'asf', 'webm', 'wtv', 'dvr-ms', 'm1v', 'm2v', 'm2t', 'm2ts', 'mpg', 'mpeg', 'mpe', 'mpv', 'mp2v', 'mp2', 'm2p', 'mp4v', 'mp4', 'm4p', 'm4v', 'mpg', 'mpeg', 'm2v', 'mp2v', 'mp2', 'm2p', 'mp4v', 'mp4', 'm4p', 'm4v', 'avi', 'wmv', 'asf', 'qt', 'mov', 'rm', 'rmvb', 'flv', 'f4v', 'swf', 'avchd', 'webm', 'wtv', 'dvr-ms', 'm1v', 'm2')
DEFAULT_IMAGE_EXTENSIONS = ('png', 'gif', 'jpg', 'jpeg', 'svg', 'bmp', 'tiff', 'webp', 'ico', 'jpe', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k', 'jpf', 'jpx', 'jpm', 'mj2', 'svgz', 'tif', 'tiff', 'jfif', 'jp2', 'j2k')


@dataclasses.dataclass
class SiteConfig:
    '''Stores configuration for entire site.'''
    root_path: pathlib.Path | str
    
    template: jinja2.Template
    template_args: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    
    page_fname: str = 'index.html'
    
    thumb_extension: str = '.gif'
    thumb_path: pathlib.Path | str | None = None

    vid_extensions: tuple[str, ...] = DEFAULT_VIDEO_EXTENSIONS
    img_extensions: tuple[str, ...] = DEFAULT_IMAGE_EXTENSIONS

    video_sort_key: typing.Callable[[VidInfo], typing.Any] | None = None
    clip_sort_key: typing.Callable[[VidInfo], typing.Any] | None = None
    image_sort_key: typing.Callable[[ImgInfo], typing.Any] | None = None
    subpage_sort_key: typing.Callable[[typing.Self], typing.Any] | None = None

    max_clip_duration: int | None = 60

    max_depth: int | None = None

    def __post_init__(self) -> None:
        '''Post init checks and conversions.'''
        self.root_path = pathlib.Path(self.root_path)
        self.thumb_path = pathlib.Path(self.thumb_path) if self.thumb_path else self.root_path.joinpath('_thumbs/')

        self.thumb_path.relative_to(self.root_path) # raise error if not relative. Must be relative.
    
    def vid_to_thumb_path(self, vid_path: pathlib.Path) -> pathlib.Path:
        '''Get absolute or relative thumb path from vid path.'''
        with_suffix = vid_path.with_suffix(self.thumb_extension)

        
        thumb_fname = str(with_suffix).replace('/', '.')
        
        
        return self.thumb_path.joinpath(vid_path.stem + self.thumb_extension)
    
    def rel_vid_to_rel_thumb(self, vid_path: pathlib.Path) -> pathlib.Path:
        '''Get relative thumb path from vid path.'''
        return self.vid_to_thumb_path(vid_path).relative_to(self.root_path)

    #def thumb_path_rel(self) -> pathlib.Path:
    #    '''Thumb path relative to base path.'''
    #    fp = self.thumb_path_abs().relative_to(self.config.base_path)
    #    #print(fp)
    #    return fp

    #def thumb_path_abs(self) -> pathlib.Path:
    #    '''Absolute thumb path.'''
    #    rel_path = self.get_rel_path().with_suffix(self.config.thumb_extension)
    #    #print(f'=============')
    #    #print(rel_path)
    #    thumb_fname = str(rel_path).replace('/', '.')
    #    #print(thumb_fname)
    #    #print(self.config.thumb_base_path.joinpath(thumb_fname))
    #    return self.config.thumb_base_path.joinpath(thumb_fname)
    
    def abs_to_rel(self, fpath: pathlib.Path) -> pathlib.Path:
        '''Convert absolute path to relative path.'''
        return fpath.relative_to(self.root_path)
    
    def rel_to_abs(self, fpath: pathlib.Path) -> pathlib.Path:
        '''Convert relative path to absolute path.'''
        return self.root_path.joinpath(fpath)

    #video_width: int,
    #clip_width: int,
    #ideal_aspect: float,
    #clip_duration: int,
    #do_clip_autoplay: bool,

    #config = mediatools.site.SiteConfig(
    #    base_path = base_path,
    #    thumb_base_path = thumb_path,
    #    template = template,
    #    page_fname = 'web.html',
    #    vid_extensions = ('mp4', 'MOV', 'mov', 'MP4', 'flv', 'ts', 'webm'),
    #    img_extensions = ('png', 'gif', 'jpg', 'jpeg'),
    #    thumb_extension = '.gif',
    #    video_width = '85%',
    #    clip_width = '100%',
    #    ideal_aspect = 1.8,
    #    clip_duration = 60,
    #    do_clip_autoplay = False,
    #)
