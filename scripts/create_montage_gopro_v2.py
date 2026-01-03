import pathlib
import random
import json
import tempfile
import datetime
import tqdm
import dateutil.parser


import sys
sys.path.append('../src')
sys.path.append('src')
from mediatools import ffmpeg
import mediatools






def get_gopro_vids(root: pathlib.Path|str) -> list[tuple[mediatools.VideoInfo, datetime.datetime]]:
    root = pathlib.Path(root)
    all_paths = list(root.rglob('GX*.MP4')) + list(root.rglob('GX*.mp4'))

    all_vid_files = mediatools.VideoFiles.from_rglob(
        root = root, 
        extensions=('mp4','MP4'), 
        base_name_pattern='GX*',
    )
    print(len(all_vid_files), "video files found.")

    usable_vid_infos = []
    for vf in all_vid_files:
        try:
            vf_info = vf.get_info()
        except mediatools.ffmpeg.ProbeError as e:
            continue
        except KeyError as e:
            continue

        ts_str = vf_info.probe.tags['creation_time']
        ts = datetime.datetime.fromisoformat(ts_str)
        usable_vid_infos.append((vf_info, ts))
    return usable_vid_infos
    
def filter_gopro_by_date(
    vid_infos: list[tuple[mediatools.VideoInfo, datetime.datetime]], 
    start_date: str, 
    end_date: str,
) -> list[mediatools.VideoInfo]:
    if not isinstance(start_date, datetime.datetime):
        start_date = dateutil.parser.parse(start_date)
    if not isinstance(end_date, datetime.datetime):
        end_date = dateutil.parser.parse(end_date)

    filtered = []
    for vi, ts in vid_infos:
        if ts >= start_date and ts <= end_date:
            filtered.append(vi)
    return filtered


