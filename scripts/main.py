
import sys
sys.path.append('../src')

import mediatools

if __name__ == '__main__':
    
    vf = mediatools.VideoFile.from_path('test_data/firstsecond.mp4')

    result = vf.ffmpeg.compress('test_data/firstsecond_compressed.mp4', crf=30, overwrite=True)

    print(result.vf)
    print(result.vf.probe().video_streams[0].codec_name)
    print(result.stdout)

