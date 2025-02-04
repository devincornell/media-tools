import typing
from pathlib import Path
import functools


Constant = str | int | bool | float


#def get_or_None_factory(data: typing.Dict) -> typing.Callable[[str, type], typing.Optional[Constant]]:
#    return functools.partial(get_or_None, data)

#def get_or_None_int(data: typing.Dict, key: str) -> typing.Optional[int]:
#    return int(data[key]) if key in data else None

#def get_or_None_str(data: typing.Dict, key: str) -> typing.Optional[str]:
#    return str(data[key]) if key in data else None



########################### Old factories for type hints ###########################
T = typing.TypeVar("T")

def get_or_None_factory(data: typing.Dict) -> typing.Callable[[str, type[T]], typing.Optional[T]]:
    return functools.partial(get_or_None, data)

def get_or_None(data: typing.Dict, key: str, convert_type: type[T] = str) -> typing.Optional[T]:
    return convert_type(data[key]) if key in data else None


class VideoTime(str):
    '''Represents a time value in video. Retain as string for perfect storage.'''
    
    def as_float(self) -> float:
        return float(self)


def multi_extension_glob(
    glob_func: typing.Callable[[str],list[Path]], 
    extensions: typing.Iterable[str],
    base_name_pattern: str = '*',
) -> list[Path]:
    '''Get a list of file paths that match patterns for different file extensions.
    Args:
        glob_func: A function that takes a pattern and returns a list of paths.
            Could be glob.glob, Path.glob, or Path.rglob.
        extensions: A list of file extensions to search for.
        base_name_pattern: The base name pattern to use for the file name.
            Example: "*" or "video_*" or "vid_*_name". Concatenated with extensions.
    '''
    # insert capitalized and lower case versions of extensions
    exts = list(extensions)
    extensions = [e.lower() for e in exts] + [e.upper() for e in exts]

    all_paths = list()
    for ext in extensions:
        pattern = f'{base_name_pattern}{ext}' if ext.startswith('.') else f'{base_name_pattern}.{ext}'
        all_paths += list(glob_func(pattern))
    return list(sorted(all_paths))
    


def format_time(num_seconds: int, decimals: int = 2):
    ''' Get string representing time quantity with correct units.
    '''
    
    if num_seconds >= 3600:
        return f'{num_seconds/3600:0.{decimals}f} hrs'
    elif num_seconds >= 60:
        return f'{num_seconds/60:0.{decimals}f} min'
    elif num_seconds < 1.0:
        return f'{num_seconds*1000:0.{decimals}f} ms'
    else:
        return f'{num_seconds:0.{decimals}f} sec'

def format_memory(num_bytes: int, decimals: int = 2):
    ''' Get string representing memory quantity with correct units.
    '''
    if num_bytes >= 1e9:
        return f'{num_bytes/1e9:0.{decimals}f} GB'
    elif num_bytes >= 1e6:
        return f'{num_bytes/1e6:0.{decimals}f} MB'
    elif num_bytes >= 1e3:
        return f'{num_bytes*1e3:0.{decimals}f} kB'
    else:
        return f'{num_bytes:0.{decimals}f} Bytes'




