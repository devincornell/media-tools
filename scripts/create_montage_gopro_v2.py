import pathlib
import random
import json
import tempfile

import tqdm


import sys
sys.path.append('../src')
from mediatools import ffmpeg
import mediatools


def get_gopro_paths(root: pathlib.Path|str, start: int, end: int) -> list[pathlib.Path]:
    root = pathlib.Path(root)
    all_paths = list(root.rglob('GX*.MP4')) + list(root.rglob('GX*.mp4'))
    all_paths.sort()
    paths = [(p, int(p.stem.split('_')[0][2:])) for p in all_paths]
    return [p for p, num in paths if start <= num <= end]



if __name__ == '__main__':
    runs = [

        {'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 3.0, 'output': 'virgin_islands-90-3_0.mp4', 'seed': 0},
        {'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 3.0, 'output': 'virgin_islands-60-3_0.mp4', 'seed': 0},
        {'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 3.0, 'output': 'virgin_islands-30-3_0.mp4', 'seed': 0},
        {'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 2.0, 'output': 'virgin_islands-90-2_0.mp4', 'seed': 0},
        {'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 2.0, 'output': 'virgin_islands-60-2_0.mp4', 'seed': 0},
        {'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 2.0, 'output': 'virgin_islands-30-2_0.mp4', 'seed': 0},

        {'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 3.0, 'output': 'virgin_islands-90-3_0.mp4', 'seed': 1},
        {'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 3.0, 'output': 'virgin_islands-60-3_0.mp4', 'seed': 1},
        {'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 3.0, 'output': 'virgin_islands-30-3_0.mp4', 'seed': 1},
        {'start': 10567, 'end': 12079, 'ratio': 90, 'duration': 2.0, 'output': 'virgin_islands-90-2_0.mp4', 'seed': 1},
        {'start': 10567, 'end': 12079, 'ratio': 60, 'duration': 2.0, 'output': 'virgin_islands-60-2_0.mp4', 'seed': 1},
        {'start': 10567, 'end': 12079, 'ratio': 30, 'duration': 2.0, 'output': 'virgin_islands-30-2_0.mp4', 'seed': 1},

        
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



    for run in tqdm.tqdm(runs):
        use_paths = get_gopro_paths(gopro_src, start=run['start'], end=run['end'])
        print(f"Creating montage: {run['output']} with {len(use_paths)} source videos.")
        compilation = ffmpeg.create_montage(
            video_files=use_paths, 
            output_filename=f"/mnt/HugeHDD/gopro/compilations/{run['output']}", 
            clip_ratio=run['ratio'], 
            clip_duration=run['duration'], 
            verbose=False,
            random_seed=run['seed'],
            width = 3840,
            height = 2160,
            fps = 60
        )

