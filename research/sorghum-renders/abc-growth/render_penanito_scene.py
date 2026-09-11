#!/usr/bin/env python3
"""Render orbit videos of Penanito's contributed scenes, as authored.

Unlike `render_genotype_weeks.py`, this script does not build a planting grid of
its own. It loads a scene exactly as Penanito committed it - the preserved
per-plant seeds, the authored spacing, the PAR-bar context and the project's own
materials - and only moves the camera.

Geometry is rebuilt with `MaterializeSorghumLsPlantGeometry`, which restores from
the stored per-plant state. It does NOT reseed, so the 20-seed field realization
that passed the August 11 endpoint tolerances is preserved. Never substitute
`GrowSorghumLsPlantsToAdulthood` with a seed base here - that would discard it.

    python render_penanito_scene.py --scene genotype_c_2x10 --orbit 120
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT_ROOT = EVOENGINE / "Resources" / "DigitalAgricultureProject"

# Scenes contributed on Penanito's codex/sorghum-gpu-field-geometry branch.
SCENES = {
    "genotype_c_2x10": {
        "project": "test_lsystem_sorghum_genotype_c_aug11_2x10.eveproj",
        "scene": "GeneratedAssets/Experiments/Sorghum2026_C_2x10_2026-08-11/Scenes/"
                 "Sorghum_C_2x10_Final_2026-08-11.evescene",
        "label": "Genotype C 2x10, August 11 final snapshot",
    },
    "field_6x10": {
        "project": "test_lsystem_sorghum.eveproj",
        "scene": "GeneratedAssets/Experiments/Sorghum2026_6x10_2026-08-11/Scenes/"
                 "Sorghum_6x10_FinalSnapshot2026-08-11.evescene",
        "label": "2026 6x10 A/B/C field, August 11 final snapshot",
    },
    "stage01_6x10": {
        "project": "test_lsystem_sorghum.eveproj",
        "scene": "GeneratedAssets/Experiments/Sorghum2026_6x10/Scenes/"
                 "Sorghum_6x10_MeasurementStage01.evescene",
        "label": "2026 6x10 measurement stage 01",
    },
}


def configure_engine_imports() -> None:
    paths = (
        BUILD / "PythonBinding" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG / "Packages",
        BUILD / "EvoEngine_SDK" / CONFIG,
        BUILD / "EvoEngine_Services" / "CudaModule" / CONFIG,
    )
    sys.path.insert(0, str(paths[0]))
    sys.path.insert(0, str(EVOENGINE / "PythonBinding"))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def vec3(evo, values) -> object:
    result = evo.Vec3()
    result.x, result.y, result.z = (float(v) for v in values)
    return result


def scene_bounds(records):
    def read(record, name):
        value = getattr(record, name)
        return float(value.x), float(value.y), float(value.z)

    lows = [read(r, "geometry_min_position") for r in records]
    highs = [read(r, "geometry_max_position") for r in records]
    return (tuple(min(v[i] for v in lows) for i in range(3)),
            tuple(max(v[i] for v in highs) for i in range(3)))


def orbit_camera(low, high, aspect, fov_deg, elevation_deg, azimuth_deg, margin=1.45):
    """Fixed-radius orbit, framed on the larger ground span so nothing breathes."""
    centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
    span_y = high[1] - low[1]
    span_ground = max(high[0] - low[0], high[2] - low[2])

    half = max(span_y * 0.5, span_ground * 0.5 / max(aspect, 1e-3))
    distance = half / math.tan(math.radians(fov_deg) * 0.5) * margin

    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    target = (centre[0], low[1] + span_y * 0.45, centre[2])
    position = (target[0] + distance * math.cos(elevation) * math.cos(azimuth),
                low[1] + distance * math.sin(elevation) + span_y * 0.20,
                target[2] + distance * math.cos(elevation) * math.sin(azimuth))
    return position, target, (0.0, 1.0, 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scene", choices=sorted(SCENES), default="genotype_c_2x10")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--orbit", type=int, default=120, help="frames for a full 360")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fov", type=float, default=38.0)
    parser.add_argument("--elevation", type=float, default=17.0)
    parser.add_argument("--ground-size", type=float, default=600.0,
                        help="presentation ground skirt in metres; the 160 m default "
                             "leaves a visible edge against the sky at low camera angles")
    parser.add_argument("--margin", type=float, default=1.45,
                        help="framing slack; 1.0 exactly fills the frame")
    parser.add_argument("--quality", type=int, default=5,
                        help="x264 quality 0-10; 5 is visually equal to 8 here at ~1/14 the size")
    parser.add_argument("--gif", action="store_true", help="also write an animated GIF")
    parser.add_argument("--no-parbar", action="store_true",
                        help="strip the PAR-bar rig; it is part of the authored scene")
    parser.add_argument("--warmup-frames", type=int, default=6)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    spec = SCENES[args.scene]
    project = PROJECT_ROOT / spec["project"]
    if not project.is_file():
        raise SystemExit(f"missing project: {project}")

    if args.output is None:
        args.output = Path(__file__).parent / "penanito-scenes" / f"{args.scene}_orbit.mp4"
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402
    from sorghum_4x10_presentation import (  # noqa: E402
        DEFAULT_PROFILE, apply_photo_grade, configure_lighting, set_ground_extension,
    )
    import imageio.v2 as imageio  # noqa: E402
    import numpy as np  # noqa: E402
    from PIL import Image  # noqa: E402

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    print(f"scene: {spec['label']}", flush=True)
    if not evo.RunLSystemSorghumProject(str(project), str(packages), spec["scene"]):
        raise SystemExit(f"failed to load {spec['scene']}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("scene never became idle")

    if args.no_parbar and hasattr(evo, "RemoveParbarContext"):
        print(f"removed parbar entities: {int(evo.RemoveParbarContext())}", flush=True)

    # Rebuild geometry from the stored per-plant state. Seed-preserving by design.
    materialized = int(evo.MaterializeSorghumLsPlantGeometry(True))
    print(f"materialized {materialized} plants (seeds preserved)", flush=True)
    if materialized == 0:
        raise SystemExit(
            "no plants to materialize - this is a planting-marker template, not a final "
            "snapshot. Use render_genotype_weeks.py for marker scenes, or pick a "
            "Scenes/*Final*.evescene here.")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("geometry never became idle")

    configure_lighting(evo, DEFAULT_PROFILE)
    # Widen the ground skirt: the 160 m default shows its own edge against the
    # sky once the camera sits low enough to see the horizon.
    if not int(evo.ConfigurePresentationGroundExtension(
            True, args.ground_size, DEFAULT_PROFILE.ground_texture_repeat_m,
            DEFAULT_PROFILE.ground_extension_grid_spacing_m)):
        set_ground_extension(evo, True, DEFAULT_PROFILE)

    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    if not records:
        raise SystemExit("no plants reported")
    heights = [float(r.plant_height_m) for r in records]
    print(f"plants: {len(records)}  height min={min(heights):.2f} "
          f"max={max(heights):.2f} mean={sum(heights)/len(heights):.2f} m", flush=True)
    low, high = scene_bounds(records)
    if (high[1] - low[1]) < 0.05:
        raise SystemExit("geometry is flat - materialization failed")

    scratch = args.output.with_name(f".{args.output.stem}.frame.png")
    frames = []
    for index in range(args.orbit):
        azimuth = 360.0 * index / args.orbit
        position, target, up = orbit_camera(low, high, args.width / args.height,
                                            args.fov, args.elevation, azimuth, args.margin)
        if not evo.SetMainCameraLookAt(vec3(evo, position), vec3(evo, target),
                                       vec3(evo, up), float(args.fov)):
            raise SystemExit("failed to place the camera")
        evo.LoopFrames(args.warmup_frames)
        if not evo.CaptureCurrentScene(args.width, args.height, str(scratch), args.warmup_frames):
            raise SystemExit(f"capture failed on frame {index}")
        apply_photo_grade(scratch, scratch, DEFAULT_PROFILE)
        frames.append(np.asarray(Image.open(scratch).convert("RGB")).copy())
        if (index + 1) % 20 == 0 or index + 1 == args.orbit:
            print(f"  {index + 1}/{args.orbit} frames", flush=True)
    scratch.unlink(missing_ok=True)

    if frames[0].max() == 0:
        raise SystemExit("frames came back black")

    with imageio.get_writer(args.output, fps=args.fps, codec="libx264",
                            quality=args.quality, macro_block_size=8) as writer:
        for frame in frames:
            writer.append_data(frame)
    print(f"wrote {args.output} ({len(frames)} frames, "
          f"{args.output.stat().st_size / 1e6:.1f} MB)", flush=True)

    if args.gif:
        gif = args.output.with_suffix(".gif")
        images = [Image.fromarray(f) for f in frames]
        palette = images[len(images) // 2].convert("P", palette=Image.ADAPTIVE, colors=256)
        quantised = [im.quantize(palette=palette, dither=Image.FLOYDSTEINBERG) for im in images]
        quantised[0].save(gif, save_all=True, append_images=quantised[1:],
                          duration=int(round(1000.0 / max(args.fps, 1e-3))), loop=0, optimize=True)
        print(f"wrote {gif} ({gif.stat().st_size / 1e6:.1f} MB)", flush=True)

    evo.Terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
