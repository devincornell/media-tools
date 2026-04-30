# `ffmpeg` Interface

The `mediatools` package maintains a custom interface for using the ffmpeg library.


```python
import pathlib

import mediatools
```

Let's download a public video file for demonstration.


```python
import tempfile
import requests

def download_test_video(
    target_path: pathlib.Path,
    url: str = "https://storage.googleapis.com/public_data_09324832787/totk_secret_attack.mkv",
) -> pathlib.Path:
    """Download a test video for the entire test session"""
    
    print(f"\nDownloading test video to {target_path}...")
    response = requests.get(url, stream=True)
    with open(target_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return target_path
    

td = tempfile.TemporaryDirectory()
temp_dir = pathlib.Path(td.name)

ex_vid = download_test_video(temp_dir / "test_video.mkv")
ex_vid
```

    
    Downloading test video to /tmp/tmpt6i9ra7r/test_video.mkv...





    PosixPath('/tmp/tmpt6i9ra7r/test_video.mkv')



## Probe

The ability to probe video metadata is one of the most useful features of `ffmpeg`. The `mediatools` uses the `ProbeInfo` type to store information returned from a probe.


```python
probe = mediatools.ffmpeg.probe(ex_vid)
probe
```




    ProbeInfo(fname='/tmp/tmpt6i9ra7r/test_video.mkv', nb_streams=2, nb_programs=0, format_name='matroska,webm', format_long_name='Matroska / WebM', start_time='0.000000', bit_rate=1480411, dur='23.687000', size=4383314, probe_score=100, tags={'ENCODER': 'Lavf60.16.100'}, video_streams=[VideoStreamInfo(stream_ind=0, codec_name='h264', codec_long_name='H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10', start_time='0.003000', start_pts=3, time_base='1/1000', tags={'ENCODER': 'Lavc60.31.102 libx264', 'DURATION': '00:00:23.669000000'}, disposition={'default': False, 'dub': False, 'original': False, 'comment': False, 'lyrics': False, 'karaoke': False, 'forced': False, 'hearing_impaired': False, 'visual_impaired': False, 'clean_effects': False, 'attached_pic': False, 'timed_thumbnails': False, 'non_diegetic': False, 'captions': False, 'descriptions': False, 'metadata': False, 'dependent': False, 'still_image': False}, height=854, width=480, coded_width=480, coded_height=854, bits_per_raw_sample=8, avg_frame_rate='30/1', r_frame_rate='30/1', chroma_location='left', color_range='tv', color_space='bt709', field_order='progressive', has_b_frames=2, closed_captions=False, is_avc='true', level=31, pix_fmt='yuv420p', profile='High', refs=1)], audio_streams=[AudioStreamInfo(stream_ind=1, codec_name='vorbis', codec_long_name='Vorbis', start_time='0.000000', start_pts=0, time_base='1/1000', tags={'VARIANT_BITRATE': '0', 'ID3V2_PRIV.COM.APPLE.STREAMING.TRANSPORTSTREAMTIMESTAMP': '\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00', 'ENCODER': 'Lavc60.31.102 libvorbis', 'DURATION': '00:00:23.687000000'}, disposition={'default': False, 'dub': False, 'original': False, 'comment': False, 'lyrics': False, 'karaoke': False, 'forced': False, 'hearing_impaired': False, 'visual_impaired': False, 'clean_effects': False, 'attached_pic': False, 'timed_thumbnails': False, 'non_diegetic': False, 'captions': False, 'descriptions': False, 'metadata': False, 'dependent': False, 'still_image': False}, sample_fmt='fltp', sample_rate=44100, channels=2, channel_layout='stereo')], other_streams=[])



### Basic Metadata

The `tags` property maintains metadata that is attached to the video. This could vary according to the camera used or any converter/translation software applied to the video.


```python
probe.tags
```




    {'ENCODER': 'Lavf60.16.100'}




```python
probe.bit_rate, probe.duration, probe.size, probe.probe_score, probe.resolution_str()
```




    (1480411, 23.687, 4383314, 100, '480x854')



### Streams

