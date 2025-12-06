import tqdm
from pathlib import Path
#import pathlib
import jinja2
import PIL
import dataclasses

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import traceback



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate a media website from a directory.')
    parser.add_argument('source', type=Path, help='Root directory containing media files')
    parser.add_argument('destination', type=Path, help='Root directory for relative paths')
    args = parser.parse_args()



    #root = pathlib.Path('/mnt/MoStorage/gopro/')
    source = Path(args.source).resolve()
    dest = Path(args.destination).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    mdir = mediatools.scan_directory(source, use_absolute=True, ingore_folder_names=('_thumbs',))

    image_files = mdir.all_image_files()
    for imgf in tqdm.tqdm(image_files, ncols=100):
        rel_path = imgf.fpath.relative_to(source)
        dest_path = dest / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        img = imgf.read()
        #print(img.im.dtype)
        img.transform.resize((1000, -1)).to_rgb().as_ubyte().write(dest_path)


        
    