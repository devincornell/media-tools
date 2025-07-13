import pathlib

import sys
sys.path.append('../src')
import mediatools


def make_site(root: pathlib.Path):
    thumb_folder = root / '_thumbs'
    mdir = mediatools.MediaDir.from_path(root, use_absolute=False, ingore_folder_names=('_thumbs',))
    print(make_pages(mdir))

def make_pages(mdir: mediatools.MediaDir):
    print(mdir.fpath)
    for sdir in mdir.subdirs:
        make_pages(sdir)


if __name__ == '__main__':

    # Example usage
    root = pathlib.Path('/AddStorage/personal/dwhelper/')
    make_site(root)
    


