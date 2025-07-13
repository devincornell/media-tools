import pathlib

import sys
sys.path.append('../src')
import mediatools


def make_site(root: pathlib.Path):
    thumb_folder = root / '_thumbs'
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=('_thumbs',))
    make_pages(mdir)

def make_pages(mdir: mediatools.MediaDir):
    print(mdir.fpath)
    for sdir in mdir.subdirs:
        make_pages(sdir)

    for vfile in mdir.videos:
        info = vfile.get_info()
        print(info.size_str(), info.vfile.fpath)

    for ifile in mdir.images:
        info = ifile.get_info()
        print(info.size_str(), info.ifile.fpath)


if __name__ == '__main__':

    # Example usage
    root = pathlib.Path('/AddStorage/personal/dwhelper/')
    make_site(root)
    