Each video maintains multiple video or audio streams, depending on the type of video file. The `streams` attribute allows you to explore the streams. Here you can see we have one video stream and one audio stream.


```python
len(probe.video_streams), len(probe.audio_streams), len(probe.other_streams)
```




    (1, 1, 0)



You can get the first video stream (in the order it appears in the original file) using the `video` attribute. This is convenient because most video file types have only one video stream.


```python
probe.video
```




    VideoStreamInfo(stream_ind=0, codec_name='h264', codec_long_name='H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10', start_time='0.003000', start_pts=3, time_base='1/1000', tags={'ENCODER': 'Lavc60.31.102 libx264', 'DURATION': '00:00:23.669000000'}, disposition={'default': False, 'dub': False, 'original': False, 'comment': False, 'lyrics': False, 'karaoke': False, 'forced': False, 'hearing_impaired': False, 'visual_impaired': False, 'clean_effects': False, 'attached_pic': False, 'timed_thumbnails': False, 'non_diegetic': False, 'captions': False, 'descriptions': False, 'metadata': False, 'dependent': False, 'still_image': False}, height=854, width=480, coded_width=480, coded_height=854, bits_per_raw_sample=8, avg_frame_rate='30/1', r_frame_rate='30/1', chroma_location='left', color_range='tv', color_space='bt709', field_order='progressive', has_b_frames=2, closed_captions=False, is_avc='true', level=31, pix_fmt='yuv420p', profile='High', refs=1)




```python
probe.video.resolution, probe.video.codec_name, probe.video.start_time, probe.video.frame_rate
```




    ((480, 854), 'h264', '0.003000', 30)



Similarly, the first audio channel can be retrieved using `audio` attribute.


```python
probe.audio
```




    AudioStreamInfo(stream_ind=1, codec_name='vorbis', codec_long_name='Vorbis', start_time='0.000000', start_pts=0, time_base='1/1000', tags={'VARIANT_BITRATE': '0', 'ID3V2_PRIV.COM.APPLE.STREAMING.TRANSPORTSTREAMTIMESTAMP': '\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00', 'ENCODER': 'Lavc60.31.102 libvorbis', 'DURATION': '00:00:23.687000000'}, disposition={'default': False, 'dub': False, 'original': False, 'comment': False, 'lyrics': False, 'karaoke': False, 'forced': False, 'hearing_impaired': False, 'visual_impaired': False, 'clean_effects': False, 'attached_pic': False, 'timed_thumbnails': False, 'non_diegetic': False, 'captions': False, 'descriptions': False, 'metadata': False, 'dependent': False, 'still_image': False}, sample_fmt='fltp', sample_rate=44100, channels=2, channel_layout='stereo')




```python
probe.audio.codec_name, probe.audio.start_time, probe.audio.channels, probe.audio.channel_layout, probe.audio.sample_rate
```




    ('vorbis', '0.000000', 2, 'stereo', 44100)



## `ffmpeg` Command Interface

The low-level ffmpeg interface allows you to access the full range of ffmpeg features through a modern interface.


### Executing ffmpeg Commands

Create the command object using the `ffmpeg` function along with `ffinput` and `ffoutput`.

For the first example, I will execute a command that will cut a video halfway through. You would instantiate the command as follows:


