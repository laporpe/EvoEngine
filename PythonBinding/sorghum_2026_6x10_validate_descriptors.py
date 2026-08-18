#!/usr/bin/env python3
"""Sample and validate the six measured 2026 descriptor assets in EvoEngine."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, repo_root_from_script
from sorghum_lsystem_calibrate_date_cultivar_descriptors import summarize_records


def configure_engine_imports(build_dir: Path, config: str) -> None:
    paths = [
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    ]
    sys.path.insert(0, str(paths[0]))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def stable_seed(session_id: str, genotype_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{session_id}|{genotype_id}".encode()).digest()[:4], "little") & 0x7FFFFFFF


def relative_error(observed: float, target: float) -> float:
    return abs(observed - target) / max(abs(target), 1e-9)


def acceptance(target: dict[str, float], metrics: dict[str, float | int]) -> dict[str, object]:
    errors = {
        "leaf_count_mean": relative_error(float(metrics["leaf_mean"]), target["leaf_count"]),
        "tiller_count_mean": abs(float(metrics["tiller_count_mean"]) - target["tiller_count"]),
        "max_leaf_length_mean": relative_error(
            float(metrics["main_culm_max_target_blade_length_mean_m"]), target["max_leaf_length_m"]
        ),
        "max_leaf_width_mean": relative_error(
            float(metrics["main_culm_max_target_blade_width_mean_m"]), target["max_leaf_width_m"]
        ),
        "gravity_tip_deflection_fraction": abs(float(metrics["main_culm_gravity_tip_deflection_mean_m"]))
        / max(target["max_leaf_length_m"], 1e-9),
        "centerline_arc_to_chord_excess": max(
            0.0, float(metrics["main_culm_centerline_arc_to_chord_mean"]) - 1.0
        ),
    }
    thresholds = {
        "leaf_count_mean": 0.08,
        "tiller_count_mean": 0.50,
        "max_leaf_length_mean": 0.10,
        "max_leaf_width_mean": 0.15,
        "gravity_tip_deflection_fraction": 0.15,
        "centerline_arc_to_chord_excess": 0.15,
    }
    failed = [name for name, error in errors.items() if error > thresholds[name]]
    diagnostics = {
        "tallest_leaf_height_target_m": target["height_m"],
        "tallest_leaf_height_observed_m": float(metrics["height_mean_m"]),
        "tallest_leaf_height_relative_error": relative_error(float(metrics["height_mean_m"]), target["height_m"]),
        "main_culm_tip_height_mean_m": float(metrics.get("main_culm_tip_height_mean_m", 0.0)),
        "main_culm_mature_collar_height_mean_m": float(
            metrics.get("main_culm_mature_collar_height_mean_m", 0.0)
        ),
        "height_acceptance_policy": "diagnostic_only_without_measured_leaf_curvature",
    }
    return {
        "success": not failed,
        "failed_metrics": failed,
        "errors": errors,
        "thresholds": thresholds,
        "diagnostics": diagnostics,
    }


def target_values(
    descriptor: dict[str, object],
    target_rows: list[dict[str, str]],
    leaf_rank_rows: list[dict[str, str]],
) -> dict[str, float]:
    session_id = str(descriptor["session_id"])
    genotype_id = str(descriptor["genotype_id"])
    target = next(row for row in target_rows if row["session_id"] == session_id and row["genotype_id"] == genotype_id)
    leaves = [row for row in leaf_rank_rows if row["session_id"] == session_id and row["genotype_id"] == genotype_id]
    return {
        "height_m": float(target["height_m_mean"]),
        "leaf_count": float(target["leaf_count_mean"]),
        "tiller_count": float(target["tiller_count_mean"]),
        "max_leaf_length_m": max(float(row["length_m_mean"]) for row in leaves if row["length_m_mean"]),
        "max_leaf_width_m": max(float(row["width_m_mean"]) for row in leaves if row["width_m_mean"]),
    }


def validate(evo: object, args: argparse.Namespace) -> dict[str, object]:
    build_report = json.loads((args.data_root / "descriptor_build_report.json").read_text(encoding="utf-8"))
    target_rows = read_csv(args.data_root / "descriptor_targets.csv")
    leaf_rank_rows = read_csv(args.data_root / "leaf_rank_targets.csv")
    if not evo.RunLSystemSorghumProject(
        args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene
    ):
        raise RuntimeError("failed to start EvoEngine descriptor validation scene")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("descriptor validation scene did not become idle")
    reports = []
    for descriptor in build_report["descriptors"]:
        asset_path = Path(descriptor["descriptor_asset_path"])
        records = list(
            evo.SampleSorghumLsDescriptorAssetPhenotypes(
                asset_path,
                args.sample_count,
                stable_seed(str(descriptor["session_id"]), str(descriptor["genotype_id"])),
                True,
                True,
                args.gravity_compliance,
            )
        )
        metrics = summarize_records(records, args.sample_count)
        metrics["main_culm_tip_height_mean_m"] = statistics.fmean(
            float(record.main_culm_tip_height_m) for record in records
        )
        metrics["main_culm_mature_collar_height_mean_m"] = statistics.fmean(
            float(record.main_culm_highest_mature_collar_height_m) for record in records
        )
        targets = target_values(descriptor, target_rows, leaf_rank_rows)
        result = acceptance(targets, metrics)
        reports.append(
            {
                "session_id": descriptor["session_id"],
                "genotype_id": descriptor["genotype_id"],
                "descriptor_asset_path": descriptor["descriptor_asset_path"],
                "sample_count": args.sample_count,
                "targets": targets,
                "observed": metrics,
                "acceptance": result,
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": build_report.get("experiment_id", EXPERIMENT_ID),
        "sample_count_per_descriptor": args.sample_count,
        "descriptor_count": len(reports),
        "success": all(report["acceptance"]["success"] for report in reports),
        "descriptors": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    data_root = project_root / "Data" / "Experiments" / EXPERIMENT_ID
    default_build = repo_root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=default_build)
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--runtime-package-dir", type=Path, default=default_build / "EvoEngine_App" / "RelWithDebInfo" / "Packages")
    parser.add_argument("--base-scene", type=Path, default=Path("ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene"))
    parser.add_argument("--data-root", type=Path, default=data_root)
    parser.add_argument("--sample-count", type=int, default=1000)
    parser.add_argument("--gravity-compliance", type=float, default=-1.0)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--report", type=Path, default=data_root / "descriptor_engine_validation.json")
    parser.add_argument("--require-acceptance", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.build_dir = args.build_dir.resolve()
    args.project = args.project.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.data_root = args.data_root.resolve()
    configure_engine_imports(args.build_dir, args.config)
    import PyDigitalAgriculture as evo

    project_bytes = args.project.read_bytes()
    try:
        report = validate(evo, args)
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "descriptor_count": report["descriptor_count"]}, indent=2))
    if args.require_acceptance and not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
