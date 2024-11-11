import sys
sys.path.append('..')
import pydevin

import pathlib


if __name__ == '__main__':
    base_path = pathlib.Path(f'/DataDrive/data/vichi_videos')
    out_folder = base_path.joinpath('cropped')
    out_folder.mkdir(exist_ok=True, parents=True)
    
    fnames = [
        base_path.joinpath('first_tape_xmas_2022/tape1_Dec2022.mp4'),
        base_path.joinpath('third_tape/tape3.mp4'),
    ]
    fpaths = [pathlib.Path(fn) for fn in fnames]
    
    for fpath in fpaths:
        out_fpath = out_folder.joinpath(fpath.name)
        info = pydevin.ffmpeg_probe(fpath)
        print(f'{fpath}: {info.res=}')
        pydevin.ffmpeg_thumb(fpath, out_folder.joinpath('thumb.png'))
        pydevin.ffmpeg_crop(fpath, out_fpath, height=1080, width=1617)
        #print(videotools.ffmpeg_probe(str(fpath)))
        print(fpath)
        print(out_fpath, '\n')




