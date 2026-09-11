#!/usr/bin/env python3
"""Step A, B and C through their per-week descriptors along the field GDD axis.

Each week is a separate .sorghumls fitted to that week's field measurements
(`build_weekly_descriptors.py`), so this steps rather than interpolates: bind
week N, regenerate, hold, move on. That keeps tillers and the fitted leaf pitch
and yaw, none of which the growth-stages (.sgs) path can carry - `SorghumState`
has no tiller representation at all.

Snapshot morphology stays ENABLED here, unlike `render_abc_growth.py`. There the
point was to let GDD drive development from one endpoint descriptor; here every
week already is a measured endpoint, so each should render its full topology.

    python render_weekly_gdd.py --hold 15
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import sys
from pathlib import Path

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT_ROOT = EVOENGINE / "Resources" / "DigitalAgricultureProject"
PROJECT = PROJECT_ROOT / "test_lsystem_sorghum.eveproj"
TEMPLATE_SCENE = Path("ManualAssets/Scenes/Sorghum_6x10_2026.evescene")

WEEKLY_DIR = EVOENGINE / "Resources" / "HandoffTest" / "Assets" / "Descriptors" / "weekly"
TRAJECTORY_DIR = EVOENGINE / "Resources" / "HandoffTest" / "Assets" / "Descriptors" / "trajectory"
STAGE_DIR_NAME = "WeeklyTuned"
FIELD_CSV = Path(os.environ.get("SORGHUM_FIELD_CSV",
                    Path(__file__).resolve().parent.parent / "data"
                    / "sorghum_all_weeks_long_gdd.csv"))
GDD_COLUMN = "gdd_cumulative_F_8655"
GENOTYPES = ("A", "B", "C")

SEED = 202_609_020
LEAF_VERTICAL_SUBDIVISION_M = 0.01
LEAF_HORIZONTAL_SUBDIVISIONS = 6


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


def field_weeks() -> dict[int, tuple[str, float]]:
    weeks: dict[int, tuple[str, float]] = {}
    with FIELD_CSV.open() as handle:
        for row in csv.DictReader(handle):
            gdd = row[GDD_COLUMN].strip()
            if gdd:
                weeks[int(row["week"])] = (row["date"], float(gdd))
    return dict(sorted(weeks.items()))


def stage_trajectory() -> tuple[list[dict], dict[int, dict[str, str]]]:
    """Stage the interpolated trajectory steps, one file per step per genotype."""
    import json
    manifest_path = TRAJECTORY_DIR / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"missing {manifest_path} - run build_plant_trajectory.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage = PROJECT_ROOT / "Assets" / (STAGE_DIR_NAME + "Traj")
    stage.mkdir(parents=True, exist_ok=True)
    staged = {}
    for entry in manifest:
        step = entry["step"]
        mapping = {}
        for genotype in GENOTYPES:
            name = f"Genotype{genotype}_t{step:03d}.sorghumls"
            shutil.copy2(TRAJECTORY_DIR / name, stage / name)
            mapping[f"Genotype{genotype}"] = f"{STAGE_DIR_NAME}Traj/{name}"
        staged[step] = mapping
    return manifest, staged


def stage_all_weeks(weeks) -> dict[int, dict[str, str]]:
    """Stage every week under its own filename.

    One file per week matters: the engine caches assets by path, so reusing a
    single filename and rewriting it in place serves the first week's geometry
    for the whole run.
    """
    stage = PROJECT_ROOT / "Assets" / STAGE_DIR_NAME
    stage.mkdir(parents=True, exist_ok=True)
    by_week: dict[int, dict[str, str]] = {}
    for week in weeks:
        mapping = {}
        for genotype in GENOTYPES:
            name = f"Genotype{genotype}_w{week}.sorghumls"
            source = WEEKLY_DIR / name
            if not source.is_file():
                raise SystemExit(f"missing {source} - run build_weekly_descriptors.py first")
            shutil.copy2(source, stage / name)
            mapping[f"Genotype{genotype}"] = f"{STAGE_DIR_NAME}/{name}"
        by_week[week] = mapping
    return by_week


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


def fixed_camera(low, high, aspect, fov_deg, elevation_deg, azimuth_deg, margin):
    centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
    span_y = high[1] - low[1]
    span_ground = max(high[0] - low[0], high[2] - low[2])
    half = max(span_y * 0.5, span_ground * 0.5 / max(aspect, 1e-3))
    distance = half / math.tan(math.radians(fov_deg) * 0.5) * margin
    elevation, azimuth = math.radians(elevation_deg), math.radians(azimuth_deg)
    target = (centre[0], low[1] + span_y * 0.42, centre[2])
    position = (target[0] + distance * math.cos(elevation) * math.cos(azimuth),
                low[1] + distance * math.sin(elevation) + span_y * 0.18,
                target[2] + distance * math.cos(elevation) * math.sin(azimuth))
    return position, target, (0.0, 1.0, 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--trajectory", action="store_true",
                        help="render the smoothed continuous single plant from "
                             "build_plant_trajectory.py instead of stepping the 8 weekly fits")
    parser.add_argument("--hold", type=int, default=15, help="frames held on each week")
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fov", type=float, default=36.0)
    parser.add_argument("--elevation", type=float, default=13.0)
    parser.add_argument("--azimuth", type=float, default=0.0)
    parser.add_argument("--margin", type=float, default=1.30)
    parser.add_argument("--spacing", type=float, default=0.85)
    parser.add_argument("--ground-size", type=float, default=600.0)
    parser.add_argument("--quality", type=int, default=5)
    parser.add_argument("--no-overlay", action="store_true")
    parser.add_argument("--warmup-frames", type=int, default=6)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    weeks = field_weeks()
    if args.output is None:
        args.output = Path(__file__).parent / "abc-growth" / "genotypeABC_weekly_gdd.mp4"
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
    from PIL import Image, ImageDraw, ImageFont  # noqa: E402

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(packages), str(TEMPLATE_SCENE)):
        raise SystemExit("failed to load the template scene")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("scene never became idle")
    evo.RemoveParbarContext()

    labels = [f"Genotype{g}" for g in GENOTYPES]
    if int(evo.ConfigureSorghumLsPlantingGrid(labels, 1, args.spacing, args.spacing)) != 3:
        raise SystemExit("expected 3 planting markers")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != 3:
        raise SystemExit("failed to instantiate the three plants")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != 3:
        raise SystemExit("failed to sit the plants on the ground")
    evo.ConfigureSorghumLsLeafMeshQuality(
        LEAF_VERTICAL_SUBDIVISION_M, LEAF_HORIZONTAL_SUBDIVISIONS, False, True, False)
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise SystemExit("failed to establish the soil context")
    configure_lighting(evo, DEFAULT_PROFILE)
    if not int(evo.ConfigurePresentationGroundExtension(
            True, args.ground_size, DEFAULT_PROFILE.ground_texture_repeat_m,
            DEFAULT_PROFILE.ground_extension_grid_spacing_m)):
        set_ground_extension(evo, True, DEFAULT_PROFILE)

    if args.trajectory:
        manifest, staged = stage_trajectory()
        sequence = [(e["step"], f"week {e['week_low']}", e["date_low"], e["gdd"]) for e in manifest]
    else:
        staged = stage_all_weeks(weeks)
        sequence = [(w, f"week {w}", d, g) for w, (d, g) in weeks.items()]

    def apply_key(key: int) -> list:
        if int(evo.SetSorghumLsGenotypeDescriptors(staged[key], True, SEED)) != 3:
            raise SystemExit(f"failed to bind descriptors for {key}")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise SystemExit(f"geometry never became idle for {key}")
        return list(evo.GetSorghumLsPlantSceneMetadata(True))

    # Frame on the largest state so nothing grows out of shot later.
    widest, widest_key = None, None
    for key, *_ in sequence:
        low, high = scene_bounds(apply_key(key))
        if widest is None or (high[1] - low[1]) > (widest[1][1] - widest[0][1]):
            widest, widest_key = (low, high), key
    print(f"framing on {widest_key} (tallest canopy)", flush=True)
    screen_order = [r.cultivar.replace("Genotype", "") for r in
                    sorted(apply_key(widest_key), key=lambda r: float(r.global_position.z),
                           reverse=True)]
    print(f"screen order: {' '.join(screen_order)} (left to right)", flush=True)

    position, target, up = fixed_camera(widest[0], widest[1], args.width / args.height,
                                        args.fov, args.elevation, args.azimuth, args.margin)
    if not evo.SetMainCameraLookAt(vec3(evo, position), vec3(evo, target),
                                   vec3(evo, up), float(args.fov)):
        raise SystemExit("failed to place the camera")

    def load_font(pixels: int):
        for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, pixels)
            except OSError:
                continue
        return ImageFont.load_default()

    caption_font = load_font(max(14, args.height // 26))
    scratch = args.output.with_name(f".{args.output.stem}.frame.png")
    frames = []
    hold = 1 if args.trajectory else max(1, args.hold)

    for index, (key, label, date, gdd) in enumerate(sequence):
        records = apply_key(key)
        heights = {r.cultivar.replace("Genotype", ""): float(r.plant_height_m) for r in records}
        evo.LoopFrames(args.warmup_frames)
        if not evo.CaptureCurrentScene(args.width, args.height, str(scratch), args.warmup_frames):
            raise SystemExit(f"capture failed on {key}")
        apply_photo_grade(scratch, scratch, DEFAULT_PROFILE)
        image = Image.open(scratch).convert("RGB")
        if not args.no_overlay:
            draw = ImageDraw.Draw(image)
            pad = max(12, args.height // 40)
            step_y = int(caption_font.size * 1.25)
            summary = "  ".join(f"{k} {heights.get(k, 0):.2f}m" for k in screen_order)
            for offset, line in enumerate((f"{label}   {date}",
                                           f"{gdd:6.0f} GDD  (86/55 F)",
                                           summary + "     (left to right)")):
                y = pad + offset * step_y
                draw.text((pad + 2, y + 2), line, font=caption_font, fill=(0, 0, 0))
                draw.text((pad, y), line, font=caption_font, fill=(255, 255, 255))
        frames.extend([np.asarray(image).copy()] * hold)
        if (index + 1) % 20 == 0 or index + 1 == len(sequence):
            print(f"  {index + 1}/{len(sequence)}  {label}  {gdd:7.1f} GDD   " +
                  "  ".join(f"{k}={heights.get(k, 0):.2f}m" for k in screen_order), flush=True)
    scratch.unlink(missing_ok=True)

    if frames[0].max() == 0:
        raise SystemExit("frames came back black")
    with imageio.get_writer(args.output, fps=args.fps, codec="libx264",
                            quality=args.quality, macro_block_size=8) as writer:
        for frame in frames:
            writer.append_data(frame)
    print(f"wrote {args.output} ({len(frames)} frames, "
          f"{args.output.stat().st_size / 1e6:.1f} MB)", flush=True)

    evo.Terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
