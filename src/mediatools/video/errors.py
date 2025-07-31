import typing
from pathlib import Path


class VideoFileDoesNotExistError(Exception):
    fpath: Path
    _msg_template: str = 'This video file does not exist: {fp}'

    @classmethod
    def from_fpath(cls, fpath: Path) -> typing.Self:
        o = cls(cls._msg_template.format(fp=str(fpath)))
        o.fpath = fpath
        return o
