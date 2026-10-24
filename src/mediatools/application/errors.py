class GalleryError(Exception):
    '''Base class for gallery use-case errors.'''


class DirectoryNotIndexedError(GalleryError):
    '''The requested directory has no index document.'''


class MediaFileNotFoundError(GalleryError):
    '''The requested media or thumbnail file does not exist.'''


class PathOutsideRootError(GalleryError):
    '''The requested relative path escapes the gallery root.'''


class InvalidJobRequestError(GalleryError):
    '''A job submission was rejected (bad path, disabled feature, ...).'''


class UploadError(GalleryError):
    '''Base class for upload failures; `status_code` is the HTTP status the API reports.'''

    status_code = 400


class InvalidUploadError(UploadError):
    '''The destination or file path is not acceptable.'''

    status_code = 422


class UploadConflictError(UploadError):
    '''A file already exists at the target path.'''

    status_code = 409


class UploadIncompleteError(UploadError):
    '''The body ended before the declared size was received.'''

    status_code = 400


class UploadPermissionError(UploadError):
    '''The server user isn't allowed to write there.'''

    status_code = 403


class UploadStorageFullError(UploadError):
    '''The disk is full.'''

    status_code = 507