```python
output_path = temp_dir / "test_video_output.mp4"
half_duration = probe.duration / 2
print(f'{half_duration=}')

cmd = mediatools.ffmpeg.ffmpeg(
    input = mediatools.ffmpeg.ffinput(str(ex_vid), ss=probe.start_time, to=half_duration),
    output = mediatools.ffmpeg.ffoutput(str(output_path), y=True),
)
cmd
```

    half_duration=11.8435





    FFMPEG(inputs=[FFInput(path='/tmp/tmpt6i9ra7r/test_video.mkv', args=FFInputArgs(f=None, t=None, ss='0.000000', to=11.8435, itsoffset=None, c_v=None, c_a=None, r=None, s=None, pix_fmt=None, aspect=None, vframes=None, top=None, ar=None, ac=None, aframes=None, vol=None, hwaccel=None, hwaccel_device=None, map_metadata=None, map_chapters=None, probesize=None, analyzeduration=None, fpsprobesize=None, safe=None, loop=None, stream_loop=None, accurate_seek=None, seek_timestamp=None, other_args=None, other_flags=None))], outputs=[FFOutput(path='/tmp/tmpt6i9ra7r/test_video_output.mp4', args=FFOutputArgs(y=True, maps=[], map_metadata=None, map_chapters=None, ss=None, t=None, duration=None, to=None, c_v=None, b_v=None, crf=None, q_v=None, maxrate=None, bufsize=None, framerate=None, fps=None, s=None, aspect=None, pix_fmt=None, vframes=None, keyint_min=None, g=None, bf=None, profile_v=None, level=None, tune=None, c_a=None, b_a=None, ar=None, ac=None, vol=None, aframes=None, profile_a=None, q_a=None, v_f=None, a_f=None, filter_complex=None, f=None, movflags=None, brand=None, hwaccel=None, hwaccel_output_format=None, vaapi_device=None, preset=None, x264_params=None, x265_params=None, an=False, vn=False, sn=False, dn=False, metadata=None, c_s=None, threads=None, other_args=None, other_flags=None))], filter_complex=None, loglevel=None, hide_banner=True, nostats=True, progress=None, passlogfile=None, pass_num=None, other_args=[], other_flags=[])



The `run` the command will actually execute the ffmpeg call and return a `FFMPEGResult` instance with information about the command and `stderr`/`stdout`.


```python
result = cmd.run()
result
```




    FFMPEGResult(command=ffmpeg -ss 0.000000 -to 11.8435 -i /tmp/tmpt6i9ra7r/test_video.mkv -hide_banner -nostats -y /tmp/tmpt6i9ra7r/test_video_output.mp4, returncode=0, output_length=3965)




