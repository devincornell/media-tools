"""Track objects in a video, then render an annotated copy with boxes and motion trails.

Usage:
    python scripts/track_objects_video.py VIDEO [-o OUTPUT] [--point-every N] [--max-frames M]
"""
from __future__ import annotations

import argparse
import colorsys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

from mediatools.video.h264_writer import H264Writer
from mediatools.vision import ObjectTracker, TrackedFrame, TrackId

Color = tuple[int, int, int]
Point = tuple[int, int]


def color_for_track(track_id: TrackId) -> Color:
    """Deterministic, well-separated BGR color per track (golden-ratio hue spacing)."""
    hue = (track_id * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


COCO_PERSON_CLASS_ID = 0
DEFAULT_TRACKER = Path(__file__).parent / "botsort_persistent.yaml"


def extract_tracks(
    video: Path,
    max_frames: int | None,
    people_only: bool,
    model: str,
    tracker_cfg: str,
    conf: float,
    imgsz: int,
) -> list[TrackedFrame]:
    tracker = ObjectTracker(
        model=model,
        tracker=tracker_cfg,
        conf=conf,
        classes=[COCO_PERSON_CLASS_ID] if people_only else None,
        imgsz=imgsz,
    )
    frames: list[TrackedFrame] = []
    for i, frame in enumerate(tracker.track_video(video)):
        if max_frames is not None and i >= max_frames:
            break
        frames.append(frame)
        if (i + 1) % 100 == 0:
            print(f"tracked {i + 1} frames")
    return frames


def sample_trails(frames: list[TrackedFrame], every: int) -> dict[TrackId, list[tuple[int, Point]]]:
    """Box-center points per track, sampled every `every` frames."""
    trails: dict[TrackId, list[tuple[int, Point]]] = defaultdict(list)
    for idx, frame in enumerate(frames):
        if idx % every != 0:
            continue
        for obj in frame:
            b = obj.bounding_box
            center = (int((b.x_min + b.x_max) / 2), int((b.y_min + b.y_max) / 2))
            trails[obj.track_id].append((idx, center))
    return trails


def render(
    video: Path,
    output: Path,
    frames: list[TrackedFrame],
    trails: dict[TrackId, list[tuple[int, Point]]],
) -> None:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    writer = H264Writer(output, fps, size)

    thickness = max(2, size[0] // 640)
    try:
        for idx, tracked in enumerate(frames):
            success, image = cap.read()
            if not success:
                raise RuntimeError(f"Video ended at frame {idx}, expected {len(frames)} frames")

            # Draw trails first so boxes stay on top.
            for track_id, points in trails.items():
                color = color_for_track(track_id)
                visible = [p for f, p in points if f <= idx]
                for a, b in zip(visible, visible[1:]):
                    cv2.line(image, a, b, color, thickness)
                for p in visible:
                    cv2.circle(image, p, thickness * 2, color, -1)

            for obj in tracked:
                box = obj.bounding_box
                color = color_for_track(obj.track_id)
                p1, p2 = (int(box.x_min), int(box.y_min)), (int(box.x_max), int(box.y_max))
                cv2.rectangle(image, p1, p2, color, thickness)
                cv2.putText(
                    image,
                    f"{obj.track_id} {obj.class_name} {obj.confidence:.2f}",
                    (p1[0], max(p1[1] - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    thickness * 0.5,
                    color,
                    thickness,
                )
            writer.write(image)
    finally:
        cap.release()
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--point-every", type=int, default=10, help="sample a trail point every N frames")
    parser.add_argument("--max-frames", type=int, default=None, help="only process the first M frames")
    parser.add_argument("--people-only", action="store_true", help="only track the 'person' class")
    parser.add_argument("--model", default="yolo11n.pt", help="detector weights, e.g. yolo11s.pt, yolo11m.pt")
    parser.add_argument(
        "--tracker",
        default=str(DEFAULT_TRACKER),
        help="tracker yaml: bytetrack.yaml, botsort.yaml, or a custom path",
    )
    parser.add_argument("--conf", type=float, default=0.25, help="detection confidence threshold")
    parser.add_argument("--imgsz", type=int, default=1280, help="detector input size; larger finds smaller people")
    args = parser.parse_args()

    if args.point_every < 1:
        parser.error("--point-every must be >= 1")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    output = args.output or Path(f"{args.video.stem}_tracked.mp4")

    frames = extract_tracks(
        args.video, args.max_frames, args.people_only, args.model, args.tracker, args.conf, args.imgsz
    )
    track_lengths = Counter(o.track_id for f in frames for o in f)
    mean_len = sum(track_lengths.values()) / max(len(track_lengths), 1)
    print(f"extracted detections for {len(frames)} frames, "
          f"{len(track_lengths)} unique tracks, mean track length {mean_len:.1f} frames")

    trails = sample_trails(frames, args.point_every)
    render(args.video, output, frames, trails)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
