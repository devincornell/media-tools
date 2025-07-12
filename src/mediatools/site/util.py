
import urllib
import urllib.parse
import jinja2
import pathlib
import os
from collections import defaultdict


def fname_to_title(fname: str, max_char: int = 150) -> str:
    """Convert a file name to a human-readable title."""
    replaced = fname.replace('_', ' ').replace('-', ' ')
    return ' '.join(replaced.strip().split()).title()[:max_char]

def fname_to_id(fname: str) -> str:
    """Convert a file name to a URL-friendly ID."""
    return '-'.join(fname.strip().split())

def parse_url(urlstr: str) -> str:
    """Parse a URL string and return a properly encoded URL."""
    try:
        return urllib.parse.quote(urlstr)
    except TypeError as e:
        return ''

def read_template(template_path: str | pathlib.Path) -> jinja2.Template:
    '''Read template file and return jinja2 template object.'''
    with pathlib.Path(template_path).open('r') as f:
        template_html = f.read()
    environment = jinja2.Environment()
    return environment.from_string(template_html)

