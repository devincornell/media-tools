import pathlib

import sys
sys.path.append('../src')
import mediatools

if __name__ == '__main__':

    # Example usage
    root_path = pathlib.Path('/AddStorage/personal/dwhelper/')
    #file_tree = mediatools.build_file_tree(root_path)
    #mdir = mediatools.MediaDir.from_dict(file_tree)
    mdir = mediatools.MediaDir.from_path(root_path, use_absolute=False)

    #mediatools.print_tree(file_tree)
    print(mdir)
    for subdir in mdir.subdirs:
        print(f'Subdir: {subdir.fpath}')
        for video in subdir.videos:
            print(f'  Video: {video.fpath}')
        for image in subdir.images:
            print(f'  Image: {image.fpath}')
        for other_file in subdir.other_files:
            print(f'  Other file: {other_file}')

    # Print the tree structure
    #print_tree(file_tree)
    
    # Optionally, you can save this tree to a file or use it as needed
    # with open('file_tree.txt', 'w') as f:
    #     f.write(str(file_tree))



