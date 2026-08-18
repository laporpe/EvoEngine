#!/usr/bin/env python3
"""Validate the generated August 11 endpoint field against its measured targets."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from sorghum_2026_6x10_aug11_data import EXPERIMENT_ID, ROW_GENOTYPES, repo_root_from_script
from sorghum_2026_6x10_aug11_descriptors import PANICLE_BRANCH_ANGLE_DEGREES


THRESHOLDS = {
    "height_relative_error": 0.10,
    "leaf_count_absolute_error": 0.50,
    "tiller_count_absolute_error": 0.50,
    "panicle_emergence_absolute_error": 0.001,
    "panicle_length_relative_error": 0.10,
    "panicle_width_relative_error": 0.10,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def relative_error(observed: float, target: float) -> float:
    return abs(observed - target) / max(abs(target), 1e-9)


def mean(rows: list[dict[str, str]], field: str) -> float:
    return statistics.fmean(float(row[field]) for row in rows)


def validate(data_root: Path) -> dict[str, object]:
    targets = {row["genotype_id"]: row for row in read_csv(data_root / "descriptor_targets.csv")}
    rows = read_csv(data_root / "scene_manifest.csv")
    descriptor_build = json.loads((data_root / "descriptor_build_report.json").read_text(encoding="utf-8"))
    descriptor_engine = json.loads((data_root / "descriptor_engine_validation.json").read_text(encoding="utf-8"))

    layout_errors = []
    if len(rows) != 60:
        layout_errors.append(f"expected 60 plants, got {len(rows)}")
    counts = Counter(row["genotype_id"] for row in rows)
    if counts != Counter({genotype: 20 for genotype in targets}):
        layout_errors.append(f"expected 20 plants per genotype, got {dict(counts)}")
    coordinates = {(int(row["row"]), int(row["column"])) for row in rows}
    if coordinates != {(row, column) for row in range(6) for column in range(10)}:
        layout_errors.append("row/column coordinates do not cover one complete 6x10 field")
    for row in rows:
        if ROW_GENOTYPES[int(row["row"])] != row["genotype_id"]:
            layout_errors.append(f"row assignment mismatch for {row['plant_name']}")

    reports = []
    for genotype_id, target in sorted(targets.items()):
        group = [row for row in rows if row["genotype_id"] == genotype_id]
        emerged = [row for row in group if row["panicle_emerged"].lower() == "true"]
        observed = {
            "height_m_mean": mean(group, "plant_height_m"),
            "leaf_count_mean": mean(group, "main_culm_leaf_count"),
            "tiller_count_mean": mean(group, "primary_tiller_count"),
            "panicle_emerged_rate": len(emerged) / len(group),
            "panicle_length_m_mean": mean(emerged, "panicle_rachis_length_m") if emerged else None,
            "panicle_width_m_mean": (
                2.0
                * math.sin(math.radians(PANICLE_BRANCH_ANGLE_DEGREES))
                * mean(emerged, "panicle_branch_length_m")
                if emerged
                else None
            ),
        }
        errors = {
            "height_relative_error": relative_error(observed["height_m_mean"], float(target["height_m_mean"])),
            "leaf_count_absolute_error": abs(observed["leaf_count_mean"] - float(target["leaf_count_mean"])),
            "tiller_count_absolute_error": abs(observed["tiller_count_mean"] - float(target["tiller_count_mean"])),
            "panicle_emergence_absolute_error": abs(
                observed["panicle_emerged_rate"] - float(target["panicle_emerged_rate"])
            ),
        }
        if target["panicle_length_m_mean"]:
            errors["panicle_length_relative_error"] = relative_error(
                float(observed["panicle_length_m_mean"]), float(target["panicle_length_m_mean"])
            )
            errors["panicle_width_relative_error"] = relative_error(
                float(observed["panicle_width_m_mean"]), float(target["panicle_width_m_mean"])
            )
        failed = [name for name, value in errors.items() if value > THRESHOLDS[name]]
        reports.append(
            {
                "genotype_id": genotype_id,
                "plants": len(group),
                "measured": {
                    "height_m_mean": float(target["height_m_mean"]),
                    "leaf_count_mean": float(target["leaf_count_mean"]),
                    "tiller_count_mean": float(target["tiller_count_mean"]),
                    "panicle_emerged_rate": float(target["panicle_emerged_rate"]),
                    "panicle_length_m_mean": (
                        float(target["panicle_length_m_mean"]) if target["panicle_length_m_mean"] else None
                    ),
                    "panicle_width_m_mean": (
                        float(target["panicle_width_m_mean"]) if target["panicle_width_m_mean"] else None
                    ),
                },
                "observed": observed,
                "errors": errors,
                "failed_metrics": failed,
                "success": not failed,
            }
        )
    descriptor_finalization = all(
        bool(row["endpoint_only"]) and bool(row["finalize_snapshot_morphology"])
        for row in descriptor_build["descriptors"]
    )
    success = (
        not layout_errors
        and descriptor_finalization
        and bool(descriptor_engine["success"])
        and all(report["success"] for report in reports)
    )
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "success": success,
        "endpoint_policy": "only the final snapshot is constrained; the intermediate growth path is not calibrated",
        "layout_errors": layout_errors,
        "descriptor_finalization_enabled": descriptor_finalization,
        "descriptor_engine_validation_success": bool(descriptor_engine["success"]),
        "thresholds": THRESHOLDS,
        "genotypes": reports,
    }


def main() -> None:
    repo_root = repo_root_from_script()
    default_root = (
        repo_root
        / "Resources"
        / "DigitalAgricultureProject"
        / "Data"
        / "Experiments"
        / EXPERIMENT_ID
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=default_root)
    args = parser.parse_args()
    report = validate(args.data_root.resolve())
    output = args.data_root.resolve() / "endpoint_field_validation.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "output": str(output)}, indent=2))
    if not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
