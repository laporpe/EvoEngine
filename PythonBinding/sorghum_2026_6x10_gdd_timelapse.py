#!/usr/bin/env python3
"""Render the 2026 6x10 SorghumLS field through 1,000 target-GDD states."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, ROW_GENOTYPES, repo_root_from_script
from sorghum_2026_6x10_scene import (
    GENOTYPES,
    SEEDS,
    TEMPLATE_SCENE,
    configure_engine_imports,
)
from sorghum_4x10_presentation import DEFAULT_PROFILE, apply_photo_grade, configure_lighting, set_ground_extension
from sorghum_render_2026_6x10 import camera_for_view, geometry_bounds, image_metrics, sha256


STATE_COUNT = 1000
FPS = 24
FRAME_PATTERN = "field_%04d.png"
DESCRIPTOR_SESSION = "MeasurementStage02"
FIELD_LEAF_VERTICAL_SUBDIVISION_M = 0.04
FIELD_LEAF_HORIZONTAL_SUBDIVISIONS = 3
TARGET_GDD_PATTERN = re.compile(
    r"(?m)^target_gdd:\s*\r?\n\s*mean:\s*([-+0-9.eE]+)\s*\r?\n\s*deviation:\s*([-+0-9.eE]+)"
)


def state_gdd(state: int, target_gdd: float, state_count: int = STATE_COUNT) -> float:
    if not 1 <= state <= state_count or target_gdd <= 0.0:
        raise ValueError("state and target GDD are invalid")
    return target_gdd * state / state_count


def requested_states(value: str | None, state_count: int) -> tuple[int, ...]:
    if not value:
        return tuple(range(1, state_count + 1))
    states = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    if not states or states[0] < 1 or states[-1] > state_count:
        raise ValueError("requested states must be within the configured timeline")
    return states


def descriptor_paths(project_root: Path) -> dict[str, Path]:
    root = project_root / "Assets/GeneratedAssets/Experiments" / EXPERIMENT_ID / "Descriptors" / DESCRIPTOR_SESSION
    paths = {genotype: root / f"{genotype}.sorghumls" for genotype in GENOTYPES}
    if any(not path.is_file() for path in paths.values()):
        raise FileNotFoundError(f"missing {DESCRIPTOR_SESSION} 2026 descriptor asset")
    return paths


def shared_target_gdd(paths: dict[str, Path]) -> float:
    values = []
    for path in paths.values():
        match = TARGET_GDD_PATTERN.search(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"{path} has no readable target_gdd distribution")
        mean, deviation = (float(value) for value in match.groups())
        if deviation != 0.0:
            raise ValueError("the time-lapse requires a fixed target GDD for every 2026 plant")
        values.append(mean)
    if any(abs(value - values[0]) > 1.0e-6 for value in values[1:]):
        raise ValueError(f"the three genotype descriptors have different target GDD values: {values}")
    return values[0]


def frame_path(output_dir: Path, state: int) -> Path:
    return output_dir / "frames" / (FRAME_PATTERN % state)


def state_path(output_dir: Path, state: int) -> Path:
    return output_dir / "states" / f"field_{state:04d}.json"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def valid_cached_state(path: Path, frame: Path, expected: dict[str, object]) -> bool:
    if not path.is_file() or not frame.is_file():
        return False
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
        return all(actual.get(key) == value for key, value in expected.items()) and actual.get("frame_sha256") == sha256(frame)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def validate_field(records: list[object], expected_gdd: float) -> None:
    if len(records) != 60 or any(not record.has_geometry for record in records):
        raise RuntimeError("expected a rendered 60-plant field")
    expected_rows = {genotype: 20 for genotype in GENOTYPES}
    observed = {genotype: sum(record.cultivar == genotype for record in records) for genotype in GENOTYPES}
    if observed != expected_rows or any(abs(float(record.evaluation_gdd) - expected_gdd) > 1.0e-3 for record in records):
        raise RuntimeError("field plants do not match the requested genotype/GDD state")


def summarize_phenology(records: list[object]) -> dict[str, dict[str, float | int]]:
    """Return a compact, renderer-independent reproductive audit by genotype."""
    summary: dict[str, dict[str, float | int]] = {}
    for genotype in GENOTYPES:
        group = [record for record in records if record.cultivar == genotype]
        if len(group) != 20:
            raise RuntimeError(f"{genotype}: expected 20 plants in phenology audit")
        summary[genotype] = {
            "plants": len(group),
            "panicle_emerged_plants": sum(bool(record.panicle_emerged) for record in group),
            "panicle_vertex_count": sum(int(record.panicle_vertex_count) for record in group),
            "panicle_triangle_count": sum(int(record.panicle_triangle_count) for record in group),
            "panicle_branch_count": sum(int(record.panicle_branch_count) for record in group),
            "panicle_spikelet_count": sum(int(record.panicle_spikelet_count) for record in group),
            "mean_height_m": sum(float(record.plant_height_m) for record in group) / len(group),
            "mean_panicle_tip_height_m": sum(float(record.panicle_tip_height_m) for record in group) / len(group),
        }
    return summary


def initialize_field(evo: object, args: argparse.Namespace, descriptors: dict[str, Path]) -> None:
    if not evo.RunLSystemSorghumProject(args.project, args.runtime_package_dir, TEMPLATE_SCENE):
        raise RuntimeError(f"failed to load {TEMPLATE_SCENE}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("2026 marker scene did not become idle")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != 60:
        raise RuntimeError("failed to instantiate the 60 SorghumLS planting markers")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != 60:
        raise RuntimeError("failed to conform the 60 SorghumLS plants to the field soil")
    asset_descriptors = {
        genotype: path.relative_to(args.project_root / "Assets") for genotype, path in descriptors.items()
    }
    if int(evo.SetSorghumLsGenotypeDescriptors(asset_descriptors, False, -1)) != 60:
        raise RuntimeError("failed to assign the three 2026 genotype descriptors")
    if int(
        evo.ConfigureSorghumLsLeafMeshQuality(
            FIELD_LEAF_VERTICAL_SUBDIVISION_M, FIELD_LEAF_HORIZONTAL_SUBDIVISIONS, False, True, False
        )
    ) != 60:
        raise RuntimeError("failed to apply the render-only SorghumLS field leaf LOD")
    if int(evo.SetSorghumLsFinalizeSnapshotMorphology(False)) != len(GENOTYPES):
        raise RuntimeError("failed to disable static-snapshot finalization for the dynamic GDD timeline")
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("the established 2026 soil/illumination context is invalid")
    configure_lighting(evo)
    if set_ground_extension(evo, True) != 1:
        raise RuntimeError("failed to create the render-only field ground extension")


def configure_camera(evo: object, args: argparse.Namespace, target_gdd: float) -> dict[str, object]:
    if int(evo.GrowSorghumLsPlantsToGdd(target_gdd, SEEDS[DESCRIPTOR_SESSION], True)) != 60:
        raise RuntimeError("failed to generate the frame-1000 SorghumLS field")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("frame-1000 field did not become idle")
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    validate_field(records, target_gdd)
    print(json.dumps({"gdd": target_gdd, "phenology": summarize_phenology(records)}, sort_keys=True), flush=True)
    camera = camera_for_view(geometry_bounds(records), "perspective", args.width / args.height)
    position, target, up = (evo.Vec3(), evo.Vec3(), evo.Vec3())
    for vector, values in zip((position, target, up), (camera["position"], camera["target"], camera["up"])):
        vector.x, vector.y, vector.z = values
    if not evo.SetMainCameraLookAt(position, target, up, float(camera["fov_degrees"])):
        raise RuntimeError("failed to apply the fixed 6x10 field camera")
    return camera


def capture_state(
    evo: object,
    args: argparse.Namespace,
    output_dir: Path,
    state: int,
    target_gdd: float,
) -> dict[str, object]:
    gdd = state_gdd(state, target_gdd, args.state_count)
    frame = frame_path(output_dir, state)
    metadata = state_path(output_dir, state)
    expected = {"state": state, "state_count": args.state_count, "gdd": gdd, "target_gdd": target_gdd}
    if valid_cached_state(metadata, frame, expected):
        return json.loads(metadata.read_text(encoding="utf-8"))

    if int(evo.AdvanceSorghumLsPlantsToGdd(gdd, SEEDS[DESCRIPTOR_SESSION], True)) != 60:
        raise RuntimeError(f"state {state}: failed to advance all 60 SorghumLS plants")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError(f"state {state}: geometry did not become idle")
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    evo.LoopFrames(args.warmup_frames)
    raw = frame.with_name(f".{frame.stem}.raw.png")
    graded = frame.with_name(f".{frame.stem}.graded.png")
    frame.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not evo.CaptureCurrentSceneRayTraced(args.width, args.height, raw, args.samples, args.bounces, DEFAULT_PROFILE.gamma):
            raise RuntimeError(f"state {state}: OptiX capture failed")
        apply_photo_grade(raw, graded)
        metrics = image_metrics(graded)
        if metrics["luminance_stddev"] < 3.0:
            raise RuntimeError(f"state {state}: render appears blank or flat")
        graded.replace(frame)
    finally:
        raw.unlink(missing_ok=True)
        graded.unlink(missing_ok=True)
    payload = {
        **expected,
        "frame": str(frame.resolve()),
        "frame_sha256": sha256(frame),
        "metrics": image_metrics(frame),
        "phenology": summarize_phenology(records),
    }
    write_json(metadata, payload)
    return payload


def verify_state_outputs(output_dir: Path, states: tuple[int, ...], args: argparse.Namespace, target_gdd: float) -> list[dict[str, object]]:
    rows = []
    for state in states:
        gdd = state_gdd(state, target_gdd, args.state_count)
        frame = frame_path(output_dir, state)
        metadata = state_path(output_dir, state)
        expected = {"state": state, "state_count": args.state_count, "gdd": gdd, "target_gdd": target_gdd}
        if not valid_cached_state(metadata, frame, expected):
            raise RuntimeError(f"invalid state output: {state}")
        metrics = image_metrics(frame)
        if metrics["size"] != [args.width, args.height] or metrics["luminance_stddev"] < 3.0:
            raise RuntimeError(f"state {state}: rendered frame failed image verification")
        rows.append(json.loads(metadata.read_text(encoding="utf-8")))
    return rows


def require_video_tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required to assemble the time-lapse")
    return ffmpeg, ffprobe


def encode_video(output_dir: Path, args: argparse.Namespace) -> tuple[Path, dict[str, object]]:
    ffmpeg, ffprobe = require_video_tools()
    video = output_dir / "sorghum_2026_6x10_1000_gdd_panicle_lsystem_midday.mp4"
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
            str(output_dir / "frames" / FRAME_PATTERN),
            "-frames:v",
            str(args.state_count),
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
        or int(stream["nb_read_frames"]) != args.state_count
        or stream["r_frame_rate"] != f"{args.fps}/1"
    ):
        raise RuntimeError("encoded time-lapse does not match the requested video specification")
    temporary.replace(video)
    return video, info


def run(args: argparse.Namespace) -> Path:
    if args.state_count != STATE_COUNT:
        raise ValueError("the published 2026 timeline is fixed at 1,000 field states")
    if args.width <= 0 or args.height <= 0 or args.width % 2 or args.height % 2 or args.fps <= 0:
        raise ValueError("video dimensions must be positive and even; FPS must be positive")
    states = requested_states(args.states, args.state_count)
    if not args.no_video and states != tuple(range(1, args.state_count + 1)):
        raise ValueError("video assembly requires every state from 1 through 1,000")
    descriptors = descriptor_paths(args.project_root)
    target_gdd = shared_target_gdd(descriptors)
    source_hashes = {
        "project": sha256(args.project),
        "template_scene": sha256(args.project_root / "Assets" / TEMPLATE_SCENE),
        **{f"descriptor_{genotype}": sha256(path) for genotype, path in descriptors.items()},
    }
    build_dir = args.build_dir.resolve()
    configure_engine_imports(build_dir, args.config)
    os.chdir(build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    # The PyDigitalAgriculture runtime unloads its own package during
    # ``Terminate``.  Persist the self-contained deliverable before that
    # teardown; otherwise a successful render can leave frames on disk without
    # its manifest or assembled mobile video.
    try:
        initialize_field(evo, args, descriptors)
        camera = configure_camera(evo, args, target_gdd)
        for offset, state in enumerate(states, start=1):
            capture_state(evo, args, args.output_dir, state, target_gdd)
            if offset % 25 == 0 or offset == len(states):
                print(f"captured {offset}/{len(states)} SorghumLS field states", flush=True)
        rows = verify_state_outputs(args.output_dir, states, args, target_gdd)

        for name, digest in source_hashes.items():
            source = args.project if name == "project" else args.project_root / "Assets" / TEMPLATE_SCENE if name == "template_scene" else descriptors[name.removeprefix("descriptor_")]
            if sha256(source) != digest:
                raise RuntimeError(f"rendering changed a scientific source asset: {source}")
        video, probe = (encode_video(args.output_dir, args) if not args.no_video else (None, None))
        report = {
            "schema_version": 1,
            "renderer": "EvoEngine_OptiX",
            "basis": "Sorghum_6x10_2026 marker scene instantiated as 60 SorghumLS plants",
            "experiment_id": EXPERIMENT_ID,
            "layout": {"rows": 6, "columns": 10, "row_genotypes": list(ROW_GENOTYPES), "plants_per_genotype": 20},
            "descriptor_session": DESCRIPTOR_SESSION,
            "target_gdd": target_gdd,
            "timeline": {"state_count": args.state_count, "state_1_gdd": state_gdd(1, target_gdd), "state_1000_gdd": state_gdd(args.state_count, target_gdd)},
            "render": {"width": args.width, "height": args.height, "fps": args.fps, "samples": args.samples, "bounces": args.bounces, "fixed_midday_profile": DEFAULT_PROFILE.to_dict(), "camera": camera, "field_leaf_lod": {"vertical_subdivision_m": FIELD_LEAF_VERTICAL_SUBDIVISION_M, "horizontal_subdivisions": FIELD_LEAF_HORIZONTAL_SUBDIVISIONS, "bottom_face": False, "leaf_sheath": True}},
            "growth_execution": "camera framing replays the final state once; ordered field states advance from the prior GDD state",
            "captured_states": list(states),
            "states": rows,
            "source_sha256": source_hashes,
            "scientific_scene_assets_modified": False,
            "video": None if video is None else {"path": str(video.resolve()), "sha256": sha256(video), "probe": probe},
        }
        report_path = args.output_dir / "sorghum_2026_6x10_1000_gdd_panicle_lsystem_midday.json"
        write_json(report_path, report)
        return report_path
    finally:
        set_ground_extension(evo, False)
        evo.Terminate()


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
    parser.add_argument("--output-dir", type=Path, default=root / "out/panicle_timelapse/sorghum_2026_6x10_1000_gdd_lsystem_midday")
    parser.add_argument("--state-count", type=int, default=STATE_COUNT)
    parser.add_argument("--states", help="comma-separated state numbers for a no-video smoke render")
    # Match the established mobile-ready 4x10 delivery format.  The lower
    # resolution mode remains available explicitly for smoke tests.
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--bounces", type=int, default=2)
    parser.add_argument("--warmup-frames", type=int, default=1)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--no-video", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    print(run(args))


if __name__ == "__main__":
    main()
