import glob
import typing
import pprint
import tempfile
import datetime
import tqdm
import random
import pathlib

import sys
sys.path.append('..')
import pydevin

def get_new_filename(fp: pathlib.Path) -> pathlib.Path:
    return fp.with_name(fp.stem[:249] + "-c" + fp.suffix)

def bitrate_calculator(info: pydevin.vtools.ProbeInfo) -> int:
    # 1920x1080: 2073600
    # 1280x720: 921600
    if info.video.pixels > 3000000: # ~80% of 2160p
        return 400000
    if info.video.pixels > 1573600: # ~75% of 1080p
        return 300000
    elif info.video.pixels > 751600: # ~75% of 720p
        return 200000
    else:
        return 100000


def compress_video(
    vf: pydevin.vtools.VideoFile,
    new_fpath: pathlib.Path,
    bitrate_cutoff: int,
    crf_increment: int = 5,
    verbose: bool = True,
    delete_errored_files: bool = False,
) -> bool:
    try:
        try_crf = 25
        while True:
            nvid = vf.compress(
                output_fname = new_fpath,
                crf = try_crf,
                overwrite = True,
            )
            if verbose:
                print(f'\ttried crf: {try_crf}; {vf.probe().file_bitrate/1000:6.1f} kbps ({pydevin.util.format_memory(vf.probe().size)}) --> '
                    f'{nvid.probe().file_bitrate/1000:6.1f} kbps ({pydevin.util.format_memory(nvid.probe().size)})')
            if nvid.probe().file_bitrate < bitrate_cutoff:
                return True
            else:
                try_crf += crf_increment
                if verbose:
                    print(f'\t{nvid.probe().file_bitrate/1000:5.1f} kbps > target '
                        f'({bitrate_cutoff/1000:5.1f} kbps). increasing crf to {try_crf}')
    except pydevin.vtools.FFMPEGCommandError as e:
        new_fpath.unlink(missing_ok=True)
        if verbose:
            print(f'\n\terror encountered. {str(new_fpath)}')
        if delete_errored_files:
            vf.fpath.unlink(missing_ok=True)
            print(f'\n\tdeleting {str(vf.fpath)}')
        #raise e from e

def compress_all_files(
    root_fpath: str = '/home/devin/personal/dwhelper/',
    #root_fpath: str = '/AddStorage/personal/dwhelper/',
    crf_increment: int = 5,
    do_compress: bool = True,
    delete_old: bool = True,
    samp_size: typing.Optional[int] = None,
    delete_errored_files: bool = True,
):
    #sfp = pathlib.Path(fpath_glob)
    #vfs = [pydevin.VideoFile(fn) for fn in glob.glob(fpath_glob)]
    cand_vfs = pydevin.vtools.VideoFile.from_rglob(root_fpath)
    print(f'found {len(cand_vfs)} video files.')
    
    if samp_size is not None:
        random.seed(0)
        cand_vfs = random.sample(cand_vfs, samp_size)

    ivfs: list[tuple[pydevin.vtools.ProbeInfo, pydevin.vtools.VideoFile]] = list()
    for vf in tqdm.tqdm(cand_vfs):
        #print(vf)
        try:
            info = vf.probe()
        except pydevin.vtools.ProbeError as e:
            print(f'\n\tcould not probe {str(vf.fpath)}')
            if delete_errored_files:
                vf.fpath.unlink(vf.fpath)
                print(f'\n\tdeleted file.')
        else:
            max_bitrate = bitrate_calculator(info)
            
            if info.file_bitrate > max_bitrate and not vf.fpath.stem.endswith('-c'):

                new_fpath = get_new_filename(vf.fpath)
                if new_fpath.exists():
                    pass # idk what to do if file already exists

                if do_compress:
                    print(f'\ncompressing: {str(vf.fpath)}')
                    result = compress_video(
                        vf = vf, 
                        new_fpath=new_fpath, 
                        bitrate_cutoff=max_bitrate,
                        crf_increment = crf_increment,
                        delete_errored_files = delete_errored_files,
                    )
                    if result and delete_old:
                        vf.fpath.unlink()
                else:
                    print(f'compressable video found: {str(vf.fpath)}')
                
                ivfs.append((info, vf))

    print(f'{len(ivfs)/len(cand_vfs)*100}% above bitrate')

if __name__ == '__main__':
    compress_all_files()
