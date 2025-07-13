import typing
from pathlib import Path
import functools
import pathlib
import hashlib
from collections import defaultdict
import urllib.parse


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
    '''Factory function to create a function that retrieves a value from a dictionary by key and 
        converts it to a specified type.
    '''
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






def hash_file(path, hash_algo='sha256') -> str:
    """Generate a hash for a file using the specified hash algorithm."""
    hasher = hashlib.new(hash_algo)
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()







def build_file_tree(root: pathlib.Path, pattern: str = '**/*') -> defaultdict:
    """Build a tree structure from file paths in a directory.
    
        # Example usage
        root_path = pathlib.Path('/AddStorage/personal/dwhelper/')
        file_tree = build_file_tree(root_path)

        # Print the tree structure
        print_tree(file_tree)

    """
    root = pathlib.Path(root)
    file_paths = [fp.relative_to(root) for fp in root.rglob(pattern) if fp.is_file()]
    tree = make_tree()
    for path in file_paths:
        insert_path(tree, path)
    return tree

def make_tree():
    """Create a recursive defaultdict for tree structure."""
    return defaultdict(make_tree)

# Insert a path into the tree
def insert_path(tree: defaultdict, path: pathlib.Path):
    """Insert a file path into the tree structure."""
    parts = path.parts
    for part in parts[:-1]:  # all directories
        # Only traverse if not a file node
        if tree.get(part) is None:
            tree[part] = make_tree()
        tree = tree[part]
    # Only set file node if not already present
    if tree.get(parts[-1]) is None or isinstance(tree.get(parts[-1]), dict):
        tree[parts[-1]] = None  # file

def print_tree(d: dict, indent=0):
    """Recursively print the tree structure."""
    for key, value in d.items():
        print("  " * indent + str(key))
        if isinstance(value, dict):
            print_tree(value, indent + 1)




def fname_to_title(fname: str, max_char: int = 150) -> str:
    replaced = fname.replace('_', ' ').replace('-', ' ')
    return ' '.join(replaced.strip().split()).title()[:max_char]

def fname_to_id(fname: str) -> str:
    return '-'.join(fname.strip().split())

def parse_url(urlstr: str) -> str:
    try:
        return urllib.parse.quote(urlstr)
    except TypeError as e:
        return ''

