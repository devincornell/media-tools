import tqdm
import re
import dataclasses
import pathlib
import typing
import datetime

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import util


if __name__ == "__main__":
    # List of filenames from the image
    src_path = pathlib.Path('/mnt/HugeHDD/gopro/latest_from_dwhelper/')
    dest_root = pathlib.Path('/mnt/HugeHDD/gopro/gopro_raw_organized')
    mdir = mediatools.scan_directory(root_path=src_path)
    video_files = mdir.all_video_files()
    print(len(video_files))

    for vf in video_files:
        try:
            probe = vf.probe()
            creation_time = probe.tags['creation_time']
        except (KeyError,mediatools.ffmpeg.ProbeError):
            print(f'{vf.path.name}: None')
            continue
        else:
            dt = datetime.datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%S.%fZ")
            day_str = dt.strftime('%Y-%m-%d')
            dt_str = dt.strftime('%Y-%m-%d_%H-%M-%S')
            dest_path = dest_root / f'{day_str}' / f'{dt_str}-{vf.path.name}'
            if not dest_path.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                vf.path.rename(dest_path)
            print(f'{vf.path.name} -> {dest_path}')
            
            


        #print(probe.tags)
        #break