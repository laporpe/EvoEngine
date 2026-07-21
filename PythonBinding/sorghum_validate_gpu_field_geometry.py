#!/usr/bin/env python3
"""Validate deterministic 4x10 geometry parity and regeneration timing."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from sorghum_4x10_parbar_sensor_illumination_handoff import configure_engine_imports
from sorghum_4x10_scene import prepare_4x10_scene, query_4x10_scene
from sorghum_asset_layout import DATE_ORDER, GENERATED_DESCRIPTOR_ROOT, GENERATED_REPORT_ROOT

RAY_TRACER_COUNTER_NAMES = ("gas_builds", "gas_updates", "ias_builds", "ias_updates")


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def _vector(value: object) -> list[float]:
    components = (
        (value.x, value.y, value.z)
        if hasattr(value, "x")
        else (value[0], value[1], value[2])
    )
    return [round(float(component), 7) for component in components]


def scene_snapshot(records: list[object]) -> list[dict[str, object]]:
    snapshot = []
    for record in sorted(records, key=lambda item: str(item.name)):
        snapshot.append(
            {
                "name": str(record.name),
                "cultivar": str(record.cultivar),
                "local_position": _vector(record.local_position),
                "global_position": _vector(record.global_position),
                "geometry_min_position": _vector(record.geometry_min_position),
                "geometry_max_position": _vector(record.geometry_max_position),
                "leaf_count": int(record.leaf_count),
                "main_culm_leaf_count": int(record.main_culm_leaf_count),
                "tiller_leaf_count": int(record.tiller_leaf_count),
                "primary_tiller_count": int(record.primary_tiller_count),
                "geometry_snapshot_schema_version": int(record.geometry_snapshot_schema_version),
                "geometry_snapshot_organ_count": int(record.geometry_snapshot_organ_count),
                "leaf_vertex_count": int(record.leaf_vertex_count),
                "leaf_triangle_count": int(record.leaf_triangle_count),
                "culm_vertex_count": int(record.culm_vertex_count),
                "culm_triangle_count": int(record.culm_triangle_count),
                "leaf_width_scale": round(float(record.leaf_width_scale), 7),
                "leaf_thickness_m": round(float(record.leaf_thickness_m), 7),
                "plant_height_m": round(float(record.plant_height_m), 7),
                "leaf_area_m2": round(float(record.leaf_area_m2), 7),
                "has_geometry": bool(record.has_geometry),
                "axes": [
                    {
                        "axis_id": int(axis.axis_id),
                        "origin_rank": int(axis.origin_rank),
                        "leaf_count": int(axis.leaf_count),
                        "internode_count": int(axis.internode_count),
                        "origin_height_m": round(float(axis.origin_height_m), 7),
                        "culm_tip_height_m": round(float(axis.culm_tip_height_m), 7),
                    }
                    for axis in sorted(record.axes, key=lambda item: int(item.axis_id))
                ],
            }
        )
    return snapshot


def snapshot_digest(snapshot: list[dict[str, object]]) -> str:
    payload = json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def parbar_snapshot(records: list[object]) -> list[dict[str, object]]:
    return [
        {
            "cultivar": str(record.cultivar),
            "sensor_bar_level": str(record.sensor_bar_level),
            "row": int(record.row),
            "column": int(record.column),
            "position": _vector(record.position),
            "energy": _vector(record.energy),
            "scalar": round(float(record.scalar), 7),
        }
        for record in sorted(
            records,
            key=lambda item: (
                str(item.cultivar),
                str(item.sensor_bar_level),
                int(item.row),
                int(item.column),
            ),
        )
    ]


def counter_delta(before: list[int], after: list[int]) -> dict[str, int]:
    return {
        name: int(end) - int(start)
        for name, start, end in zip(RAY_TRACER_COUNTER_NAMES, before, after)
    }


def timing_summary(records: list[object], wall_seconds: float) -> dict[str, float]:
    fields = (
        "last_grow_seconds",
        "last_rebuild_seconds",
        "last_rebuild_internode_seconds",
        "last_leaf_spline_seconds",
        "last_leaf_mesh_seconds",
        "last_mesh_upload_seconds",
    )
    return {
        "wall_seconds": wall_seconds,
        **{field: sum(float(getattr(record, field)) for record in records) for field in fields},
    }


def grow_and_measure(
    evo: object,
    seed: int,
    reuse_geometry_entities: bool,
    update_render_geometry: bool,
    max_wait_frames: int,
) -> tuple[list[object], float, dict[str, int]]:
    counters_before = list(evo.GetRayTracerBuildCounters())
    started = time.perf_counter()
    count = int(
        evo.GrowSorghumLsPlantsToAdulthood(
            seed, "", reuse_geometry_entities, update_render_geometry
        )
    )
    evo.LoopFrames(1)
    if count != 40 or not evo.WaitForProjectIdle(max_wait_frames):
        raise RuntimeError(f"geometry generation failed: seed={seed}, plants={count}")
    wall_seconds = time.perf_counter() - started
    counters_after = list(evo.GetRayTracerBuildCounters())
    return (
        list(evo.GetSorghumLsPlantSceneMetadata(True)),
        wall_seconds,
        counter_delta(counters_before, counters_after),
    )


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--build-dir", type=Path, default=repo_root / "out" / "build" / "vs2026-x64")
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument(
        "--runtime-package-dir",
        type=Path,
        default=repo_root
        / "out"
        / "build"
        / "vs2026-x64"
        / "EvoEngine_App"
        / "RelWithDebInfo"
        / "Packages",
    )
    parser.add_argument("--date", choices=DATE_ORDER, default=DATE_ORDER[-1])
    parser.add_argument("--seed", type=int, default=2_000_000)
    parser.add_argument("--different-seed", type=int, default=2_001_000)
    parser.add_argument("--probes-per-panel", type=int, default=8)
    parser.add_argument("--illumination-samples", type=int, default=64)
    parser.add_argument("--illumination-bounces", type=int, default=4)
    parser.add_argument("--illumination-seed", type=int, default=4_242)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "out" / "validation" / "gpu_field_geometry" / "mature_4x10_lifecycle.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.repo_root = args.repo_root.resolve()
    args.build_dir = args.build_dir.resolve()
    args.project = args.project.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.output = args.output.resolve()
    project_assets = args.project.parent / "Assets"
    scene = query_4x10_scene(
        project_assets / GENERATED_REPORT_ROOT / "field_manifest.csv",
        GENERATED_DESCRIPTOR_ROOT,
        args.date,
    )

    configure_engine_imports(args.repo_root, args.build_dir, args.config)
    import PyDigitalAgriculture as evo

    try:
        prepare_4x10_scene(
            evo,
            args.project,
            args.runtime_package_dir,
            scene,
            args.seed,
            2.0 / 3.0,
            2,
            args.max_wait_frames,
        )
        sensors = evo.CreateParbarTopFaceSensorGroup(args.probes_per_panel)
        runs = {}
        for name, seed, reuse, update_render_geometry in (
            ("destructive_reference", args.seed, False, True),
            ("persistent", args.seed, True, False),
            ("persistent_replay", args.seed, True, False),
            ("different_seed", args.different_seed, True, False),
        ):
            records, wall_seconds, ray_tracer = grow_and_measure(
                evo, seed, reuse, update_render_geometry, args.max_wait_frames
            )
            snapshot = scene_snapshot(records)
            runs[name] = {
                "seed": seed,
                "reuse_geometry_entities": reuse,
                "update_render_geometry": update_render_geometry,
                "digest": snapshot_digest(snapshot),
                "timing": timing_summary(records, wall_seconds),
                "ray_tracer": ray_tracer,
                "snapshot": snapshot,
            }
            if name != "different_seed":
                evo.EstimatePARSensors(
                    sensors,
                    args.illumination_samples,
                    args.illumination_bounces,
                    0.001,
                    args.illumination_seed,
                )
                illumination = parbar_snapshot(
                    list(evo.GetParbarTopFaceSensorResults(sensors, args.probes_per_panel))
                )
                runs[name]["illumination_digest"] = snapshot_digest(illumination)
                runs[name]["illumination_snapshot"] = illumination
    finally:
        evo.Terminate()

    reference_digest = runs["destructive_reference"]["digest"]
    if runs["persistent"]["digest"] != reference_digest:
        raise RuntimeError("persistent geometry differs from the destructive CPU reference")
    if runs["persistent_replay"]["digest"] != reference_digest:
        raise RuntimeError("same-seed persistent replay is not deterministic")
    if runs["different_seed"]["digest"] == reference_digest:
        raise RuntimeError("different morphology seed did not change the scene digest")
    reference_illumination_digest = runs["destructive_reference"]["illumination_digest"]
    if runs["persistent"]["illumination_digest"] != reference_illumination_digest:
        raise RuntimeError("persistent OptiX geometry changed fixed-seed PARBAR illumination")
    if runs["persistent_replay"]["illumination_digest"] != reference_illumination_digest:
        raise RuntimeError("persistent replay changed fixed-seed PARBAR illumination")
    persistent_ray_tracer = runs["persistent_replay"]["ray_tracer"]
    if persistent_ray_tracer["gas_updates"] <= 0 or persistent_ray_tracer["ias_updates"] <= 0:
        raise RuntimeError("persistent replay did not use OptiX GAS and IAS updates")

    payload = {
        "schema_version": 2,
        "coordinate_system": "EvoEngine Y-up",
        "date": args.date,
        "scene_asset_path": scene.scene_asset_path,
        "plant_count": scene.plant_count,
        "parity": "pass",
        "illumination_parity": "pass",
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    reference_wall = float(runs["destructive_reference"]["timing"]["wall_seconds"])
    persistent_wall = float(runs["persistent_replay"]["timing"]["wall_seconds"])
    print(f"parity=pass digest={reference_digest}")
    print(f"destructive_wall_s={reference_wall:.3f}")
    print(f"persistent_wall_s={persistent_wall:.3f}")
    print(f"speedup={reference_wall / persistent_wall:.3f}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
