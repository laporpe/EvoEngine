#!/usr/bin/env python3
"""Calibrate endpoint descriptor allocation to August 11 aggregate measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from sorghum_2026_6x10_aug11_data import EXPERIMENT_ID
from sorghum_2026_6x10_data import repo_root_from_script


CALIBRATED_FIELDS = {
    "internode_length_scale": ("internode_sum_m", "sampled_internode_sum_m"),
    "leaf_length_scale": ("maximum_leaf_length_m", "sampled_maximum_leaf_length_m"),
    "leaf_width_scale": ("maximum_leaf_width_m", "sampled_maximum_leaf_width_m"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def stable_seed(genotype_id: str) -> int:
    payload = f"{EXPERIMENT_ID}|aggregate-calibration|{genotype_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "little") & 0x7FFFFFFF


def measured_aggregates(data_root: Path) -> dict[str, dict[str, float]]:
    internodes = read_csv(data_root / "internodes.csv")
    leaves = read_csv(data_root / "leaves.csv")
    result: dict[str, dict[str, float]] = {}
    genotypes = sorted({row["genotype_id"] for row in internodes})
    for genotype_id in genotypes:
        internode_groups: dict[str, list[float]] = defaultdict(list)
        leaf_length_groups: dict[str, list[float]] = defaultdict(list)
        leaf_width_groups: dict[str, list[float]] = defaultdict(list)
        for row in internodes:
            if row["genotype_id"] == genotype_id and row["internode_length_m"]:
                internode_groups[row["plant_id"]].append(float(row["internode_length_m"]))
        for row in leaves:
            if row["genotype_id"] != genotype_id:
                continue
            if row["length_m"]:
                leaf_length_groups[row["plant_id"]].append(float(row["length_m"]))
            if row["width_m"]:
                leaf_width_groups[row["plant_id"]].append(float(row["width_m"]))
        result[genotype_id] = {
            "internode_sum_m": statistics.fmean(sum(values) for values in internode_groups.values()),
            "maximum_leaf_length_m": statistics.fmean(max(values) for values in leaf_length_groups.values()),
            "maximum_leaf_width_m": statistics.fmean(max(values) for values in leaf_width_groups.values()),
        }
    return result


def sampled_aggregates(records: list[object]) -> dict[str, float]:
    return {
        "sampled_internode_sum_m": statistics.fmean(
            sum(float(item.target_length_m) for item in record.internodes if int(item.axis_id) == 0)
            for record in records
        ),
        "sampled_maximum_leaf_length_m": statistics.fmean(
            float(record.main_culm_max_target_blade_length_m) for record in records
        ),
        "sampled_maximum_leaf_width_m": statistics.fmean(
            float(record.main_culm_max_target_blade_width_m) for record in records
        ),
    }


def updated_scales(
    measured: dict[str, float], sampled: dict[str, float], current: dict[str, float]
) -> dict[str, float]:
    scales = {}
    for scale_name, (measured_name, sampled_name) in CALIBRATED_FIELDS.items():
        observed = sampled[sampled_name]
        if observed <= 0.0:
            raise ValueError(f"cannot calibrate {scale_name} from non-positive sampled value {observed}")
        scales[scale_name] = float(current.get(scale_name, 1.0)) * measured[measured_name] / observed
    return scales


def configure_engine_imports(build_dir: Path, config: str) -> None:
    paths = (
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    )
    sys.path.insert(0, str(paths[0]))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def calibrate(evo: object, args: argparse.Namespace) -> dict[str, object]:
    build_report = json.loads((args.data_root / "descriptor_build_report.json").read_text(encoding="utf-8"))
    override_path = args.data_root / "descriptor_calibration_overrides.json"
    previous = json.loads(override_path.read_text(encoding="utf-8")) if override_path.is_file() else {}
    current = previous.get("descriptors", {})
    measured = measured_aggregates(args.data_root)
    if not evo.RunLSystemSorghumProject(args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene):
        raise RuntimeError("failed to start EvoEngine aggregate-calibration scene")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("aggregate-calibration scene did not become idle")
    descriptors: dict[str, dict[str, float]] = {}
    reports = []
    for descriptor in build_report["descriptors"]:
        genotype_id = str(descriptor["genotype_id"])
        records = list(
            evo.SampleSorghumLsDescriptorAssetPhenotypes(
                Path(str(descriptor["descriptor_asset_path"])),
                args.sample_count,
                stable_seed(genotype_id),
                False,
                True,
                -1.0,
            )
        )
        if len(records) != args.sample_count:
            raise RuntimeError(f"{genotype_id}: expected {args.sample_count} samples, got {len(records)}")
        sampled = sampled_aggregates(records)
        scales = updated_scales(measured[genotype_id], sampled, current.get(genotype_id, {}))
        descriptors[genotype_id] = scales
        reports.append(
            {
                "genotype_id": genotype_id,
                "sample_count": args.sample_count,
                "measured": measured[genotype_id],
                "sampled_before_calibration": sampled,
                "scales": scales,
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "method": "engine-sampled aggregate allocation; no workbook measurement is embedded in code",
        "descriptors": descriptors,
        "report": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    build_dir = repo_root / "out" / "build" / "vs2026-x64"
    data_root = project_root / "Data" / "Experiments" / EXPERIMENT_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=data_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="Debug")
    parser.add_argument("--runtime-package-dir", type=Path, default=None)
    parser.add_argument("--base-scene", type=Path, default=Path("ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene"))
    parser.add_argument("--sample-count", type=int, default=2000)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.data_root = args.data_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = (
        args.runtime_package_dir.resolve()
        if args.runtime_package_dir
        else args.build_dir / "EvoEngine_App" / args.config / "Packages"
    )
    configure_engine_imports(args.build_dir, args.config)
    import PyDigitalAgriculture as evo

    project_bytes = args.project.read_bytes()
    try:
        report = calibrate(evo, args)
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)
    output = args.data_root / "descriptor_calibration_overrides.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "descriptors": report["descriptors"]}, indent=2))


if __name__ == "__main__":
    main()
