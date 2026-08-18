#!/usr/bin/env python3
"""Validate 2026 6x10 inputs and prove the 2021 4x10 assets are unchanged."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, ROW_GENOTYPES, repo_root_from_script, sha256


LEGACY_PATHS = (
    "Assets/ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene",
    "Assets/GeneratedAssets/Reports/field_manifest.csv",
    "Assets/GeneratedAssets/Reports/calibration_summary.csv",
    "Assets/GeneratedAssets/Reports/calibration_summary.json",
    "Assets/GeneratedAssets/Reports/post_tiller_scene_validation.csv",
    *(
        f"Assets/GeneratedAssets/Scenes/Sorghum_4x10_GrowthStage{stage:02d}.evescene"
        for stage in range(1, 6)
    ),
    *(
        f"Assets/GeneratedAssets/Descriptors/GrowthStage{stage:02d}/{genotype}.sorghumls"
        for stage in range(1, 6)
        for genotype in ("BTX", "Pawaga")
    ),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def legacy_fingerprint(project_root: Path) -> dict[str, object]:
    files = []
    for relative in LEGACY_PATHS:
        path = project_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing 2021 baseline asset: {path}")
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256(path)})
    return {"schema_version": 1, "scope": "immutable_2021_4x10_assets", "files": files}


def write_baseline(project_root: Path, baseline_path: Path) -> dict[str, object]:
    if baseline_path.exists():
        raise FileExistsError(f"refusing to replace legacy baseline: {baseline_path}")
    baseline = legacy_fingerprint(project_root)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    return baseline


def validate_legacy(project_root: Path, baseline_path: Path) -> dict[str, object]:
    expected = json.loads(baseline_path.read_text(encoding="utf-8"))
    actual = legacy_fingerprint(project_root)
    expected_files = {row["path"]: row for row in expected["files"]}
    actual_files = {row["path"]: row for row in actual["files"]}
    changed = [path for path in expected_files if expected_files[path] != actual_files.get(path)]
    added = sorted(set(actual_files) - set(expected_files))
    missing = sorted(set(expected_files) - set(actual_files))
    if changed or added or missing:
        raise AssertionError(f"2021 4x10 baseline changed: changed={changed}, added={added}, missing={missing}")
    return {"file_count": len(actual_files), "changed": [], "status": "exact_match"}


def validate_normalized(data_root: Path) -> dict[str, object]:
    contract = json.loads((data_root / "validation_contract.json").read_text(encoding="utf-8"))
    summary = json.loads((data_root / "normalization_summary.json").read_text(encoding="utf-8"))
    plants = read_csv(data_root / "plants.csv")
    leaves = read_csv(data_root / "leaves.csv")
    targets = read_csv(data_root / "descriptor_targets.csv")
    qc = read_csv(data_root / "qc.csv")
    if contract["experiment_id"] != EXPERIMENT_ID or summary["plant_rows"] != 30:
        raise AssertionError("normalization contract or plant count mismatch")
    if len(plants) != 30 or len({row["plant_id"] for row in plants}) != 30:
        raise AssertionError("normalized plants must contain 30 unique measured identities")
    measured_counts = Counter((row["session_id"], row["genotype_id"]) for row in plants)
    if set(measured_counts.values()) != {5} or len(measured_counts) != 6:
        raise AssertionError(f"expected five measured plants per genotype/session: {measured_counts}")
    if len(targets) != 6 or {int(row["sample_count"]) for row in targets} != {5}:
        raise AssertionError("descriptor target count/sample size mismatch")
    excluded = [row for row in leaves if row["length_qc"] == "suspected_decimal_transcription_outlier_excluded"]
    if len(excluded) != 1 or excluded[0]["length_source"].split("|")[-1] != "Y9":
        raise AssertionError("the unresolved July 21 decimal outlier must be uniquely excluded")
    assumptions = [row for row in qc if row["action"] == "interpreted_as_cm_for_provisional_calibration"]
    if len(assumptions) < 150:
        raise AssertionError("July 21 leaf-width unit assumptions are not fully recorded")
    if tuple(contract["layout_contract"]["row_genotypes"]) != ROW_GENOTYPES:
        raise AssertionError("6x10 genotype row order changed")
    shape = contract["leaf_shape_contract"]
    if shape["midrib_curvature"] != "unmeasured_neutral_zero_intrinsic_bending" or float(
        shape["gravity_droop_compliance"]
    ) != 0.02:
        raise AssertionError("unmeasured leaf curvature or restrained gravity prior changed")
    return {
        "measured_plant_count": len(plants),
        "descriptor_target_count": len(targets),
        "qc_record_count": len(qc),
        "excluded_decimal_outliers": len(excluded),
        "provisional_width_unit_records": len(assumptions),
        "status": "valid",
    }


def validate_scene_assets(project_root: Path) -> dict[str, object]:
    scene_root = project_root / "Assets" / "GeneratedAssets" / "Experiments" / EXPERIMENT_ID / "Scenes"
    scenes = sorted(scene_root.glob("*.evescene")) if scene_root.is_dir() else []
    if not scenes:
        return {"status": "not_generated", "scene_count": 0}
    if len(scenes) != 2:
        raise AssertionError(f"expected two generated 6x10 scenes, found {len(scenes)}")
    counts = {}
    for scene in scenes:
        text = scene.read_text(encoding="utf-8")
        counts[scene.name] = {
            "plant_count": text.count("tn: SorghumLS"),
            "genotype_a": text.count("n: GenotypeA_LSystem_"),
            "genotype_b": text.count("n: GenotypeB_LSystem_"),
            "genotype_c": text.count("n: GenotypeC_LSystem_"),
            "parbar_rigs": len(re.findall(r"^\s*- n: PARBAR_Genotype[ABC]\s*$", text, re.MULTILINE)),
            "parbar_sensor_bars": len(
                re.findall(
                    r"^\s*- n: PARBAR_Genotype[ABC]_(?:Top|Middle|Bottom)SensorBarMesh\s*$",
                    text,
                    re.MULTILINE,
                )
            ),
        }
        expected = {
            "plant_count": 60,
            "genotype_a": 20,
            "genotype_b": 20,
            "genotype_c": 20,
            "parbar_rigs": 3,
            "parbar_sensor_bars": 9,
        }
        if counts[scene.name] != expected or "PARBAR_BTX" in text or "PARBAR_Pawaga" in text:
            raise AssertionError(f"invalid 6x10 scene composition: {scene.name}: {counts[scene.name]}")
    return {"status": "valid", "scene_count": 2, "scenes": counts}


def validate_scene_manifest(data_root: Path, tolerance_m: float = 1e-3) -> dict[str, object]:
    rows = read_csv(data_root / "scene_manifest.csv")
    if len(rows) != 120 or {row["parbar_context_present"] for row in rows} != {"True"} or {
        row["illumination_estimation_performed"] for row in rows
    } != {"False"}:
        raise AssertionError("scene manifest must record 120 plants, replicated PARBAR context, and no illumination run")
    session_deltas = {}
    for session in sorted({row["session_id"] for row in rows}):
        session_rows = [row for row in rows if row["session_id"] == session]
        row_z = []
        for row_index in range(6):
            positions = sorted(
                (float(row["x_m"]), float(row["z_m"]))
                for row in session_rows
                if int(row["row"]) == row_index
            )
            if len(positions) != 10 or max(z for _, z in positions) - min(z for _, z in positions) > tolerance_m:
                raise AssertionError(f"{session}: row {row_index} is incomplete or not straight")
            if any(abs(positions[index + 1][0] - positions[index][0] - 0.76) > tolerance_m for index in range(9)):
                raise AssertionError(f"{session}: row {row_index} does not preserve 0.76 m column spacing")
            row_z.append(sum(z for _, z in positions) / 10)
        deltas = [abs(row_z[index + 1] - row_z[index]) for index in range(5)]
        expected = (1.10, 2.20, 1.10, 2.20, 1.10)
        if any(abs(actual - target) > tolerance_m for actual, target in zip(deltas, expected)):
            raise AssertionError(f"{session}: row deltas changed: {deltas}")
        session_deltas[session] = deltas
    return {"status": "valid", "plant_rows": len(rows), "row_deltas_m": session_deltas}


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    data_root = project_root / "Data" / "Experiments" / EXPERIMENT_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--data-root", type=Path, default=data_root)
    parser.add_argument("--baseline", type=Path, default=data_root / "legacy_4x10_baseline.json")
    parser.add_argument("--report", type=Path, default=data_root / "validation_report.json")
    parser.add_argument("--write-baseline", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project_root = args.project_root.resolve()
    baseline_path = args.baseline.resolve()
    if args.write_baseline:
        write_baseline(project_root, baseline_path)
    report = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "legacy_4x10": validate_legacy(project_root, baseline_path),
        "normalized_measurements": validate_normalized(args.data_root.resolve()),
        "generated_scenes": validate_scene_assets(project_root),
        "scene_profile": validate_scene_manifest(args.data_root.resolve()),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
