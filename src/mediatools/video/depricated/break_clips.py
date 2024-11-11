import datetime
import pathlib
import pydevin.vtools.depricated as depricated_methods

base_path = pathlib.Path(f'/DataDrive/data/vichi_videos')

video_splices = {
    #base_path.joinpath('first_tape_xmas_2022/tape1_Dec2022.mp4'): [
    #    ('vichi bday', (0,4), (4,2)),
    #    ('dad dj basketball', (4,2), (8,29)),
    #    ('random dad', (8,29), (10,8)),
    #    ('dj cursive', (10,9), (13,42)),
    #    ('dj music', (13,43), (15,11)),
    #    ('radh dj band', (15,11), (16,31)),
    #    ('christmas', (16,33), (24,28)),
    #    ('DJ tv', (24,30), (25,55)),
    #],
    #base_path.joinpath('third_tape/tape3.mp4'): [
    #    ('basketball', (0,3), (3,46)),
    #    ('dj hawaiian dance', (3,46), (9,11)),
    #    ('spanish video', (9,22), (13,8)),
    #    ('moms bday', (13,12), (16,29)),
    #    ('house tour', (16,33), (49,37)),
    #    ('radh tae kwan do', (49,37), (65,59)),
    #    ('DJ baseball', (65,59), (85,31)),
    #    ('dj, krish, rohan', (85,33), (89,3)),
    #    ('dj basketball game', (89,3), (93,44)),
    #],
    base_path.joinpath('tape4/tape4.mp4'): [
        ('Spanish baking', (0,3), (6,16)),
        ('DJ birthday', (6,17), (15,8)),
        ('DJ random', (15,10), (15,36)),
        ('DJ basketball inside', (15,38), (21,54)),
        ('Beyond the Glory', (21,55), (36,7)),
        ('basketball inside', (36,8), (38,20)),
        ('DJ Krish Rohan', (38,21), (39,48)),
        ('NBA contests', (39,50), (51,10)),
        ('Dad birthday', (51,11), (54,12)),
        ('DJ rec basketball', (54,13), (68,52)),
        ('DJ violin concert', (68,55), (71,26)),
        ('DJ rec basketball2', (71,28), (83,2)),
        ('old school', (83,8), (87,35)),
    ]
}


if __name__ == '__main__':
    out_folder = base_path.joinpath('spliced')
    out_folder.mkdir(exist_ok=True, parents=True)
    
    for in_path, splices in video_splices.items():
        print(f'\n\n\n{in_path}')
        for name, (st_min,st_sec), (e_min, e_sec) in splices:

            start = datetime.timedelta(minutes=st_min, seconds=st_sec)
            end = datetime.timedelta(minutes=e_min, seconds=e_sec)
            name_clean = '-'.join(name.split())
            out_fpath = out_folder.joinpath(f'{in_path.stem}_{name_clean}.mp4')
            
            if True:
                print(str(in_path))
                print(start)
                print(name_clean)
                print(end)
                print(str(out_fpath))
                print()

            depricated_methods.ffmpeg_splice(in_path, out_fpath, start_sec=start.total_seconds(), end_sec=end.total_seconds())
            
        



