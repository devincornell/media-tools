import tempfile
import datetime
from pathlib import Path
import requests

import sys
sys.path.append('../src')

import mediatools


def test_ffmpeg_tools():
    
    with tempfile.TemporaryDirectory() as tempdir:
        td = lambda x: Path(tempdir) / x
        test_video_fname = 'totk_secret_attack.mkv'
        
        print('Downloading test video file...')
        r = requests.get('https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv')
        with open(Path(tempdir) / test_video_fname, 'wb') as f:
            f.write(r.content)

        vf = mediatools.VideoFile.from_path(td(test_video_fname))

        print('testing globbing multiple files')
        imfs = mediatools.VideoFiles.from_rglob(tempdir)
        assert(len(imfs) > 0)

        print('compressing')
        result = vf.ffmpeg.compress(td('totk_compressed.mp4'), crf=30, overwrite=True)
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)
        
        print('splicing')
        result = vf.ffmpeg.splice(
            output_fname=td('totk_spliced.mp4'), 
            start_time=datetime.timedelta(seconds=0), 
            end_time=datetime.timedelta(seconds=5),
            overwrite=True
        )
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)

        print('cropping')
        result = vf.ffmpeg.crop(
            output_fname=td('totk_cropped.mp4'), 
            topleft_point=(0,0),
            size=(vf.probe().video.width//2, vf.probe().video.height//2),
            overwrite=True
        )
        assert(result.vf.exists())
        assert(len(result.stdout) > 0)

        print('making thumb')
        result = vf.ffmpeg.make_thumb(
            output_fname=td('totk_thumb.jpg'), 
            time_point=0.5,
            height=100,
            overwrite=True
        )
        assert(result.fp.exists())
        assert(len(result.stdout) > 0)


def test_ffmpeg_lowlevel():
    with tempfile.TemporaryDirectory() as tempdir:
        td = lambda x: Path(tempdir) / x
        test_video_fname = 'totk_secret_attack.mkv'
        
        fp = Path(tempdir) / test_video_fname
        print(f'Downloading test video file {fp}...')
        r = requests.get('https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv')
        with open(fp, 'wb') as f:
            f.write(r.content)

        print(mediatools.ffmpeg.probe(fp))
        print(mediatools.ffmpeg.probe_dict(fp))

        #print(mediatools.ffmpeg.compress(fp))

        print('compressing')
        op = td('totk_compressed.mp4')
        result = mediatools.ffmpeg.compress(fp, op, crf=30, loglevel='info')
        assert(op.exists())
        assert(len(result.output) > 0)
        
        print('splicing')
        op = td('totk_spliced.mp4')
        result = mediatools.ffmpeg.splice(
            input_fname=fp,
            output_fname=op, 
            start_time=datetime.timedelta(seconds=0), 
            end_time=datetime.timedelta(seconds=5),
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)

        print('cropping')
        op = td('totk_cropped.mp4')
        probe = mediatools.ffmpeg.probe(fp)
        result = mediatools.ffmpeg.crop(
            input_fname=fp,
            output_fname=op, 
            topleft_point=(0,0),
            size=(probe.video.width//2, probe.video.height//2),
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)

        print('making thumb')
        result = mediatools.ffmpeg.make_thumb(
            input_fname=fp,
            output_fname=td('totk_thumb.jpg'), 
            time_point_sec=0.5,
            height=100,
            overwrite=True
        )
        assert(result.output_file.exists())
        assert(len(result.output) > 0)


if __name__ == '__main__':
    #test_ffmpeg_tools()
    test_ffmpeg_lowlevel()

