import collections
import functools
import typing
import argparse
import os
import sys
import shutil
import random
from pathlib import Path
import subprocess
import tempfile
import tqdm
import pathlib
import multiprocessing
import hashlib
import sys

sys.path.append('../src/')
sys.path.append('src/')
import mediatools



if __name__ == "__main__":
    root_path = pathlib.Path('/mnt/MoStorage/shows/Bleach_Downscaled/')
    output_dir = pathlib.Path('/mnt/MoStorage/shows/Bleach_Upscaled/')

    mdir = mediatools.scan_directory(root_path)
    all_videos = list(sorted(mdir.all_videos(), key=lambda vf: str(vf.path.name), reverse=True))
    print(len(all_videos))

    for vf in tqdm.tqdm(all_videos, ncols=80):
        relative_path = vf.path.relative_to(root_path)
        output_path = output_dir / relative_path.parent
        output_path.mkdir(parents=True, exist_ok=True)

        output_file = (output_path / relative_path.name).with_stem(relative_path.stem + '_1080p_upscaled')

        if False:
            'ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i Bleach-00168.mp4 -vf "scale_cuda=1280:720" -c:v h264_nvenc -rc constqp -qp 18 -c:a copy -c:s copy Bleach-00168_720p.mp4'
            result = mediatools.ffmpeg.FFMPEG(
                inputs = [
                    mediatools.ffmpeg.ffinput(
                        vf.path,
                        hwaccel='cuda',
                        other_args = [('hwaccel_output_format', 'cuda')]
                    )
                ],
                outputs = [
                    mediatools.ffmpeg.ffoutput(
                        output_file,
                        v_f='scale_cuda=1280:720',
                        c_v='h264_nvenc',
                        preset = 'slow',
                        c_a='copy',
                        c_s='copy',
                        y=True,
                        other_args=[('rc','constqp'), ('qp',18)]
                    )
                ],
            ).run()

        else:
            if not output_file.exists():
                print('\nUpscaling ', vf.path.name, ' to ', output_file.name)
                mediatools.ai.run_upscale(vf.path, output_file)
            else:
                print('\nSkipping existing file ', output_file.name)