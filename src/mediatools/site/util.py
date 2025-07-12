
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

def build_file_tree(root: pathlib.Path, pattern: str = '**/*') -> defaultdict:
    """Build a tree structure from file paths in a directory.
    
        # Example usage
        root_path = pathlib.Path('/AddStorage/personal/dwhelper/')
        file_tree = build_file_tree(root_path)

        # Print the tree structure
        print_tree(file_tree)

    """
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