```python
print(result.stderr)
```

    Input #0, matroska,webm, from '/tmp/tmpt6i9ra7r/test_video.mkv':
      Metadata:
        ENCODER         : Lavf60.16.100
      Duration: 00:00:23.69, start: 0.000000, bitrate: 1480 kb/s
      Stream #0:0: Video: h264 (High), yuv420p(tv, bt709, progressive), 480x854, 30 fps, 30 tbr, 1k tbn
        Metadata:
          ENCODER         : Lavc60.31.102 libx264
          DURATION        : 00:00:23.669000000
      Stream #0:1: Audio: vorbis, 44100 Hz, stereo, fltp
        Metadata:
          VARIANT_BITRATE : 0
          ID3V2_PRIV.COM.APPLE.STREAMING.TRANSPORTSTREAMTIMESTAMP: \x00\x00\x00\x00\x00\x00\x00\x00
          ENCODER         : Lavc60.31.102 libvorbis
          DURATION        : 00:00:23.687000000
    Stream mapping:
      Stream #0:0 -> #0:0 (h264 (native) -> h264 (libx264))
      Stream #0:1 -> #0:1 (vorbis (native) -> aac (native))
    Press [q] to stop, [?] for help
    [libx264 @ 0x5662d2689000] using cpu capabilities: MMX2 SSE2Fast SSSE3 SSE4.2 AVX FMA3 BMI2 AVX2
    [libx264 @ 0x5662d2689000] profile High, level 3.1, 4:2:0, 8-bit
    [libx264 @ 0x5662d2689000] 264 - core 164 r3108 31e19f9 - H.264/MPEG-4 AVC codec - Copyleft 2003-2023 - http://www.videolan.org/x264.html - options: cabac=1 ref=3 deblock=1:0:0 analyse=0x3:0x113 me=hex subme=7 psy=1 psy_rd=1.00:0.00 mixed_ref=1 me_range=16 chroma_me=1 trellis=1 8x8dct=1 cqm=0 deadzone=21,11 fast_pskip=1 chroma_qp_offset=-2 threads=27 lookahead_threads=4 sliced_threads=0 nr=0 decimate=1 interlaced=0 bluray_compat=0 constrained_intra=0 bframes=3 b_pyramid=2 b_adapt=1 b_bias=0 direct=1 weightb=1 open_gop=0 weightp=2 keyint=250 keyint_min=25 scenecut=40 intra_refresh=0 rc_lookahead=40 rc=crf mbtree=1 crf=23.0 qcomp=0.60 qpmin=0 qpmax=69 qpstep=4 ip_ratio=1.40 aq=1:1.00
    Output #0, mp4, to '/tmp/tmpt6i9ra7r/test_video_output.mp4':
      Metadata:
        encoder         : Lavf60.16.100
      Stream #0:0: Video: h264 (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 480x854, q=2-31, 30 fps, 15360 tbn
        Metadata:
          DURATION        : 00:00:23.669000000
          encoder         : Lavc60.31.102 libx264
        Side data:
          cpb: bitrate max/min/avg: 0/0/0 buffer size: 0 vbv_delay: N/A
      Stream #0:1: Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s
        Metadata:
          VARIANT_BITRATE : 0
          ID3V2_PRIV.COM.APPLE.STREAMING.TRANSPORTSTREAMTIMESTAMP: \x00\x00\x00\x00\x00\x00\x00\x00
          DURATION        : 00:00:23.687000000
          encoder         : Lavc60.31.102 aac
    [out#0/mp4 @ 0x5662d26bbe00] video:1323kB audio:194kB subtitle:0kB other streams:0kB global headers:0kB muxing overhead: 0.907372%
    frame=  356 fps=0.0 q=-1.0 Lsize=    1530kB time=00:00:11.82 bitrate=1060.5kbits/s speed=21.4x    
    [libx264 @ 0x5662d2689000] frame I:2     Avg QP:23.62  size: 21700
    [libx264 @ 0x5662d2689000] frame P:145   Avg QP:24.08  size:  6307
    [libx264 @ 0x5662d2689000] frame B:209   Avg QP:26.39  size:  1893
    [libx264 @ 0x5662d2689000] consecutive B-frames:  8.7% 33.1% 17.7% 40.4%
    [libx264 @ 0x5662d2689000] mb I  I16..4: 18.8% 47.9% 33.2%
    [libx264 @ 0x5662d2689000] mb P  I16..4:  4.8% 15.1%  3.1%  P16..4: 26.1%  4.3%  2.0%  0.0%  0.0%    skip:44.7%
    [libx264 @ 0x5662d2689000] mb B  I16..4:  0.9%  2.1%  0.4%  B16..8: 21.8%  2.1%  0.4%  direct: 2.0%  skip:70.3%  L0:45.6% L1:49.4% BI: 5.0%
    [libx264 @ 0x5662d2689000] 8x8 transform intra:64.1% inter:77.3%
    [libx264 @ 0x5662d2689000] coded y,uvDC,uvAC intra: 44.9% 73.6% 28.0% inter: 6.8% 14.1% 1.3%
    [libx264 @ 0x5662d2689000] i16 v,h,dc,p: 24% 41% 12% 23%
    [libx264 @ 0x5662d2689000] i8 v,h,dc,ddl,ddr,vr,hd,vl,hu: 18% 27% 22%  6%  5%  4%  7%  5%  7%
    [libx264 @ 0x5662d2689000] i4 v,h,dc,ddl,ddr,vr,hd,vl,hu: 28% 28% 14%  5%  5%  5%  5%  5%  5%
    [libx264 @ 0x5662d2689000] i8c dc,h,v,p: 42% 29% 19%  9%
    [libx264 @ 0x5662d2689000] Weighted P-Frames: Y:0.0% UV:0.0%
    [libx264 @ 0x5662d2689000] ref P L0: 73.1% 11.7% 11.0%  4.2%
    [libx264 @ 0x5662d2689000] ref B L0: 89.8%  8.9%  1.3%
    [libx264 @ 0x5662d2689000] ref B L1: 98.4%  1.6%
    [libx264 @ 0x5662d2689000] kb/s:912.57
    [aac @ 0x5662d3409bc0] Qavg: 1027.640


You can verify that the command was successful by probing the new file. Notice the difference between the requested duration and the actual duration. This is an issue because videos are composed of discrete frames.


```python
mediatools.ffmpeg.probe(output_path).duration
```




    11.866667



## Creating Filterchains and Filtergraphs

Audio and video filters are an important feature of FFMPEG - they allow you to do things like crop, scale, and even create thumbnails from input videos.

There are two possible ways of constructing filters, both specified through the CLI as strings:

- **filterchain**: sequence of filters applied to an input video or audio stream. Specified by passing the arguments `-v:f` (for video filters) or `-a:f` (for audio filters).
- **filtergraph**: proper DAG describing transformations applied to an input video or audio stream. Specified by passing the argument `-filter_complex` (handles both audio and video).

In the `mediatools` ffmpeg interface, you can pass these as strings to the `v_f`, `a_f`, or `filter_complex` arguments of `ffoutput`. There are, however, several methods that make it easier to create properly structured filter specifications.


```python
output_path = temp_dir / "cropped_video.mp4"

mediatools.ffmpeg.ffmpeg(
    input=mediatools.ffmpeg.ffinput(str(ex_vid)),
    output=mediatools.ffmpeg.ffoutput(
        str(output_path), 
        v_f=f'scale=w=480:h=640', 
        y=True
    ),
).run()
mediatools.ffmpeg.probe(str(output_path)).video.resolution
```




    (480, 640)



### Simple Filterchains

There are two methods that make it easy to construct simple filterchains to be passed as `v_f` (for video) or `a_f` (for audio):

- `filter_link`: specifies a single transformation of an input video or audio stream.
- `filterchain`: specifies a series of transformations for an input video or audio stream.

I will now show how these two can be used to construct filters.

#### `filter_link`

You can see how `filter_link` accepts the name of the filter and either positional or keyword arguments to specify the behavior.


```python
mediatools.ffmpeg.filter_link('scale', '480:640')
```




    'scale=480:640'




```python
mediatools.ffmpeg.filter_link('scale', w=480, h=640)
```




    'scale=w=480:h=640'




```python
mediatools.ffmpeg.filter_link('crop', w=100, h=100, x=100, y=100)
```




    'crop=w=100:h=100:x=100:y=100'



#### `filterchain`

Use `filterchain` to chain filter links together. The output of this function is just a string, so it can be passed directly to the `v_f` argument.


```python
mediatools.ffmpeg.filterchain(
    mediatools.ffmpeg.filter_link('crop', w=100, h=100, x=100, y=100),
    mediatools.ffmpeg.filter_link('scale', w=480, h=640),
)
```




    'crop=w=100:h=100:x=100:y=100,scale=w=480:h=640'



As a second example, I create a filterchain that will extract animated thumbs from a video file. Here I wrap the filter in a parameterized factory function.


```python
def animated_thumb_filter(pts: float, fps: int, width: int, height: int):
    return mediatools.ffmpeg.filterchain(
        mediatools.ffmpeg.filter_link('setpts', f'PTS/{pts}'),
        mediatools.ffmpeg.filter_link('fps', fps=fps),
        mediatools.ffmpeg.filter_link('scale', w=width, h=height, force_original_aspect_ratio='decrease'),
    )
```

### Complex Filtergraphs

There are two functions that can help you express complex filtergraph designs to be passed as `filter_complex`:

- `filtergraph_link`: specifies a single transformation from specified input and output streams.
- `filtergraph`: combines several filtergraph links to create a complete filtergraph.

#### `filtergraph_link`

The `filtergraph_link` method is very similar to `filter_link` except that it adds input and output labels on either end of the string.


```python
mediatools.ffmpeg.filtergraph_link('scale', w=480, h=640, input='0:v', output='scaled')
```




    '[0:v]scale=w=480:h=640[scaled]'



The `filtergraph_link` function also allows you to provide multiple inputs or outputs using combinations of the `input`, `inputs`, `output`, and `outputs` parameters.


```python
mediatools.ffmpeg.filtergraph_link('split', input='0:v', outputs=['bg_raw', 'fg_raw'])
```




    '[0:v]split[bg_raw][fg_raw]'



In fact, you can even use it without input or output labels - it is a more general case of `filter_link`, which was created to have simpler arguments.


```python
mediatools.ffmpeg.filtergraph_link('scale', w=480, h=640)
```




    'scale=w=480:h=640'



Importantly, `filtergraph_link` can also accept filter links from `filter_link` and filterchains from `filterchain` instead of a filter name. This will save you from needing to construct additional filtergraph links.

In the example below, we create a filtergraph link from a filterchain of two links: one to scale and one to apply a gaussian blur.


```python
chain = mediatools.ffmpeg.filterchain(
    mediatools.ffmpeg.filter_link("scale", w="ih", h="ih"),
    mediatools.ffmpeg.filter_link("gblur", sigma=25)
)

mediatools.ffmpeg.filtergraph_link(
    chain,
    input="bg_raw", 
    output="bg_ready"
)
```




    '[bg_raw]scale=w=ih:h=ih,gblur=sigma=25[bg_ready]'



#### `filtergraph`

The `filtergraph` function allows you to construct a filtergraph that audio and video streams "flow" through to produce the final output. Each link is a transformation and the labels are intermediary points, so the order does not matter. Many filtergraphs essentially follow the pattern of processing each input stream in parallel and then overlaying them at the end, so you will see these examples.

The best way to see `filtergraph` in action is to look at examples.

#### `filtergraph` Example 1: Picture-in-picture

First, I create a filtergraph that simulates picture-in-picture using a single video: both the big and small videos will come from the same source. To do that, I split the input into two parts that will be eventually overlaid: the first remains the same, and the second one is scaled to be the size of the tiny pane. Finally, the tiny pane is overlaid back onto the output video. 


```python
def picture_in_picture_self_filter(pip_scale_factor: int, margin: int):
    return mediatools.ffmpeg.filtergraph(
        # 1. Split the video
        mediatools.ffmpeg.filtergraph_link(
            'split', 
            input='0:v', 
            outputs=['main_raw', 'pip_raw']
        ), 
        
        # 2. Process the PiP pane (Scale it down)
        mediatools.ffmpeg.filtergraph_link(
            "scale", 
            # Using iw/4 and ih/4 keeps the exact same aspect ratio automatically
            w=f"iw/{pip_scale_factor}", 
            h=f"ih/{pip_scale_factor}", 
            input="pip_raw", 
            output="pip_ready"
        ), 
        
        # 3. Overlay the tiny pane onto the main video
        mediatools.ffmpeg.filtergraph_link(
            "overlay", 
            inputs=["main_raw", "pip_ready"], 
            # W = Main Width, w = PiP Width. 
            # (W - w) pushes it all the way to the right edge. Subtracting the margin brings it back slightly.
            x=f"W-w-{margin}", 
            # H = Main Height, h = PiP Height.
            # (H - h) pushes it all the way to the bottom edge. Subtracting the margin brings it up slightly.
            y=f"H-h-{margin}"
        )
    )
```


```python
mediatools.ffmpeg.filtergraph(
    mediatools.ffmpeg.filtergraph_link('split', input='0:v', outputs=['base', 'pip_raw']), 
    mediatools.ffmpeg.filtergraph_link(
        mediatools.ffmpeg.filterchain(
            mediatools.ffmpeg.filter_link("scale", w="ih", h="ih"),
            mediatools.ffmpeg.filter_link("gblur", sigma=25),
            mediatools.ffmpeg.filter_link('crop', w=100, h=100, x=100, y=100),
        ), 
        input="pip_raw", 
        output="pip_final"
    ), 
    mediatools.ffmpeg.filtergraph_link(
        "overlay", 
        inputs=["bg_ready", "fg_raw"], 
        x="(W-w)/2", 
        y="(H-h)/2"
    )
)
```




    '[0:v]split[base][pip_raw];[pip_raw]scale=w=ih:h=ih,gblur=sigma=25,crop=w=100:h=100:x=100:y=100[pip_final];[bg_ready][fg_raw]overlay=x=(W-w)/2:y=(H-h)/2'



#### `filtergraph` Example 2: Blurred Video Padding

This example shows how to create a filtergraph that transforms the input into a new video with symmetric aspect ratio where padding is filled in with a blurred version of the original video.


```python
def blurred_padding_symetric_filter(blur_sigma: int = 25):
    return mediatools.ffmpeg.filtergraph(
        
        # 1. Split the input video stream into two parts: `bg_raw` and `fg_raw`.
        mediatools.ffmpeg.filtergraph_link('split', input='0:v', outputs=['bg_raw', 'fg_raw']), 
        
        # 2. Scale `bg_raw` to the input height (`ih`) and width (`iw`), then apply a gaussian blur to produce `bg_ready`.
        mediatools.ffmpeg.filtergraph_link(
            mediatools.ffmpeg.filterchain(
                mediatools.ffmpeg.filter_link("scale", w="ih", h="ih"),
                mediatools.ffmpeg.filter_link("gblur", sigma=blur_sigma)
            ), 
            input="bg_raw", 
            output="bg_ready"
        ), 

        # 3. Overlay `fg_raw` on top of `bg_ready` according to the centering math: `x="(W-w)/2", y="(H-h)/2"` where:
        #    - `x` and `y` are the starting coordinates of the overlay.
        #    - `W` and `H` are the width and height of the main/background video
        #    - `w` and `h`  are the width and height of the foreground video.
        mediatools.ffmpeg.filtergraph_link(
            "overlay", 
            inputs=["bg_ready", "fg_raw"], 
            x="(W-w)/2", 
            y="(H-h)/2"
        )
    )
```

Now say we want to specify a custom resolution for the output so we can dynamically set the blurred output padding accoridng to the original and desired resolutions.


```python
def blurred_padding_filter(target_w: int, target_h: int, blur_sigma: int = 25):
    return mediatools.ffmpeg.filtergraph(

        # 1. Split the input video stream into two parts: `bg_raw` and `fg_raw`.
        mediatools.ffmpeg.filtergraph_link(filter_spec='split', input='0:v', outputs=['bg_raw', 'fg_raw']), 

        # 2. Fill the frame completely without stretching or leaving black bars
        mediatools.ffmpeg.filtergraph_link(
            filter_spec = mediatools.ffmpeg.filterchain(
                
                # 2a. Scale `bg_raw` to fill the frame while preserving aspect ratio, which may cause some cropping.
                mediatools.ffmpeg.filter_link(
                    "scale", 
                    w=target_w, 
                    h=target_h, 
                    force_original_aspect_ratio="increase"
                ),
                
                # 2b. Crop the scaled `bg_raw` to the target dimensions.
                mediatools.ffmpeg.filter_link("crop", w=target_w, h=target_h),
                
                # 2c. Apply a gaussian blur to the cropped background.
                mediatools.ffmpeg.filter_link("gblur", sigma=blur_sigma)
            ), 
            input="bg_raw", 
            output="bg_ready"
        ), 
        
        # 3. Scale `fg_raw` to fit within the target dimensions while preserving aspect ratio, which may cause letterboxing/pillarboxing.
        mediatools.ffmpeg.filtergraph_link(
            filter_spec = "scale", 
            w=target_w, 
            h=target_h, 
            force_original_aspect_ratio="decrease",
            input="fg_raw",
            output="fg_ready"
        ),

        # 4. Overlay `fg_ready` on top of `bg_ready` according to the centering math: `x="(W-w)/2", y="(H-h)/2"`.
        #    - `x` and `y` are the starting coordinates of the overlay.
        #    - `W` and `H` are the width and height of the main/background video
        #    - `w` and `h`  are the width and height of the foreground video.
        mediatools.ffmpeg.filtergraph_link(
            filter_spec="overlay", 
            inputs=["bg_ready", "fg_ready"], 
            x="(W-w)/2", 
            y="(H-h)/2"
        )
    )
```


```python

```


```python

```


```python

```


```python

```


```python

```


```python

```


```python

```


```python

```


```python

```

# Testing


```python
output_path = temp_dir / "test_video_out.mp4"

mediatools.ffmpeg.ffmpeg(
    input=mediatools.ffinput(ex_vid),
    output=mediatools.ffoutput(
        output_path, 
        filter_complex=animated_thumb_filter(pts=10, fps=10, width=480, height=640),
        y=True,
    ),
).run()

import shutil
shutil.copy(str(output_path), output_path.name)
```




    'test_video_out.mp4'


