import os
import sys
import hashlib

def compute_md5(file_path):
    """Compute MD5 hash of the specified file and return the hex digest."""
    md5_hash = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

def rename_mp4_to_md5(root_dir, ext: str = '.mp4'):
    """
    Recursively find all .mp4 files under root_dir and rename them to their MD5 hash.
    Preserves the .mp4 file extension.
    """
    for root, dirs, files in os.walk(root_dir):
        for filename in files:
            if filename.lower().endswith(ext):
                old_path = os.path.join(root, filename)
                new_filename = compute_md5(old_path) + ext
                new_path = os.path.join(root, new_filename)

                # Rename the file
                os.rename(old_path, new_path)
                print(f"Renamed: {old_path} -> {new_path}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/directory")
        sys.exit(1)
    
    directory = sys.argv[1]
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory.")
        sys.exit(1)

    for ext in ['.mp4', '.mov']:
        rename_mp4_to_md5(directory, ext=ext)
    #rename_mp4_to_md5(directory, ext='.mov')
    print("Renaming complete!")