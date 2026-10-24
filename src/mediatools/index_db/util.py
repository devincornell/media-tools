import multiprocessing
import typing
from pathlib import Path
import functools
import pathlib
import hashlib
from collections import defaultdict
import urllib.parse
import glob
import os
import re

import tqdm

from ..util import get_hash_firstlast_hex

Constant = str | int | bool | float
T = typing.TypeVar('T')
R = typing.TypeVar('R')



################# Hashing utilities ################

def index_hash_func(path: pathlib.Path|str) -> str:
    '''Index hash function used for all media files in the database.'''
    return get_hash_firstlast_hex(path, chunk_size=1024)


def path_prefix_regex(prefix: pathlib.Path|str) -> re.Pattern[str]:
    '''Match `prefix` and paths beneath it, but not siblings that share the prefix (`/a/b` vs `/a/bc`).'''
    return re.compile(f"^{re.escape(str(prefix).rstrip('/'))}(?:/|$)")

