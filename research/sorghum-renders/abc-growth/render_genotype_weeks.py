#!/usr/bin/env python3
"""Headless side-on render of one sorghum genotype, week 6 beside week 7.

Loads the 2026 field template scene (which carries the textured ground mesh),
replaces its planting plan with just two markers, points each at one of the
tuned week descriptors, grows both to adulthood and captures a low, slightly
oblique side view with the Vulkan rasterizer.

Run with the engine's conda env:
    python render_genotype_weeks.py --genotype A
"""

from __future__ import annotations

import argparse
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

# Tuned descriptors currently live in the HandoffTest project; they are staged
# into the DigitalAgriculture project so their texture handles resolve against
# the leaf atlas and soil assets that live there.
SOURCE_DESCRIPTORS = EVOENGINE / "Resources" / "HandoffTest" / "Assets" / "Descriptors"
STAGE_DIR_NAME = "HandoffTuned"
def plants_for(genotype: str, weeks=(6, 7)) -> tuple[tuple[str, str], ...]:
    """Marker label -> descriptor filename, one row per week."""
    return tuple((f"{genotype}Week{week}", f"Genotype{genotype}_week{week}.sorghumls")
                 for week in weeks)

SEED = 202_607_150
LEAF_VERTICAL_SUBDIVISION_M = 0.01   # finer than the 6x10 field: only two plants
LEAF_HORIZONTAL_SUBDIVISIONS = 6


