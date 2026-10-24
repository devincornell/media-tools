class GalleryError(Exception):
    '''Base class for gallery use-case errors.'''


class DirectoryNotIndexedError(GalleryError):
    '''The requested directory has no index document.'''


class MediaFileNotFoundError(GalleryError):
    '''The requested media or thumbnail file does not exist.'''


class PathOutsideRootError(GalleryError):
    '''The requested relative path escapes the gallery root.'''
