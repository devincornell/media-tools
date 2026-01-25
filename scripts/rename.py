from pathlib import Path

if __name__ == '__main__':
    fp = Path('/mnt/HDDStorage/sys/')
    vid_paths = list(fp.rglob('*.mp4'))
    pre = 'Bang RealTeens - '
    print(len(vid_paths))

    for vp in vid_paths:
        if vp.stem.startswith(pre):
            print(vp)
            new_name = vp.name.replace(pre, '')
            new_fp = vp.with_name(new_name)
            print(new_fp)
            vp.rename(new_fp)
        #new_name = pre + vp.stem.replace('-', ' ').title() + vp.suffix
        #new_path = vp.with_name(new_name)
        #vp.rename(new_path)
        #print(f'Renamed: {vp.name} -> {new_name}')









