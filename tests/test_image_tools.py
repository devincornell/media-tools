import tempfile
import datetime
from pathlib import Path
import requests

import sys
sys.path.append('../src')

import mediatools


def test_image_tools():
    
    with tempfile.TemporaryDirectory() as tempdir:
        td = lambda x: Path(tempdir) / x
        test_video_fname = 'test_image.png'
        
        print('Downloading test image file...')
        r = requests.get('https://storage.googleapis.com/public_data_09324832787/blogpost_filecol_select_payload_time.png')
        with open(Path(tempdir) / test_video_fname, 'wb') as f:
            f.write(r.content)

        imf = mediatools.ImageFile.from_path(td(test_video_fname))
        im = imf.read()
        im.transform.to_rgb()
        im.transform.resize((100,100))
        im.filter.sobel()
        im.dist.composit(im)
        im.dist.euclid(im)
        im.dist.sobel(im)




if __name__ == '__main__':
    test_image_tools()

