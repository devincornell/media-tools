from __future__ import annotations
import jinja2
import typing
import pathlib

import sys
sys.path.append('../src')
import mediatools

if __name__ == '__main__':
    clip_duration = 1  # seconds
    random_seed = 0
    clip_ratio = 30  # seconds per clip
    #output_filename = 'montage.mp4'
    root = pathlib.Path('/AddStorage/personal/dwhelper/')
    
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True)
    for i, dir in enumerate(mdir.all_dirs()):
        if len(dir.all_video_files()) > 0 or len(dir.subdirs) > 0:
            print(f'{dir.fpath}: {len(dir.all_media_files())} files, {len(dir.subdirs)} subdirs')

            mediatools.create_montage(
                video_directory=str(dir.fpath),
                clip_duration=clip_duration,
                output_filename=f'montage-{i}.mp4',
                random_seed=random_seed,
                clip_ratio=clip_ratio,
            )

