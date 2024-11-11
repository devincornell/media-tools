import typing
import ffmpeg
import sys
import glob
import pathlib
import tqdm


############################################### Main Utilities ###############################################


def ffmpeg_splice(input_fname: str, output_fname: str, start_sec: int, end_sec: int = None, duration_sec: int = None):
    duration = duration_sec if duration_sec is not None else (end_sec - start_sec)
    return ffmpeg_run(
        ffmpeg
        .input(str(input_fname), ss=start_sec)
        .output(str(output_fname), t=duration)
        .overwrite_output()
    )

def ffmpeg_crop(input_fname: str, output_fname: str, start_x: int = 0, start_y: int = 0, width: int = -1, height: int = -1):
    return ffmpeg_run(
        ffmpeg
        .input(str(input_fname))
        .crop(start_x, start_y, width, height)
        .output(str(output_fname))
        .overwrite_output()
    )

def ffmpeg_thumb(input_fname: str, output_fname: str, width: int = -1, height: int = -1):
    info = ffmpeg_probe(input_fname=input_fname)
    return ffmpeg_run(
        ffmpeg
        .input(str(input_fname), ss=info.duration//2)
        .filter('scale', width, height)
        .output(str(output_fname), vframes=1)
        .overwrite_output()
    )

def ffmpeg_compress(input_fname: str, output_fname: str, vcodec: str = 'libx264', crf: int = 30):
    return ffmpeg_run(
        ffmpeg
        .input(str(input_fname))
        .output(str(output_fname), vcodec=vcodec, crf=crf)
        .overwrite_output()
    )


def ffmpeg_run(ffmpeg_command, verbose: bool = True) -> str:
    '''Wrapper with exception handling.'''
    try:
        output = ffmpeg_command.run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        if verbose: print('\n', e.stderr.decode(), file=sys.stderr)
    else:
        return output


def make_thumb_ffmpeg(in_filename, out_filename, **kwargs):
    # copied directly from here: 
    # https://api.video/blog/tutorials/automatically-add-a-thumbnail-to-your-video-with-python-and-ffmpeg
    
    try:
        probe = ffmpeg.probe(in_filename)
    except ffmpeg.Error:
        pass
    else:
        try:
            time = float(probe['streams'][0]['duration']) // 2
            width = probe['streams'][0]['width']
            try:
                (
                    ffmpeg
                    .input(in_filename, ss=time)
                    .filter('scale', width, -1)
                    .output(out_filename, vframes=1, **kwargs)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error as e:
                print(e.stderr.decode(), file=sys.stderr)
                pass
        except KeyError:
            pass



############################################### Probe ###############################################
class MultipleStreamsError(BaseException):
    pass

class NoVideoStreamError(BaseException):
    pass

class NoAudioStreamError(BaseException):
    pass

import dataclasses
@dataclasses.dataclass
class FFProbeInfo:
    format: typing.Dict[str, str]
    streams: typing.Dict[str,typing.List[typing.Dict[str, str]]] = dataclasses.field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        return float(self.format['duration'])
    
    @property
    def res(self) -> typing.Tuple[int,int]:
        return (int(self.video['coded_width']), int(self.video['coded_height']))
    
    @property
    def has_video(self) -> bool:
        return 'video' in self.streams and len(self.streams['video'])

    @property
    def video(self) -> typing.Dict[str, str]:
        try:
            return self.streams['video'][0]
        except (KeyError,IndexError) as e:
            raise NoVideoStreamError()
    
    @property
    def audio(self) -> typing.Dict[str, str]:
        try:
            return self.streams['audio'][0]
        except (KeyError,IndexError) as e:
            raise NoAudioStreamError()
    
    @property
    def aspect(self) -> float:
        res = self.res
        return res[0]/res[1]
    
    @classmethod
    def from_json(cls, probe_info: typing.Dict[str,str]):
        '''Parse out streams and format info.'''
        new_info: cls = cls(format = probe_info['format'])
        for stream in probe_info['streams']:
            new_info.add_stream(stream)
        return new_info
    
    def add_stream(self, stream: typing.Dict[str,str]) -> None:
        self.streams.setdefault(stream['codec_type'], list())
        self.streams[stream['codec_type']].append(stream)


def ffmpeg_probe(input_fname: str) -> FFProbeInfo:
    try:
        probe_info = ffmpeg.probe(str(input_fname))
    #except BaseException as e:
    #    print(f'{type(e)}, {e}')
    #    exit()
    except ffmpeg.Error as e:
        return None
    return FFProbeInfo.from_json(probe_info)
        
        
############################################### General purpose ###############################################
    
def ffmpeg_catch_errors(ffmpeg_command) -> str:
    try:
        output = ffmpeg_command.run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        print('\n', e.stderr.decode(), file=sys.stderr)
        pass
    else:
        return output