def configure_engine_imports(build_dir: Path, config: str) -> None:
    paths = (
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    )
    sys.path.insert(0, str(paths[0]))
    # The shared presentation helpers ship with the binding sources, not the build.
    sys.path.insert(0, str(EVOENGINE / "PythonBinding"))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def stage_descriptors(plants: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """Copy the tuned descriptors into the render project, return asset-relative paths."""
    stage = PROJECT_ROOT / "Assets" / STAGE_DIR_NAME
    stage.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for label, filename in plants:
        source = SOURCE_DESCRIPTORS / filename
        if not source.is_file():
            raise FileNotFoundError(f"missing tuned descriptor: {source}")
        shutil.copy2(source, stage / filename)
        mapping[label] = f"{STAGE_DIR_NAME}/{filename}"
    return mapping


def vec3(evo, values) -> object:
    result = evo.Vec3()
    result.x, result.y, result.z = (float(v) for v in values)
    return result


def scene_bounds(records) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    def read(record, name):
        value = getattr(record, name)
        return float(value.x), float(value.y), float(value.z)

    lows = [read(r, "geometry_min_position") for r in records]
    highs = [read(r, "geometry_max_position") for r in records]
    return (
        tuple(min(v[i] for v in lows) for i in range(3)),
        tuple(max(v[i] for v in highs) for i in range(3)),
    )


def side_camera(low, high, aspect: float, fov_deg: float, elevation_deg: float, azimuth_deg: float,
                horizontal_span: float | None = None):
    """Low, slightly oblique view; the two rows read side by side.

    `horizontal_span` overrides the width being fitted. An orbit passes the larger
    of the two ground spans so the framing stays fixed as the camera swings round,
    instead of appearing to zoom in and out.
    """
    centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
    span_y = high[1] - low[1]
    span_z = high[2] - low[2] if horizontal_span is None else horizontal_span

    # Fit the taller of the plant height and the row separation, allowing for
    # the horizontal field of view being wider than the vertical one.
    half_v = span_y * 0.5
    half_h = span_z * 0.5 / max(aspect, 1e-3)
    half = max(half_v, half_h)
    distance = half / math.tan(math.radians(fov_deg) * 0.5) * 1.45

    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    offset = (
        distance * math.cos(elevation) * math.cos(azimuth),
        distance * math.sin(elevation),
        distance * math.cos(elevation) * math.sin(azimuth),
    )
    # Aim a little below mid-height so the soil stays in frame.
    target = (centre[0], low[1] + span_y * 0.42, centre[2])
    position = (target[0] + offset[0], low[1] + offset[1] + span_y * 0.20, target[2] + offset[2])
    return position, target, (0.0, 1.0, 0.0)


def nadir_camera(low, high, aspect: float, fov_deg: float, margin: float = 1.08):
    """Straight-down view, mimicking the drone orthophoto.

    Screen-up is +Z and screen-right is -X, so the row runs across the frame.
    The distance fits whichever axis is tighter against the frame.
    """
    centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
    tan_v = math.tan(math.radians(fov_deg) * 0.5)
    half_x = (high[0] - low[0]) * 0.5
    half_z = (high[2] - low[2]) * 0.5
    distance = max(half_z / tan_v, half_x / (tan_v * max(aspect, 1e-3))) * margin
    # Sit above the canopy top, not the ground, so nothing clips the near plane.
    position = (centre[0], high[1] + distance, centre[2])
    return position, (centre[0], high[1], centre[2]), (0.0, 0.0, 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genotype", choices=("A", "B", "C"), default="B")
    parser.add_argument("--week", choices=("6", "7", "both"), default="both",
                        help="render one week per scene, or both weeks as two rows")
    parser.add_argument("--output", type=Path, default=None,
                        help="defaults to tuning-genotype-<G>/genotype<G>_week6_vs_week7.png")
    parser.add_argument("--width", type=int, default=2048)
    parser.add_argument("--height", type=int, default=1152)
    parser.add_argument("--warmup-frames", type=int, default=8,
                        help="frames to settle the renderer before capturing")
    parser.add_argument("--row-spacing", type=float, default=1.30,
                        help="metres between the week-6 and week-7 rows")
    parser.add_argument("--rows", type=int, default=1,
                        help="repeat each week's row this many times, for a multi-row block")
    parser.add_argument("--columns", type=int, default=1,
                        help="plants per row; >1 renders a plot rather than a single pair")
    parser.add_argument("--column-spacing", type=float, default=0.25,
                        help="metres between plants within a row")
    parser.add_argument("--fov", type=float, default=34.0)
    parser.add_argument("--top-down", action="store_true",
                        help="straight-down orthophoto view, like the drone imagery")
    parser.add_argument("--elevation", type=float, default=11.0,
                        help="camera elevation above horizontal; low = side-on")
    parser.add_argument("--azimuth", type=float, default=12.0,
                        help="camera swing off the +X axis, for a slightly oblique side view")
    parser.add_argument("--orbit", type=int, default=0, metavar="FRAMES",
                        help="render a 360 degree orbit as an animated GIF instead of one PNG")
    parser.add_argument("--orbit-width", type=int, default=960)
    parser.add_argument("--orbit-height", type=int, default=540)
    parser.add_argument("--fps", type=float, default=15.0, help="GIF playback rate")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    genotype = args.genotype
    weeks = (6, 7) if args.week == "both" else (int(args.week),)
    plants = plants_for(genotype, weeks)
    if args.output is None:
        if args.columns > 1:
            scope = "week6_vs_week7" if len(weeks) > 1 else f"week{weeks[0]}"
            stem = f"genotype{genotype}_{scope}_plot_{len(plants)}x{args.columns}"
            if args.top_down:
                stem += "_topdown"
        else:
            stem = (f"genotype{genotype}_week6_vs_week7" if len(weeks) > 1
                    else f"genotype{genotype}_week{weeks[0]}")
        args.output = Path(__file__).parent / f"tuning-genotype-{genotype}" / f"{stem}.png"
    args.output = args.output.resolve()
    descriptors = stage_descriptors(plants)
    print(f"staged descriptors: {descriptors}", flush=True)

    configure_engine_imports(BUILD, CONFIG)
    # The runtime resolves DefaultResources/ and the shader tree relative to the
    # working directory, so it has to be the binding folder, not the caller's.
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402

    runtime_packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(runtime_packages), str(TEMPLATE_SCENE)):
        raise RuntimeError(f"failed to load {TEMPLATE_SCENE}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("template scene never became idle")

    # The 6x10 template ships PARBAR sensor masts and rails; they clutter a
    # two-plant portrait, so drop them before framing.
    if hasattr(evo, "RemoveParbarContext"):
        print(f"removed parbar context entities: {int(evo.RemoveParbarContext())}", flush=True)

    # Repeating a week's marker label gives several identical rows; the engine
    # keys descriptors by label, so every repeat draws its own seeded variation.
    labels = [label for label, _ in plants for _ in range(max(1, args.rows))]
    expected = len(labels) * max(1, args.columns)
    row_length = (max(1, args.columns) - 1) * args.column_spacing
    print(f"planting {len(labels)} rows x {args.columns} plants "
          f"({row_length:.2f} m per row, {args.column_spacing:.2f} m spacing)", flush=True)
    markers = int(evo.ConfigureSorghumLsPlantingGrid(labels, max(1, args.columns),
                                                     args.column_spacing, args.row_spacing))
    if markers != expected:
        raise RuntimeError(f"expected {expected} planting markers, got {markers}")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise RuntimeError("failed to instantiate every plant")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != expected:
        raise RuntimeError("failed to sit every plant on the ground mesh")
    if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, SEED)) != expected:
        raise RuntimeError("failed to bind the tuned week descriptors")

    evo.ConfigureSorghumLsLeafMeshQuality(
        LEAF_VERTICAL_SUBDIVISION_M, LEAF_HORIZONTAL_SUBDIVISIONS, False, True, False
    )
    # Builds the soil entity, ground mesh and soil material the scene renders on.
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("failed to establish the soil / illumination context")
    if int(evo.GrowSorghumLsPlantsToAdulthood(SEED, "", False, True)) != expected:
        raise RuntimeError("failed to grow both plants to adulthood")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("scene never became idle after growth")

    from sorghum_4x10_presentation import (
        DEFAULT_PROFILE,
        apply_photo_grade,
        configure_lighting,
        set_ground_extension,
    )

    configure_lighting(evo, DEFAULT_PROFILE)
    set_ground_extension(evo, True, DEFAULT_PROFILE)

    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    if not records:
        raise RuntimeError("no plant geometry reported")
    low, high = scene_bounds(records)
    print(f"bounds min={low} max={high}", flush=True)
    for record in sorted(records, key=lambda r: float(r.global_position.z)):
        print(f"  plant cultivar={record.cultivar} z={float(record.global_position.z):.2f} "
              f"height={float(record.plant_height_m):.2f} m", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    import numpy as np

    # A plot is long in x and shallow in z; fit whichever ground span is larger so
    # the whole block stays in frame from any azimuth.
    plot_span = max(high[0] - low[0], high[2] - low[2]) if args.columns > 1 else None

    def look_from(azimuth_deg: float, width: int, height: int, horizontal_span=None) -> None:
        if args.top_down:
            position, target, up = nadir_camera(low, high, width / height, args.fov)
        else:
            if horizontal_span is None:
                horizontal_span = plot_span
            position, target, up = side_camera(low, high, width / height, args.fov,
                                               args.elevation, azimuth_deg, horizontal_span)
        if not evo.SetMainCameraLookAt(vec3(evo, position), vec3(evo, target),
                                       vec3(evo, up), float(args.fov)):
            raise RuntimeError("failed to place the camera")

    def grab(width: int, height: int, destination: Path) -> Image.Image:
        raw = destination.with_name(f".{destination.stem}.raw.png")
        evo.LoopFrames(args.warmup_frames)
        if not evo.CaptureCurrentScene(width, height, str(raw), args.warmup_frames):
            raise RuntimeError("rasterized capture failed")
        apply_photo_grade(raw, destination, DEFAULT_PROFILE)
        image = Image.open(destination).convert("RGB").copy()
        raw.unlink(missing_ok=True)
        return image

    if args.orbit:
        # Fixed framing radius: the wider of the two ground spans, so the plants
        # neither drift out of frame nor appear to zoom as the camera swings round.
        span = max(high[0] - low[0], high[2] - low[2])
        gif = args.output.with_suffix(".gif")
        scratch = gif.with_name(f".{gif.stem}.frame.png")
        frames = []
        for index in range(args.orbit):
            azimuth = args.azimuth + 360.0 * index / args.orbit
            look_from(azimuth, args.orbit_width, args.orbit_height, span)
            frames.append(grab(args.orbit_width, args.orbit_height, scratch))
            print(f"  frame {index + 1}/{args.orbit} azimuth={azimuth % 360:6.1f}", flush=True)
        scratch.unlink(missing_ok=True)

        # One shared palette, taken from a mid-orbit frame, so colours do not
        # shimmer between frames the way per-frame adaptive palettes do.
        palette = frames[len(frames) // 2].convert("P", palette=Image.ADAPTIVE, colors=256)
        quantised = [f.quantize(palette=palette, dither=Image.FLOYDSTEINBERG) for f in frames]
        quantised[0].save(gif, save_all=True, append_images=quantised[1:],
                          duration=int(round(1000.0 / max(args.fps, 1e-3))), loop=0, optimize=True)
        print(f"wrote {gif} ({len(frames)} frames, {gif.stat().st_size / 1e6:.1f} MB)", flush=True)
        evo.Terminate()
        return 0

    look_from(args.azimuth, args.width, args.height)

    grab(args.width, args.height, args.output)
    pixels = np.asarray(Image.open(args.output).convert("RGB"), dtype=float)
    print(f"image mean={pixels.mean():.2f} max={pixels.max():.0f} "
          f"stddev={pixels.mean(axis=2).std():.2f}", flush=True)
    if pixels.max() == 0:
        raise RuntimeError("capture came back empty")
    print(f"wrote {args.output}", flush=True)

    evo.Terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
