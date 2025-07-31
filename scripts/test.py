from __future__ import annotations
import jinja2
import typing
import pathlib

import sys
sys.path.append('../src')
import mediatools


#mdir = mediatools.scan_directory('/mnt/HDDStorage/sys/')
test_file = '/mnt/MoStorage/gopro/q6RRQoL60Vy3p-1.mp4'
print(dir(mediatools))
cmd = mediatools.ffmpeg.FFMPEG(
    input_files=[test_file], 
    output_file='tmp.mp4', 
    hwaccel='cuda', 
    vcodec='h264_nvenc', 
    overwrite_output=True,
    loglevel='warning',
)
print(cmd.get_command())
print(cmd.run())


#for vf in mdir.all_video_files():
#    print(f'Probing {vf.fpath}')
#    vfp = vf.probe()

#print('audio streams:')
#for aud_stream in vfp.audio_streams:
#    print(aud_stream)
#    print()
#
#print('video streams:')
#for vid_stream in vfp.video_streams:
#    print(vid_stream)
#    print()