if __name__ == '__main__':
    runs = [
        {
            'output': 'virgin_islands-90x-2sec_seed=0.mp4', 
            'start': 10578, 
            'end': 12075, 
            'clip_ratio': 90, 
            'clip_duration': 2.0, 
            'max_duration_minutes': 60, 
            'seed': 0,
        },

        {'output': 'engagement-30x-2sec_seed=0.mp4', 'start': 12302, 'end': 12364, 'clip_ratio': 30, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'computer-30x-2sec_seed=0.mp4', 'start': 12369, 'end': 12380, 'clip_ratio': 30, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'olympic_np-90x-2sec_seed=0.mp4', 'start': 12659, 'end': 13251, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'vietnam-90x-2sec_seed=0.mp4', 'start': 14115, 'end': 15228, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'turkey-90x-2sec_seed=0.mp4', 'start': 15230, 'end': 16740, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'italy-90x-2sec_seed=0.mp4', 'start': 16741, 'end': 18299, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 90, 'seed': 0},

        {'output': 'utah-90x-2sec_seed=0.mp4', 'start': 18383, 'end': 18669, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'slovenia_croatia-90x-2sec_seed=0.mp4', 'start': 18672, 'end': 19685, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'paris-90x-2sec_seed=0.mp4', 'start': 19759, 'end': 19997, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'tanzania-90x-2sec_seed=0.mp4', 'start': 10089, 'end': 19899, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        {'output': 'kuwait-90x-2sec_seed=0.mp4', 'start': 19900, 'end': 10152, 'clip_ratio': 90, 'clip_duration': 2.0, 'max_duration_minutes': 60, 'seed': 0},

        #{'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 3.0, 'output': 'virgin_islands-60-3_0.mp4', 'seed': 0},
        #{'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 3.0, 'output': 'virgin_islands-30-3_0.mp4', 'seed': 0},
        #{'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 2.0, 'output': 'virgin_islands-90-2_0.mp4', 'seed': 0},
        #{'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 2.0, 'output': 'virgin_islands-60-2_0.mp4', 'seed': 0},
        #{'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 2.0, 'output': 'virgin_islands-30-2_0.mp4', 'seed': 0},

        #{'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 3.0, 'output': 'virgin_islands-90-3_0.mp4', 'seed': 1},
        #{'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 3.0, 'output': 'virgin_islands-60-3_0.mp4', 'seed': 1},
        #{'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 3.0, 'output': 'virgin_islands-30-3_0.mp4', 'seed': 1},
        #{'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 2.0, 'output': 'virgin_islands-90-2_0.mp4', 'seed': 1},
        #{'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 2.0, 'output': 'virgin_islands-60-2_0.mp4', 'seed': 1},
        #{'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 2.0, 'output': 'virgin_islands-30-2_0.mp4', 'seed': 1},

        
        #{'start': 18672, 'end': 19685, 'ratio': 60, 'duration': 2.0, 'output': 'croatia_slovenia-60-2.mp4'},
        #{'start': 18672, 'end': 19685, 'ratio': 60, 'duration': 3.0, 'output': 'croatia_slovenia-60-3.mp4'},
        #{'start': 18672, 'end': 19685, 'ratio': 30, 'duration': 2.0, 'output': 'croatia_slovenia-30-2.mp4'},
        #{'start': 18672, 'end': 19685, 'ratio': 30, 'duration': 3.0, 'output': 'croatia_slovenia-30-3.mp4'},


        # olympic
        #{'start': 12659, 'end': 13242, 'ratio': 30, 'duration': 2.0, 'output': 'gopro_olympic_park_30-2.mp4'},
        #{'start': 12659, 'end': 13242, 'ratio': 30, 'duration': 1.0, 'output': 'gopro_olympic_park_30-1.mp4'},
        #{'start': 12659, 'end': 13242, 'ratio': 60, 'duration': 2.0, 'output': 'gopro_olympic_park_60-2.mp4'},
        #{'start': 12659, 'end': 13242, 'ratio': 60, 'duration': 3.0, 'output': 'gopro_olympic_park_60-3.mp4'},

        # engagement party
        #{'start': 12381, 'end': 12412, 'ratio': 30, 'duration': 2.0, 'output': 'gopro_engagement_party_30-2.mp4'},
        #{'start': 12381, 'end': 12412, 'ratio': 60, 'duration': 3.0, 'output': 'gopro_engagement_party_60-1.mp4'},
        #{'start': 12381, 'end': 12412, 'ratio': 60, 'duration': 4.0, 'output': 'gopro_engagement_party_60-4.mp4'},
        #{'start': 12381, 'end': 12412, 'ratio': 30, 'duration': 5.0, 'output': 'gopro_engagement_party_30-5.mp4'},

        # vietnam trip
        #{'start': 14123, 'end': 15228, 'ratio': 60, 'duration': 1.0, 'output': 'gopro_vietnam_60-1.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 60, 'duration': 2.0, 'output': 'gopro_vietnam_60-2.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 60, 'duration': 3.0, 'output': 'gopro_vietnam_60-3.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 60, 'duration': 4.0, 'output': 'gopro_vietnam_60-4.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 30, 'duration': 1.0, 'output': 'gopro_vietnam_30-1.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 30, 'duration': 1.0, 'output': 'gopro_vietnam_30-2.mp4'},
        #{'start': 14123, 'end': 15228, 'ratio': 30, 'duration': 3.0, 'output': 'gopro_vietnam_30-3.mp4'},

        # italy trip
        #{'start': 16771, 'end': 18299, 'ratio': 30, 'duration': 1.0, 'output': 'gopro_italy_30-1.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 30, 'duration': 2.0, 'output': 'gopro_italy_30-2.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 30, 'duration': 3.0, 'output': 'gopro_italy_30-3.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 30, 'duration': 4.0, 'output': 'gopro_italy_30-4.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 60, 'duration': 1.0, 'output': 'gopro_italy_60-1.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 60, 'duration': 2.0, 'output': 'gopro_italy_60-2.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 60, 'duration': 3.0, 'output': 'gopro_italy_60-3.mp4'},
        #{'start': 16771, 'end': 18299, 'ratio': 60, 'duration': 4.0, 'output': 'gopro_italy_60-4.mp4'},
    ]




    gopro_src = pathlib.Path('/mnt/HugeHDD/gopro/raw_gopro')
    vid_infos = get_gopro_vids(gopro_src)  # warm up cache


    for run in tqdm.tqdm(runs):
        use_paths = [vi.vf.path for vi,ts in filter_gopro_by_date(vid_infos, start=run['start'], end=run['end'])]

        print(f"Creating montage: {run['output']} with {len(use_paths)} source videos.")
        mdm = run['max_duration_minutes']
        if mdm is not None:
            total_duration = mdm * 60.0
            max_total_clips = int(total_duration / run['clip_duration'])
        else:
            max_total_clips = None
        print(f' Max total clips: {max_total_clips}')


        compilation = ffmpeg.create_montage(
            video_files=use_paths, 
            output_filename=f"/mnt/HugeHDD/gopro/compilations/{run['output']}", 
            clip_ratio=run['clip_ratio'], 
            clip_duration=run['clip_duration'], 
            verbose=False,
            random_seed=run['seed'],
            width = 3840,
            height = 2160,
            fps = 60,
            max_total_clips=max_total_clips,
        )

