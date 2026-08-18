#!/usr/bin/env python3
"""Render spatial reviews and an illustrative growth path for the August 11 field."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import traceback
from collections import Counter
from pathlib import Path

from sorghum_2026_6x10_aug11_data import EXPERIMENT_ID, SESSION_ID
from sorghum_2026_6x10_aug11_scene import FIELD_SEED
from sorghum_2026_6x10_data import repo_root_from_script
from sorghum_2026_6x10_gdd_timelapse import (
    FIELD_LEAF_HORIZONTAL_SUBDIVISIONS,
    FIELD_LEAF_VERTICAL_SUBDIVISION_M,
    normalized_text_sha256,
    restore_runtime_assets,
    runtime_asset_snapshot,
    shared_target_gdd,
)
from sorghum_2026_6x10_scene import GENOTYPES, configure_engine_imports
from sorghum_4x10_presentation import (
    DEFAULT_PROFILE,
    apply_photo_grade,
    configure_lighting,
    set_ground_extension,
)
from sorghum_render_4x10_mobile_review import (
    Bounds,
    apply_camera,
    bounds_to_json,
    fit_camera,
    geometry_bounds,
    metadata_position,
    record_bounds,
)
from sorghum_render_2026_6x10 import image_metrics, representative_review_plant, sha256


SCENE_ASSET = (
    Path("GeneratedAssets/Experiments")
    / EXPERIMENT_ID
    / "Scenes"
    / f"Sorghum_6x10_{SESSION_ID}.evescene"
)
DESCRIPTOR_ROOT = (
    Path("GeneratedAssets/Experiments") / EXPERIMENT_ID / "Descriptors" / "FinalSnapshot"
)
MARKER_PATTERN = re.compile(r"^(Genotype[ABC])_LSystem_R([0-5])_C([0-9])$")
EYE_HEIGHT_M = 1.65
FRAME_PATTERN = "field_%04d.png"
VIEW_SPECS = (
    ("field_perspective_southeast", "Whole field | southeast oblique"),
    ("field_perspective_northwest", "Whole field | northwest oblique"),
    ("field_top_down", "Whole field | true top-down"),
    ("field_near_top_down", "Whole field | near top-down"),
    ("field_end_along_rows", "Whole field | along rows"),
    ("field_side_across_rows", "Whole field | across rows"),
    ("genotype_a_inter_row_positive_x", "Genotype A | inter-row walk +X"),
    ("genotype_a_inter_row_negative_x", "Genotype A | inter-row walk -X"),
    ("genotype_b_inter_row_positive_x", "Genotype B | inter-row walk +X"),
    ("genotype_b_inter_row_negative_x", "Genotype B | inter-row walk -X"),
    ("genotype_c_inter_row_positive_x", "Genotype C | inter-row walk +X"),
    ("genotype_c_inter_row_negative_x", "Genotype C | inter-row walk -X"),
    ("genotype_a_intra_row", "Genotype A | within-row view"),
    ("genotype_b_intra_row", "Genotype B | within-row view"),
    ("genotype_c_intra_row", "Genotype C | within-row view"),
    ("genotype_a_plant", "Genotype A | representative morphology"),
    ("genotype_b_plant", "Genotype B | representative morphology"),
    ("genotype_c_plant", "Genotype C | representative morphology"),
)
VIEW_NAMES = tuple(name for name, _ in VIEW_SPECS)
VIEW_LABELS = dict(VIEW_SPECS)


def parse_marker(record: object) -> tuple[str, int, int]:
    match = MARKER_PATTERN.fullmatch(str(record.name))
    if not match:
        raise ValueError(f"unexpected SorghumLS plant name: {record.name}")
    return match.group(1), int(match.group(2)), int(match.group(3))


def indexed_rows(records: list[object]) -> dict[int, list[object]]:
    rows: dict[int, list[object]] = {}
    for record in records:
        _, row, _ = parse_marker(record)
        rows.setdefault(row, []).append(record)
    if set(rows) != set(range(6)) or any(len(values) != 10 for values in rows.values()):
        raise ValueError("camera planning requires one complete 6x10 field")
    return {
        row: sorted(values, key=lambda record: parse_marker(record)[2])
        for row, values in rows.items()
    }


def point_aabb_distance(point: tuple[float, float, float], bounds: Bounds) -> float:
    squared = 0.0
    for value, low, high in zip(point, bounds.minimum, bounds.maximum):
        delta = low - value if value < low else value - high if value > high else 0.0
        squared += delta * delta
    return math.sqrt(squared)


def camera_clearance(position: tuple[float, float, float], records: list[object]) -> float:
    return min(point_aabb_distance(position, record_bounds(record)) for record in records)


def camera_record(
    camera: dict[str, object],
    records: list[object],
    category: str,
    basis: dict[str, object],
) -> dict[str, object]:
    position = tuple(float(value) for value in camera["position"])
    return {
        **camera,
        "category": category,
        "placement_basis": basis,
        "camera_to_nearest_plant_aabb_m": camera_clearance(position, records),
    }


def row_axis_metrics(rows: dict[int, list[object]]) -> dict[str, object]:
    roots = [metadata_position(record) for values in rows.values() for record in values]
    x_values = sorted({position[0] for position in roots})
    spacings = [right - left for left, right in zip(x_values, x_values[1:]) if right - left > 1e-5]
    return {
        "x_min": min(position[0] for position in roots),
        "x_max": max(position[0] for position in roots),
        "column_spacing_m": statistics.median(spacings),
        "ground_y_m": statistics.median(position[1] for position in roots),
        "row_centers_z_m": {
            row: statistics.fmean(metadata_position(record)[2] for record in values)
            for row, values in rows.items()
        },
    }


def aisle_camera(
    records: list[object],
    rows: dict[int, list[object]],
    genotype: str,
    positive_x: bool,
) -> dict[str, object]:
    genotype_rows = [row for row, values in rows.items() if parse_marker(values[0])[0] == genotype]
    if len(genotype_rows) != 2:
        raise ValueError(f"{genotype}: expected exactly two field rows")
    metrics = row_axis_metrics(rows)
    row_z = [metrics["row_centers_z_m"][row] for row in genotype_rows]
    aisle_z = statistics.fmean(row_z)
    ground_y = statistics.fmean(
        metadata_position(record)[1] for row in genotype_rows for record in rows[row]
    )
    x_min, x_max = float(metrics["x_min"]), float(metrics["x_max"])
    span = x_max - x_min
    column_x = sorted(
        {
            statistics.fmean(metadata_position(rows[row][column])[0] for row in genotype_rows)
            for column in range(10)
        }
    )
    candidates = column_x + [(a + b) * 0.5 for a, b in zip(column_x, column_x[1:])]
    center_x = (x_min + x_max) * 0.5
    anchor = center_x + 0.18 * span if positive_x else center_x - 0.18 * span
    band = [
        value
        for value in candidates
        if (
            center_x + 0.05 * span <= value <= center_x + 0.34 * span
            if positive_x
            else center_x - 0.34 * span <= value <= center_x - 0.05 * span
        )
    ]
    eye_y = ground_y + EYE_HEIGHT_M
    x = max(
        band,
        key=lambda value: (
            camera_clearance((value, eye_y, aisle_z), records),
            -abs(value - anchor),
        ),
    )
    target_x = x_max - 0.05 * span if positive_x else x_min + 0.05 * span
    camera = {
        "position": (x, eye_y, aisle_z),
        "target": (target_x, ground_y + 1.35, aisle_z),
        "up": (0.0, 1.0, 0.0),
        "fov_degrees": 58.0,
    }
    return camera_record(
        camera,
        records,
        "inter_row_walking",
        {
            "genotype": genotype,
            "paired_rows": genotype_rows,
            "paired_row_centers_z_m": row_z,
            "aisle_center_z_m": aisle_z,
            "eye_height_above_local_roots_m": EYE_HEIGHT_M,
            "travel_axis": "+X" if positive_x else "-X",
            "candidate_policy": "best plant-AABB clearance beyond the central PARBAR rig, looking toward the nearest row end",
        },
    )


def intra_row_camera(
    records: list[object], rows: dict[int, list[object]], genotype: str
) -> dict[str, object]:
    candidates = []
    for row, values in rows.items():
        if parse_marker(values[0])[0] != genotype:
            continue
        ordered = sorted(values, key=lambda record: metadata_position(record)[0])
        for left, right in zip(ordered, ordered[1:]):
            left_bounds, right_bounds = record_bounds(left), record_bounds(right)
            root_midpoint = (metadata_position(left)[0] + metadata_position(right)[0]) * 0.5
            envelope_gap = right_bounds.minimum[0] - left_bounds.maximum[0]
            candidates.append((envelope_gap, row, root_midpoint, left, right))
    gap, row, x, left, right = max(candidates, key=lambda value: (value[0], -abs(value[2])))
    row_records = rows[row]
    ground_y = statistics.fmean(metadata_position(record)[1] for record in row_records)
    z = statistics.fmean(metadata_position(record)[2] for record in row_records)
    x_values = [metadata_position(record)[0] for record in row_records]
    positive_x = x <= statistics.fmean(x_values)
    target_x = max(x_values) if positive_x else min(x_values)
    camera = {
        "position": (x, ground_y + EYE_HEIGHT_M, z),
        "target": (target_x, ground_y + 1.25, z),
        "up": (0.0, 1.0, 0.0),
        "fov_degrees": 58.0,
    }
    return camera_record(
        camera,
        records,
        "intra_row_walking",
        {
            "genotype": genotype,
            "row": row,
            "gap_between": [str(left.name), str(right.name)],
            "plant_envelope_gap_m": gap,
            "eye_height_above_local_roots_m": EYE_HEIGHT_M,
            "travel_axis": "+X" if positive_x else "-X",
            "candidate_policy": "widest adjacent plant-envelope gap in either genotype row",
        },
    )


def plan_cameras(records: list[object], width: int, height: int) -> dict[str, dict[str, object]]:
    if width <= 0 or height <= 0:
        raise ValueError("camera dimensions must be positive")
    rows = indexed_rows(records)
    bounds = geometry_bounds(records)
    aspect = width / height
    overview = {
        "field_perspective_southeast": fit_camera(bounds, (1.0, 0.36, 1.0), (0.0, 1.0, 0.0), 42.0, aspect, 1.05),
        "field_perspective_northwest": fit_camera(bounds, (-1.0, 0.36, -1.0), (0.0, 1.0, 0.0), 42.0, aspect, 1.05),
        "field_top_down": fit_camera(bounds, (0.0, 1.0, 0.0), (0.0, 0.0, -1.0), 45.0, aspect, 1.05),
        "field_near_top_down": fit_camera(bounds, (0.20, 1.0, 0.16), (0.0, 0.0, -1.0), 44.0, aspect, 1.06),
        "field_end_along_rows": fit_camera(bounds, (1.0, 0.18, 0.05), (0.0, 1.0, 0.0), 48.0, aspect, 1.04),
        "field_side_across_rows": fit_camera(bounds, (0.05, 0.18, 1.0), (0.0, 1.0, 0.0), 48.0, aspect, 1.04),
    }
    cameras = {
        name: camera_record(camera, records, "whole_field", {"source": "union of 60 plant AABBs"})
        for name, camera in overview.items()
    }
    for genotype, prefix in zip(GENOTYPES, ("genotype_a", "genotype_b", "genotype_c")):
        cameras[f"{prefix}_inter_row_positive_x"] = aisle_camera(records, rows, genotype, True)
        cameras[f"{prefix}_inter_row_negative_x"] = aisle_camera(records, rows, genotype, False)
        cameras[f"{prefix}_intra_row"] = intra_row_camera(records, rows, genotype)
        genotype_rows = [row for row, values in rows.items() if parse_marker(values[0])[0] == genotype]
        facing_row = max(genotype_rows) if genotype == "GenotypeC" else min(genotype_rows)
        representative = representative_review_plant(rows[facing_row], genotype)
        outward_z = -1.0 if genotype == "GenotypeC" else 1.0
        camera = fit_camera(
            record_bounds(representative),
            (0.25, 0.18, outward_z),
            (0.0, 1.0, 0.0),
            46.0,
            aspect,
            1.12,
        )
        cameras[f"{prefix}_plant"] = camera_record(
            camera,
            records,
            "plant_morphology",
            {
                "genotype": genotype,
                "facing_row": facing_row,
                "viewed_from_field_local_z": "+Z" if outward_z > 0 else "-Z",
                "representative_plant": str(representative.name),
                "representative_plant_aabb": bounds_to_json(record_bounds(representative)),
            },
        )
    if set(cameras) != set(VIEW_NAMES):
        raise RuntimeError("the August 11 review camera set is incomplete")
    return {name: cameras[name] for name in VIEW_NAMES}


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return {row["plant_name"]: row for row in csv.DictReader(stream)}


def validate_endpoint_records(
    records: list[object], manifest_path: Path, *, require_morphology: bool
) -> dict[str, object]:
    expected = read_manifest(manifest_path)
    actual = {str(record.name): record for record in records}
    if len(actual) != 60 or actual.keys() != expected.keys():
        raise RuntimeError("rendered field does not match the 60-plant August 11 scene manifest")
    maximum_height_delta = 0.0
    for name, record in actual.items():
        row = expected[name]
        _, expected_row, expected_column = parse_marker(record)
        checks = {
            "cultivar": (str(record.cultivar), row["genotype_id"]),
            "row": (expected_row, int(row["row"])),
            "column": (expected_column, int(row["column"])),
            "seed": (int(record.seed), int(row["seed"])),
        }
        if require_morphology:
            maximum_height_delta = max(
                maximum_height_delta,
                abs(float(record.plant_height_m) - float(row["plant_height_m"])),
            )
            checks.update(
                {
                    "leaf_count": (
                        int(record.main_culm_leaf_count),
                        int(row["main_culm_leaf_count"]),
                    ),
                    "tiller_count": (
                        int(record.primary_tiller_count),
                        int(row["primary_tiller_count"]),
                    ),
                    "panicle_emerged": (
                        bool(record.panicle_emerged),
                        row["panicle_emerged"].lower() == "true",
                    ),
                }
            )
        mismatches = {field: values for field, values in checks.items() if values[0] != values[1]}
        if mismatches:
            raise RuntimeError(f"August 11 endpoint mismatch for {name}: {mismatches}")
    if require_morphology and maximum_height_delta > 1e-3:
        raise RuntimeError(f"August 11 endpoint height mismatch: {maximum_height_delta:.6f} m")
    summary = {}
    for genotype in GENOTYPES:
        group = [record for record in records if str(record.cultivar) == genotype]
        manifest_group = [row for row in expected.values() if row["genotype_id"] == genotype]
        summary[genotype] = {
            "plants": len(group),
            "mean_height_m": statistics.fmean(
                float(record.plant_height_m) for record in group
            )
            if require_morphology
            else statistics.fmean(float(row["plant_height_m"]) for row in manifest_group),
            "mean_leaf_count": statistics.fmean(
                float(record.main_culm_leaf_count) for record in group
            )
            if require_morphology
            else statistics.fmean(float(row["main_culm_leaf_count"]) for row in manifest_group),
            "mean_tiller_count": statistics.fmean(
                float(record.primary_tiller_count) for record in group
            )
            if require_morphology
            else statistics.fmean(float(row["primary_tiller_count"]) for row in manifest_group),
            "panicle_emerged_plants": sum(bool(record.panicle_emerged) for record in group)
            if require_morphology
            else sum(row["panicle_emerged"].lower() == "true" for row in manifest_group),
        }
    if Counter(str(record.cultivar) for record in records) != Counter({name: 20 for name in GENOTYPES}):
        raise RuntimeError("August 11 endpoint must contain 20 plants per genotype")
    if [summary[name]["panicle_emerged_plants"] for name in GENOTYPES] != [0, 0, 20]:
        raise RuntimeError("August 11 endpoint must preserve A/B vegetative and C panicle states")
    return {
        "status": "pass",
        "verification_mode": "live_procedural_morphology" if require_morphology else "serialized_geometry_identity_plus_saved_manifest",
        "maximum_height_delta_from_saved_scene_m": maximum_height_delta,
        "by_genotype": summary,
    }


def descriptor_paths(project_root: Path) -> dict[str, Path]:
    return {
        genotype: project_root / "Assets" / DESCRIPTOR_ROOT / f"{genotype}.sorghumls"
        for genotype in GENOTYPES
    }


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "project": args.project,
        "scene": args.project_root / "Assets" / SCENE_ASSET,
        **{f"descriptor_{name}": path for name, path in descriptor_paths(args.project_root).items()},
    }


def prepare_scene(evo: object, args: argparse.Namespace) -> list[object]:
    if not evo.RunLSystemSorghumProject(args.project, args.runtime_package_dir, SCENE_ASSET):
        raise RuntimeError(f"failed to load {SCENE_ASSET}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("August 11 scene did not become idle")
    if int(
        evo.ConfigureSorghumLsLeafMeshQuality(
            FIELD_LEAF_VERTICAL_SUBDIVISION_M,
            FIELD_LEAF_HORIZONTAL_SUBDIVISIONS,
            False,
            True,
            False,
        )
    ) != 60:
        raise RuntimeError("failed to apply the render-only field leaf LOD")
    if int(evo.SetSorghumLsFinalizeSnapshotMorphology(True)) != len(GENOTYPES):
        raise RuntimeError("failed to enable August 11 endpoint finalization")
    if int(evo.GrowSorghumLsPlantsToAdulthood(FIELD_SEED)) != 60:
        raise RuntimeError("failed to rebuild the 60-plant August 11 endpoint")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("rebuilt August 11 field did not become idle")
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("August 11 soil/illumination context is invalid")
    configure_lighting(evo)
    if set_ground_extension(evo, True) != 1:
        raise RuntimeError("failed to create the presentation-only ground extension")
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    if len(records) != 60 or any(not record.has_geometry for record in records):
        raise RuntimeError("August 11 scene must contain 60 rendered plant geometries")
    return records


def make_contact_sheet(view_rows: list[dict[str, object]], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    columns, rows = 6, 3
    tile_width, tile_height, label_height, margin, title_height = 384, 216, 42, 16, 78
    canvas = Image.new(
        "RGB",
        (margin + columns * (tile_width + margin), title_height + rows * (tile_height + label_height + margin)),
        (17, 24, 28),
    )
    draw = ImageDraw.Draw(canvas)
    regular, bold = Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\segoeuib.ttf")
    title_font = ImageFont.truetype(str(bold), 29) if bold.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(regular), 17) if regular.exists() else ImageFont.load_default()
    draw.text((margin, 18), "August 11 Sorghum 6x10 | 18-view spatial and morphology review", font=title_font, fill=(245, 248, 247))
    for index, row in enumerate(view_rows):
        grid_row, column = divmod(index, columns)
        x = margin + column * (tile_width + margin)
        y = title_height + grid_row * (tile_height + label_height + margin)
        draw.text((x, y), str(row["label"]), font=label_font, fill=(218, 227, 225))
        with Image.open(str(row["output"])).convert("RGB") as source:
            canvas.paste(ImageOps.fit(source, (tile_width, tile_height)), (x, y + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def render_stills(evo: object, args: argparse.Namespace) -> Path:
    records = prepare_scene(evo, args)
    endpoint = validate_endpoint_records(
        records, args.data_root / "scene_manifest.csv", require_morphology=True
    )
    cameras = plan_cameras(records, args.width, args.height)
    selected = [name for name in VIEW_NAMES if name in args.views]
    rows = []
    still_dir = args.output_dir / "stills"
    for index, name in enumerate(selected, start=1):
        camera = cameras[name]
        apply_camera(evo, camera)
        evo.LoopFrames(args.warmup_frames)
        raw = still_dir / ".raw" / f"{index:02d}_{name}.png"
        final = still_dir / f"{index:02d}_{name}.png"
        raw.parent.mkdir(parents=True, exist_ok=True)
        if not evo.CaptureCurrentSceneRayTraced(
            args.width,
            args.height,
            raw,
            args.still_samples,
            args.still_bounces,
            DEFAULT_PROFILE.gamma,
            args.denoiser_strength,
        ):
            raise RuntimeError(f"capture failed for {name}")
        apply_photo_grade(raw, final)
        raw.unlink(missing_ok=True)
        metrics = image_metrics(final)
        if metrics["size"] != [args.width, args.height] or metrics["luminance_stddev"] < 3.0:
            raise RuntimeError(f"{name} appears blank or has invalid dimensions")
        rows.append(
            {
                "view": name,
                "label": VIEW_LABELS[name],
                "output": str(final.resolve()),
                "sha256": sha256(final),
                "camera": camera,
                "metrics": metrics,
            }
        )
        print(f"captured still {index}/{len(selected)}: {name}", flush=True)
    contact_sheet = args.output_dir / "sorghum_6x10_aug11_18_view_contact_sheet.png"
    if selected == list(VIEW_NAMES):
        make_contact_sheet(rows, contact_sheet)
    report = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "scene_asset": SCENE_ASSET.as_posix(),
        "field_geometry_bounds": bounds_to_json(geometry_bounds(records)),
        "camera_policy": "whole-field framing, walking locations, and morphology framing derive from actual world-space plant AABBs and measured root rows",
        "walking_eye_height_m": EYE_HEIGHT_M,
        "endpoint_validation": endpoint,
        "render": {
            "renderer": "EvoEngine_OptiX",
            "width": args.width,
            "height": args.height,
            "samples": args.still_samples,
            "bounces": args.still_bounces,
            "denoiser_strength": args.denoiser_strength,
            "field_leaf_lod": {
                "vertical_subdivision_m": FIELD_LEAF_VERTICAL_SUBDIVISION_M,
                "horizontal_subdivisions": FIELD_LEAF_HORIZONTAL_SUBDIVISIONS,
            },
        },
        "view_count": len(rows),
        "views": rows,
        "contact_sheet": str(contact_sheet.resolve()) if contact_sheet.is_file() else None,
    }
    report_path = args.output_dir / "stills_render_manifest.json"
    write_json(report_path, report)
    return report_path


def frame_path(output_dir: Path, frame: int) -> Path:
    return output_dir / "animation" / "frames" / (FRAME_PATTERN % frame)


def summarize_animation_state(records: list[object]) -> dict[str, object]:
    return {
        genotype: {
            "mean_height_m": statistics.fmean(
                float(record.plant_height_m) for record in records if str(record.cultivar) == genotype
            ),
            "panicle_emerged_plants": sum(
                bool(record.panicle_emerged) for record in records if str(record.cultivar) == genotype
            ),
        }
        for genotype in GENOTYPES
    }


def encode_video(args: argparse.Namespace) -> tuple[Path, dict[str, object]]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required")
    animation_dir = args.output_dir / "animation"
    video = animation_dir / f"sorghum_6x10_aug11_endpoint_growth_{args.fps}fps.mp4"
    temporary = video.with_name(f".{video.stem}.tmp.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-framerate",
            str(args.fps),
            "-i",
            str(animation_dir / "frames" / FRAME_PATTERN),
            "-frames:v",
            str(args.frame_count),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        check=True,
    )
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(temporary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    if (
        int(stream["width"]) != args.width
        or int(stream["height"]) != args.height
        or int(stream["nb_read_frames"]) != args.frame_count
        or stream["r_frame_rate"] != f"{args.fps}/1"
    ):
        raise RuntimeError("encoded video does not match its requested specification")
    temporary.replace(video)
    return video, info


def make_milestone_strip(args: argparse.Namespace, frames: list[int], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    tile_width, tile_height, label_height, margin = 320, 180, 36, 14
    canvas = Image.new(
        "RGB",
        (margin + len(frames) * (tile_width + margin), tile_height + label_height + 2 * margin),
        (17, 24, 28),
    )
    draw = ImageDraw.Draw(canvas)
    font_path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    for index, frame in enumerate(frames):
        x = margin + index * (tile_width + margin)
        draw.text((x, margin), f"Frame {frame} | {100 * (frame - 1) / max(args.frame_count - 1, 1):.0f}%", font=font, fill=(230, 235, 233))
        with Image.open(frame_path(args.output_dir, frame)).convert("RGB") as source:
            canvas.paste(ImageOps.fit(source, (tile_width, tile_height)), (x, margin + label_height))
    canvas.save(output, "PNG", optimize=True)


def render_animation(evo: object, args: argparse.Namespace) -> Path:
    endpoint_records = prepare_scene(evo, args)
    endpoint_validation = validate_endpoint_records(
        endpoint_records, args.data_root / "scene_manifest.csv", require_morphology=True
    )
    endpoint_bounds = geometry_bounds(endpoint_records)
    camera = fit_camera(
        endpoint_bounds, (1.0, 0.36, 1.0), (0.0, 1.0, 0.0), 42.0, args.width / args.height, 1.05
    )
    camera = camera_record(camera, endpoint_records, "whole_field_animation", {"source": "August 11 endpoint union AABB"})
    apply_camera(evo, camera)
    if int(evo.SetSorghumLsFinalizeSnapshotMorphology(False)) != len(GENOTYPES):
        raise RuntimeError("failed to disable endpoint finalization for the illustrative animation")
    if int(evo.GrowSorghumLsPlantsToGdd(0.0, FIELD_SEED, True)) != 60:
        raise RuntimeError("failed to reset the field to GDD 0")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("GDD 0 field did not become idle")
    target_gdd = shared_target_gdd(descriptor_paths(args.project_root))
    states = []
    for frame in range(1, args.frame_count + 1):
        progress = (frame - 1) / max(args.frame_count - 1, 1)
        gdd = target_gdd * progress
        if frame > 1:
            if frame == args.frame_count and int(evo.SetSorghumLsFinalizeSnapshotMorphology(True)) != len(GENOTYPES):
                raise RuntimeError("failed to restore August 11 endpoint finalization")
            if int(evo.AdvanceSorghumLsPlantsToGdd(gdd, FIELD_SEED, True)) != 60:
                raise RuntimeError(f"frame {frame}: failed to advance all 60 plants")
            if not evo.WaitForProjectIdle(args.max_wait_frames):
                raise RuntimeError(f"frame {frame}: geometry did not become idle")
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        if len(records) != 60:
            raise RuntimeError(f"frame {frame}: expected 60 plants")
        evo.LoopFrames(args.warmup_frames)
        output = frame_path(args.output_dir, frame)
        raw = output.with_name(f".{output.stem}.raw.png")
        graded = output.with_name(f".{output.stem}.graded.png")
        output.parent.mkdir(parents=True, exist_ok=True)
        if not evo.CaptureCurrentSceneRayTraced(
            args.width,
            args.height,
            raw,
            args.animation_samples,
            args.animation_bounces,
            DEFAULT_PROFILE.gamma,
            args.denoiser_strength,
        ):
            raise RuntimeError(f"frame {frame}: capture failed")
        apply_photo_grade(raw, graded)
        graded.replace(output)
        raw.unlink(missing_ok=True)
        metrics = image_metrics(output)
        if metrics["size"] != [args.width, args.height] or metrics["luminance_stddev"] < 3.0:
            raise RuntimeError(f"frame {frame}: rendered image failed validation")
        if frame in {1, args.frame_count}:
            states.append(
                {
                    "frame": frame,
                    "progress": progress,
                    "gdd": gdd,
                    "phenotype": summarize_animation_state(records),
                    "frame_sha256": sha256(output),
                }
            )
        if frame % 10 == 0 or frame == args.frame_count:
            print(f"captured animation frame {frame}/{args.frame_count}", flush=True)
    final_records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    final_validation = validate_endpoint_records(
        final_records, args.data_root / "scene_manifest.csv", require_morphology=True
    )
    video, probe = encode_video(args)
    milestones = sorted({1, args.frame_count, *[round(1 + index * (args.frame_count - 1) / 4) for index in range(1, 4)]})
    strip = args.output_dir / "animation" / "growth_milestones.png"
    make_milestone_strip(args, milestones, strip)
    report = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "interpretation": "Illustrative linear-GDD interpolation only; the measurement data constrain the final August 11 timestep, not the path used to reach it.",
        "timeline": {
            "frame_count": args.frame_count,
            "fps": args.fps,
            "duration_seconds": args.frame_count / args.fps,
            "start_gdd": 0.0,
            "endpoint_gdd": target_gdd,
            "interpolation": "linear GDD",
        },
        "camera": camera,
        "endpoint_geometry_bounds": bounds_to_json(endpoint_bounds),
        "preflight_endpoint_validation": endpoint_validation,
        "final_frame_endpoint_validation": final_validation,
        "sampled_states": states,
        "render": {
            "renderer": "EvoEngine_OptiX",
            "width": args.width,
            "height": args.height,
            "samples": args.animation_samples,
            "bounces": args.animation_bounces,
            "denoiser_strength": args.denoiser_strength,
        },
        "video": {
            "path": str(video.resolve()),
            "sha256": sha256(video),
            "probe": probe,
        },
        "milestone_frames": [str(frame_path(args.output_dir, frame).resolve()) for frame in milestones],
        "milestone_strip": str(strip.resolve()),
    }
    report_path = args.output_dir / "animation" / "animation_manifest.json"
    write_json(report_path, report)
    return report_path


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_sources_unchanged(paths: dict[str, Path], hashes: dict[str, str]) -> None:
    for name, path in paths.items():
        actual = normalized_text_sha256(path) if name == "project" else sha256(path)
        if actual != hashes[name]:
            raise RuntimeError(f"rendering changed a scientific source asset: {path}")


def run_worker(args: argparse.Namespace) -> None:
    failure_path = args.output_dir / f"{args.worker}_failure.json"
    completion_path = args.output_dir / f".{args.worker}_worker_complete.json"
    failure_path.unlink(missing_ok=True)
    completion_path.unlink(missing_ok=True)
    paths = source_paths(args)
    hashes = {
        name: normalized_text_sha256(path) if name == "project" else sha256(path)
        for name, path in paths.items()
    }
    asset_snapshot = runtime_asset_snapshot(args.project_root, args.project)
    initial_side_effects = set((args.project_root / "Assets").glob("New Scene*.evescene*"))
    configure_engine_imports(args.build_dir, args.config)
    os.chdir(args.build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    try:
        report = render_stills(evo, args) if args.worker == "stills" else render_animation(evo, args)
        verify_sources_unchanged(paths, hashes)
        write_json(
            completion_path,
            {"worker": args.worker, "report": str(report.resolve()), "source_sha256": hashes},
        )
        print(json.dumps({"success": True, "report": str(report.resolve())}, indent=2), flush=True)
    except Exception as error:
        write_json(
            failure_path,
            {"error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()},
        )
        raise
    finally:
        set_ground_extension(evo, False)
        restore_runtime_assets(asset_snapshot, args.project_root, initial_side_effects)


def worker_command(args: argparse.Namespace, worker: str) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        worker,
        "--project-root",
        str(args.project_root),
        "--project",
        str(args.project),
        "--build-dir",
        str(args.build_dir),
        "--config",
        args.config,
        "--runtime-package-dir",
        str(args.runtime_package_dir),
        "--output-dir",
        str(args.output_dir),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--still-samples",
        str(args.still_samples),
        "--still-bounces",
        str(args.still_bounces),
        "--animation-samples",
        str(args.animation_samples),
        "--animation-bounces",
        str(args.animation_bounces),
        "--denoiser-strength",
        str(args.denoiser_strength),
        "--frame-count",
        str(args.frame_count),
        "--fps",
        str(args.fps),
        "--warmup-frames",
        str(args.warmup_frames),
        "--max-wait-frames",
        str(args.max_wait_frames),
        "--views",
        ",".join(args.views),
    ]
    return command


def run_parent(args: argparse.Namespace) -> None:
    snapshot = runtime_asset_snapshot(args.project_root, args.project)
    initial_side_effects = set((args.project_root / "Assets").glob("New Scene*.evescene*"))
    try:
        for worker in ("stills", "animation"):
            if (worker == "stills" and args.animation_only) or (worker == "animation" and args.stills_only):
                continue
            completed = subprocess.run(worker_command(args, worker), check=False)
            report = (
                args.output_dir / "stills_render_manifest.json"
                if worker == "stills"
                else args.output_dir / "animation" / "animation_manifest.json"
            )
            completion = args.output_dir / f".{worker}_worker_complete.json"
            if not report.is_file() or not completion.is_file():
                raise RuntimeError(f"{worker} worker failed with status {completed.returncode}")
            if completed.returncode:
                print(
                    f"{worker} worker completed its verified report before native teardown status "
                    f"{completed.returncode}",
                    flush=True,
                )
    finally:
        restore_runtime_assets(snapshot, args.project_root, initial_side_effects)


def build_parser() -> argparse.ArgumentParser:
    root = repo_root_from_script()
    project_root = root / "Resources" / "DigitalAgricultureProject"
    build_dir = root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="Debug")
    parser.add_argument("--runtime-package-dir", type=Path, default=build_dir / "EvoEngine_App/Debug/Packages")
    parser.add_argument("--output-dir", type=Path, default=root / "out/realism_review" / EXPERIMENT_ID)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--still-samples", type=int, default=8)
    parser.add_argument("--still-bounces", type=int, default=3)
    parser.add_argument("--animation-samples", type=int, default=1)
    parser.add_argument("--animation-bounces", type=int, default=2)
    parser.add_argument("--denoiser-strength", type=float, default=0.0)
    parser.add_argument("--frame-count", type=int, default=120)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--warmup-frames", type=int, default=1)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--views", default=",".join(VIEW_NAMES))
    parser.add_argument("--stills-only", action="store_true")
    parser.add_argument("--animation-only", action="store_true")
    parser.add_argument("--worker", choices=("stills", "animation"), help=argparse.SUPPRESS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    args.data_root = args.project_root / "Data" / "Experiments" / EXPERIMENT_ID
    args.views = tuple(name for name in args.views.split(",") if name)
    if (
        args.width < 512
        or args.height < 512
        or args.width % 2
        or args.height % 2
        or args.frame_count < 2
        or args.fps <= 0
        or any(name not in VIEW_NAMES for name in args.views)
        or not 0.0 <= args.denoiser_strength <= 1.0
        or (args.stills_only and args.animation_only)
    ):
        raise ValueError("invalid render dimensions, timeline, views, denoiser, or mode")
    if args.worker:
        run_worker(args)
    else:
        run_parent(args)


if __name__ == "__main__":
    main()
