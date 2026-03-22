import tqdm
import re
import dataclasses
import pathlib
import typing

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util



@dataclasses.dataclass
class FTVPath:
    name: str
    album_id: str
    video_id: str
    resolution: str

    @classmethod
    def from_filename(cls, filename: str) -> typing.Self:
        filename = str(filename).strip()
        # Regex pattern explanation:
        # ^(?P<name>.+)          : Match anything from start (name)
        # -(?P<album_id>\d{8})   : Match exactly 8 digits preceded by a hyphen
        # -(?P<video_id>\d{2})   : Match exactly 2 digits preceded by a hyphen
        # -(?P<resolution>[^.]+) : Match everything up to the dot (resolution)
        # \.mp4$                 : Match the file extension at the end
        regex_pattern = r"^(?P<name>.+)-(?P<album_id>\d{8})-(?P<video_id>\d{2})-(?P<resolution>[^.]+)\.mp4$"
        match = re.search(regex_pattern, filename)
        if match:
            return cls(**match.groupdict())
        raise ValueError(f"Filename '{filename}' does not match the expected pattern.")


if __name__ == "__main__":
    # List of filenames from the image
    root_path = pathlib.Path('/mnt/HugeHDD/dwhelper/ftv_website')
    mdir = mediatools.scan_directory(root_path=root_path)
    video_files = mdir.all_video_files()
    print(len(video_files))

    for vf in mdir.all_video_files():
        try:
            ftv_path = FTVPath.from_filename(vf.path.name)
        except ValueError as e:
            print(e)
        else:
            rel_path = pathlib.Path(f'{ftv_path.name}/{ftv_path.album_id}/{vf.path.name}')
            (root_path/rel_path).parent.mkdir(parents=True, exist_ok=True)
            vf.path.rename(root_path / rel_path)
            print(f'{ftv_path.name} -> {rel_path}')

