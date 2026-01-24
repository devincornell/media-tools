import tempfile
import datetime
from pathlib import Path
import requests

import sys
sys.setrecursionlimit(500)

#sys.path.append('../src')
sys.path.append('src')
import mediatools


def test_media_dirs(test_dir: Path = Path('/mnt/HugeHDD/gopro/compilations')):
    
    mdir = mediatools.scan_directory(test_dir)
    video_files = mdir.all_videos()
    images = mdir.all_images()

    for imf in images:
        imm = imf.read_meta()
        print(imm.path, imm.stat.size_str(), imm.res)

    for vf in video_files:
        vfm = vf.read_meta()
        print(vfm.path, vfm.stat.size_str(), vfm.resolution_str(), vfm.duration_str())




if __name__ == '__main__':
    test_media_dirs()

