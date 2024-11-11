
import sys
sys.path.append('../src')

import mediatools

if __name__ == '__main__':
    
    vf = mediatools.VideoFile.from_path('test.mp4')

    result = vf.ffmpeg.compress()

    result.vf

