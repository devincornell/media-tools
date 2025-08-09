import pathlib
import jinja2
import PIL
import dataclasses

import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
import traceback




def make_compilations_recursive(mdir: mediatools.MediaDir, root: pathlib.Path):
    '''Make pages for the media directory and its subdirectories.'''
    rel_path = mdir.fpath.relative_to(root)

    # depth-first traversal
    for sdir in sorted(mdir.subdirs, key=lambda sd: sd.fpath.name):
        make_compilations_recursive(sdir, root)

    out_path = mdir.fpath / f'-montage_{str(rel_path).replace('/','.')}.mp4'
    if out_path.is_file():
        out_path.unlink()

    if len(mdir.videos) > 0:
        try:
            return mediatools.functions.create_montage(
                video_directory = str(mdir.fpath),
                clip_duration = 1,
                output_filename = str(out_path),
                random_seed = 0,
                width = 1920,
                height = 1080,
                fps = 30,
                clip_ratio = 30,
                supported_extensions = ("*.MP4", "*.mp4", "*.mov", "*.avi", "*.mkv", "*.flv"),
            )
        except Exception as e:
            print(f"Error processing directory: {mdir.fpath}")
            print(f"Exception: {e}")
            traceback.print_exc()



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate a media website from a directory.')
    parser.add_argument('root', type=pathlib.Path, help='Root directory containing media files')
    args = parser.parse_args()

    #root = pathlib.Path('/mnt/MoStorage/gopro/')
    root = pathlib.Path(args.root).resolve()
    mdir = mediatools.MediaDir.from_path(root, use_absolute=True, ingore_folder_names=('_thumbs',))
    make_compilations_recursive(root=root, mdir=mdir)

