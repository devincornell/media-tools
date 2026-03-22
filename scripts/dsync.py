import os
import hashlib
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from fabric import Connection

def parallel_upload(host, user, local_path, remote_path, chunks=4, key_path=None):
    """
    Splits a file, uploads chunks in parallel, recombines them, 
    and verifies integrity via SHA256.
    """
    file_size = os.path.getsize(local_path)
    chunk_size = file_size // chunks
    remote_parts = []
    
    # Connection settings
    conn_args = {"key_filename": key_path} if key_path else {}
    
    def transfer_chunk(idx):
        # Create a connection per thread to avoid socket sharing issues
        with Connection(host=host, user=user, connect_kwargs=conn_args) as c:
            start = idx * chunk_size
            # Last chunk takes the remainder of the file
            size = chunk_size if idx < chunks - 1 else file_size - start
            
            part_name = f"{remote_path}.part{idx}"
            local_part_path = os.path.join(tmpdir, f"part{idx}")
            
            # Read and write the specific slice locally
            with open(local_path, "rb") as f_src:
                f_src.seek(start)
                with open(local_part_path, "wb") as f_tmp:
                    f_tmp.write(f_src.read(size))
            
            print(f"[Chunk {idx}] Uploading {size} bytes...")
            c.put(local_part_path, remote=part_name)
            return part_name

    with TemporaryDirectory() as tmpdir:
        # 1. Parallel Upload
        with ThreadPoolExecutor(max_workers=chunks) as executor:
            remote_parts = list(executor.map(transfer_chunk, range(chunks)))

        # 2. Recombine and Cleanup
        with Connection(host=host, user=user, connect_kwargs=conn_args) as c:
            print("Recombining on remote...")
            parts_str = " ".join(remote_parts)
            c.run(f"cat {parts_str} > {remote_path} && rm {parts_str}")

            # 3. Integrity Check
            print("Verifying SHA256...")
            local_hash = hashlib.sha256(open(local_path, 'rb').read()).hexdigest()
            remote_hash_raw = c.run(f"sha256sum {remote_path}", hide=True).stdout
            remote_hash = remote_hash_raw.split()[0]

            if local_hash == remote_hash:
                print("✅ Success: Integrity verified.")
                return True
            else:
                print("❌ Error: Checksum mismatch!")
                return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parallel file upload with integrity check.")
    parser.add_argument("host", help="Remote host (e.g., 1.2.3.4)")
    parser.add_argument("user", help="Remote user (e.g., ubuntu)")
    parser.add_argument("local_path", help="Local file path to upload")
    parser.add_argument("remote_path", help="Remote file path to save")
    parser.add_argument("--chunks", type=int, default=4, help="Number of chunks to split the file into")
    parser.add_argument("--key", help="Path to SSH private key")
    args = parser.parse_args()

    parallel_upload(args.host, args.user, args.local_path, args.remote_path, chunks=args.chunks, key_path=args.key)
