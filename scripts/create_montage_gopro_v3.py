import pathlib
import tqdm
import dateutil.parser

import mediatools
import mediatools.ffmpeg

from montage_collections import CollectionsConfig


def get_gopro_creation_times(paths: list[pathlib.Path]) -> dict[pathlib.Path, mediatools.ffmpeg.ProbeInfo]:
    info_dict = {}
    for path in tqdm.tqdm(paths, desc="Probing videos", ncols=100):
        try:
            info = mediatools.ffmpeg.probe(path)
            if 'creation_time' in info.tags and 'GX' in path.name:
                creation_time = dateutil.parser.parse(info.tags['creation_time'])
                info_dict[path] = creation_time
        except Exception as e:
            print(f"Error probing {path}: {e}")
    return info_dict



if __name__ == '__main__':

    source_root = pathlib.Path('/mnt/HugeHDD/gopro/gopro_raw_organized')
    cc = CollectionsConfig.from_yaml('/home/devin/code/pydevin/projects/gopro/gopro_trip_spans.yaml')

    paths_to_probe = list(source_root.glob('**/*.MP4'))
    print(f"Found {len(paths_to_probe)} video files to probe.")
    probes = get_gopro_creation_times(paths_to_probe)
    print(f"Probed {len(probes)} videos.")

    output_root = pathlib.Path('/mnt/HugeHDD/gopro/compilations')

    for collection in cc.collections:
        print(f"\nCollection: {collection.title} ({collection.slug})")

        collection_paths = []
        for period in collection.periods:
            period_paths = [p for p, creation_time in probes.items() if period.start <= creation_time <= period.end]
            print(f"  Period: {period.start.date()} to {period.end.date()}: {len(period_paths)} videos")
            collection_paths.extend(period_paths)

        print(f"  Total videos for collection: {len(collection_paths)}")

        if not collection_paths:
            print("  Skipping — no videos found in any period.")
            continue

        output_root.mkdir(parents=True, exist_ok=True)
        output_path = output_root / f"{collection.slug}.mp4"

        if output_path.exists():
            print(f"  Skipping — output already exists: {output_path}")
            continue

        print(f"  Creating montage: {output_path}")
        result = mediatools.ffmpeg.create_montage(
            video_files=collection_paths,
            output_filename=str(output_path),
            clip_ratio=90,
            clip_duration=2.0,
            random_seed=0,
            width=3840,
            height=2160,
            fps=60,
            verbose=True,
        )
        print(f"  Done: {result}")

