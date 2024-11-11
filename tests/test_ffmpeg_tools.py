import datetime
from pathlib import Path

import sys
sys.path.append('../src')

import mediatools


def test_ffmpeg_tools(test_data_path = Path('test_data')):
                                    
    
    td = lambda x: test_data_path / x

    vf = mediatools.VideoFile.from_path(td('totk_secret_attack.mkv'))

    result = vf.ffmpeg.compress(td('totk_compressed.mp4'), crf=30, overwrite=True)
    assert(result.vf.exists())
    assert(len(result.stdout) > 0)
    
    result = vf.ffmpeg.splice(
        output_fname=td('totk_spliced.mp4'), 
        start_time=datetime.timedelta(seconds=0), 
        end_time=datetime.timedelta(seconds=5),
        overwrite=True
    )
    assert(result.vf.exists())
    assert(len(result.stdout) > 0)


    result = vf.ffmpeg.crop(
        output_fname=td('totk_cropped.mp4'), 
        topleft_point=(0,0),
        size=(vf.probe().video.width//2, vf.probe().video.height//2),
        overwrite=True
    )
    assert(result.vf.exists())
    assert(len(result.stdout) > 0)


    result = vf.ffmpeg.make_thumb(
        output_fname=td('totk_thumb.jpg'), 
        time_point=0.5,
        height=100,
        overwrite=True
    )
    assert(result.fp.exists())
    assert(len(result.stdout) > 0)



if __name__ == '__main__':
    test_ffmpeg_tools()

