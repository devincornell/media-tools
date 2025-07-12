



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

file_paths = glob.glob('/AddStorage/personal/dwhelper/**/*.mp4', recursive=True)

# Recursive defaultdict for tree
def make_tree():
    return defaultdict(make_tree)

# Insert a path into the tree
def insert_path(tree, path):
    parts = path.strip(os.sep).split(os.sep)
    for part in parts[:-1]:  # all directories
        tree = tree[part]
    tree[parts[-1]] = None  # file

# Build tree
tree = make_tree()
for path in file_paths:
    insert_path(tree, path)

# Optional: Pretty print the tree
#def print_tree(d, indent=0):
#    for key, value in d.items():
#        print("    " * indent + str(key))
#        if isinstance(value, dict):
#            print_tree(value, indent + 1)

#print_tree(tree)

print(tree.keys())





