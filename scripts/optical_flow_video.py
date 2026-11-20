"""Estimate dense optical flow for a video, cache it, and optionally render it two ways.

A thin command-line wrapper over `mediatools.vision.FlowVideo` (the same code the app's
optical-flow job runs). By default this only fills the flow cache. Each output is enabled by
giving it a filename:

  --overlay-output FILE    the source frame with the flow drawn on top: a color-wheel
                           layer (hue = direction, brightness = speed) blended in, plus a
                           sparse grid of motion arrows.
  --particles-output FILE  particles on a black background that drift with the flow. A
                           particle's velocity is the flow at its exact sub-pixel position
                           (bilinear interpolation). Each frame's flow is integrated in
                           --particle-substeps smaller steps, re-sampling the velocity each
                           time so paths curve with the field. Particles that leave the
                           frame or reach --particle-lifetime frames respawn at random.
                           Trails come from fading the previous frame by --particle-fade.

Computed flow is cached on disk, one file per frame pair, keyed by the video (path, size,
modification time), the algorithm and its parameters, `--step`, and `--cache-height`. Any
run, whatever its `--max-frames`, only computes the frame pairs that are not cached yet, so
extending 500 frames to 1000 computes just the new 500 and shrinking back to 500 computes
nothing. Flow is stored downscaled to `--cache-height` rows (float16) to keep the cache
small, and upscaled when rendering; both fresh and cached runs go through that same
round trip, so their output is identical. With no `--max-frames`, the whole video is
processed.

Usage:
    python scripts/optical_flow_video.py VIDEO [--algorithm raft|dis|farneback] [--step N]
        [--max-frames M] [--cache-dir DIR] [--recompute]
        [--overlay-output FILE [--side-by-side] [--alpha A] [--arrow-every PX]]
        [--particles-output FILE [--particle-count N] [--particle-fade F]]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from mediatools.vision import (
    DEFAULT_CACHE_DIR,
    FlowSettings,
    FlowVideo,
    OverlayOptions,
    ParticleOptions,
)


def add_flow_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--algorithm", choices=["raft", "dis", "farneback"], default="dis",
                        help="flow estimator; raft is the most accurate, dis the fastest on CPU")  # fmt: skip
    parser.add_argument("--step", type=int, default=1, help="estimate flow between frames N apart")
    parser.add_argument("--dis-preset", choices=["ultrafast", "fast", "medium"], default="medium")
    parser.add_argument("--raft-max-height", type=int, default=360, help="downscale frames to this height for RAFT")
    parser.add_argument("--raft-variant", choices=["small", "large"], default="small")
    parser.add_argument("--raft-flow-updates", type=int, default=None,
                        help="RAFT refinement iterations (model default if unset); more is slower, not larger in memory")  # fmt: skip
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="where computed flow is stored")
    parser.add_argument("--cache-height", type=int, default=360,
                        help="store flow downscaled to this many rows (0 = full resolution, much larger files)")  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("video", type=Path)
    add_flow_args(parser)
    parser.add_argument("--max-frames", type=int, default=None, help="only process the first M frame pairs")
    parser.add_argument("--device", default=None, help="torch device for RAFT, e.g. cuda or cpu")
    parser.add_argument("--recompute", action="store_true", help="ignore cached flow and overwrite it")

    overlay = parser.add_argument_group("overlay video")
    overlay.add_argument("--overlay-output", type=Path, default=None, help="write the flow overlay video here")
    overlay.add_argument("--side-by-side", action="store_true", help="show the original frame next to the overlay")
    overlay.add_argument("--alpha", type=float, default=0.5, help="opacity of the color-wheel layer (0-1)")
    overlay.add_argument("--max-flow", type=float, default=None,
                         help="flow (pixels) that maps to full brightness; default 2%% of width per step")  # fmt: skip
    overlay.add_argument("--arrow-every", type=int, default=48, help="arrow grid spacing in pixels; 0 disables arrows")
    overlay.add_argument("--arrow-scale", type=float, default=3.0, help="arrow length multiplier")

    particles = parser.add_argument_group("particle video")
    particles.add_argument("--particles-output", type=Path, default=None, help="write the particle video here")
    particles.add_argument("--particle-count", type=int, default=4000, help="number of particles")
    particles.add_argument("--particle-lifetime", type=int, default=90, help="frames before a particle respawns")
    particles.add_argument("--particle-fade", type=float, default=0.85,
                           help="fraction of the previous frame kept each frame; higher = longer trails (0-1)")  # fmt: skip
    particles.add_argument("--particle-substeps", type=int, default=4, help="integration steps per frame of flow")
    particles.add_argument("--particle-seed", type=int, default=0, help="random seed for particle placement")
    particles.add_argument("--particle-white", action="store_true", help="draw particles white, not colored by direction")
    particles.add_argument("--particle-height", type=int, default=720,
                           help="particle video height, keeping aspect (0 = source size)")  # fmt: skip
    args = parser.parse_args()

    if not 0.0 <= args.alpha <= 1.0:
        parser.error("--alpha must be between 0 and 1")
    if args.particle_height < 0:
        parser.error("--particle-height must be >= 0")
    if args.particle_count < 1 or args.particle_lifetime < 1 or args.particle_substeps < 1:
        parser.error("--particle-count, --particle-lifetime and --particle-substeps must be >= 1")
    if not 0.0 <= args.particle_fade < 1.0:
        parser.error("--particle-fade must be in [0, 1)")
    if args.max_frames is not None and args.max_frames < 1:
        parser.error("--max-frames must be >= 1")
    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")
    try:
        settings = FlowSettings(
            algorithm=args.algorithm,
            step=args.step,
            cache_height=args.cache_height,
            dis_preset=args.dis_preset,
            raft_max_height=args.raft_max_height,
            raft_variant=args.raft_variant,
            raft_flow_updates=args.raft_flow_updates,
            device=args.device,
        )
    except ValueError as e:
        parser.error(str(e))

    flow = FlowVideo(args.video, settings, args.cache_dir, args.max_frames)
    missing = flow.missing(args.recompute)
    print(f"{len(flow.pairs) - len(missing)}/{len(flow.pairs)} flows cached in {flow.cache.directory}")
    for done, _ in enumerate(flow.compute(missing), 1):
        if done % 50 == 0:
            print(f"computed {done}/{len(missing)} flows")

    overlay_options = None
    if args.overlay_output is not None:
        overlay_options = OverlayOptions(
            output=args.overlay_output,
            side_by_side=args.side_by_side,
            alpha=args.alpha,
            max_flow=args.max_flow,
            arrow_every=args.arrow_every,
            arrow_scale=args.arrow_scale,
        )
    particle_options = None
    if args.particles_output is not None:
        particle_options = ParticleOptions(
            output=args.particles_output,
            count=args.particle_count,
            lifetime=args.particle_lifetime,
            fade=args.particle_fade,
            substeps=args.particle_substeps,
            seed=args.particle_seed,
            white=args.particle_white,
            height=args.particle_height,
        )
    if overlay_options is None and particle_options is None:
        print("no outputs requested; pass --overlay-output and/or --particles-output to render")
        return

    written = 0
    for written in flow.render(overlay_options, particle_options):
        if written % 50 == 0:
            print(f"rendered {written} frames")
    for label, options in (("overlay", overlay_options), ("particles", particle_options)):
        if options is not None:
            print(f"wrote {written} {label} frames to {options.output}")


if __name__ == "__main__":
    main()
