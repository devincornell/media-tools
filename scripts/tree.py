import pathlib
import os
from collections import defaultdict

# Sample list of file paths
#file_paths = [
#    "/media/music/pop/song1.mp3",
#    "/media/music/pop/song2.mp3",
#    "/media/music/rock/song3.mp3",
#    "/media/videos/movies/movie1.mp4",
#    "/media/videos/shows/show1.mkv",
#    "/documents/work/report.docx",
#]

import glob

#file_paths = glob.glob('/AddStorage/personal/dwhelper/**/*.mp4', recursive=True)

def build_file_tree(root: pathlib.Path, ignore_dirs='_thumbs') -> defaultdict:
    """Build a tree structure from file paths in a directory."""
    file_paths = [fp.relative_to(root) for fp in root.rglob('**/*') if fp.is_file()]
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

def print_tree(d, indent=0):
    """Recursively print the tree structure."""
    for key, value in d.items():
        print("  " * indent + str(key))
        if isinstance(value, dict):
            print_tree(value, indent + 1)

if __name__ == '__main__':

    # Example usage
    root_path = pathlib.Path('/AddStorage/personal/dwhelper/')
    file_tree = build_file_tree(root_path)

    # Print the tree structure
    print_tree(file_tree)
    
    # Optionally, you can save this tree to a file or use it as needed
    # with open('file_tree.txt', 'w') as f:
    #     f.write(str(file_tree))