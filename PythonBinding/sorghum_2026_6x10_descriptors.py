#!/usr/bin/env python3
"""Build six measured-trait descriptor populations for the 2026 6x10 field."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, repo_root_from_script, sha256
from sorghum_migrate_fidelity_v4_descriptors import curve_plotted, replace_block, single


DESCRIPTOR_ROOT = Path("GeneratedAssets") / "Experiments" / EXPERIMENT_ID / "Descriptors"
SESSIONS = ("MeasurementStage01", "MeasurementStage02")
GENOTYPES = ("GenotypeA", "GenotypeB", "GenotypeC")
UNMEASURED_LEAF_GRAVITY_COMPLIANCE = 0.02


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def values(rows: list[dict[str, str]], field: str) -> list[float]:
    return [float(row[field]) for row in rows if row.get(field) not in (None, "")]


def stable_handle(relative: Path, kind: str) -> int:
    digest = hashlib.sha256(f"{EXPERIMENT_ID}|{kind}|{relative.as_posix()}".encode()).digest()
    return int.from_bytes(digest[:8], "little") or 1


def folder_metadata(path: Path, assets_root: Path) -> None:
    relative = path.relative_to(assets_root)
    sidecar = path.with_name(f"{path.name}.evefoldermeta")
    if sidecar.exists():
        return
    sidecar.write_text(
        f"handle_: {stable_handle(relative, 'folder')}\ntype_name: {path.name}\n",
        encoding="utf-8",
    )


def ensure_asset_folders(path: Path, assets_root: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    current = path
    while current != assets_root and current.name != "GeneratedAssets":
        folder_metadata(current, assets_root)
        current = current.parent


def file_metadata(path: Path, assets_root: Path) -> None:
    relative = path.relative_to(assets_root)
    sidecar = Path(f"{path}.evefilemeta")
    if sidecar.exists():
        return
    sidecar.write_text(
        "\n".join(
            (
                f"asset_extension_: {path.suffix}",
                f"asset_file_name_: {path.stem}",
                "asset_type_name_: SorghumLSDescriptor",
                f"asset_handle_: {stable_handle(relative, 'asset')}",
                "",
            )
        ),
        encoding="utf-8",
    )


def rank_distribution(
    rows: list[dict[str, str]],
    mean_field: str,
    std_field: str,
    count_field: str,
    name: str,
    scale: float = 1.0,
) -> tuple[str, dict[str, object]]:
    measured = [
        (int(row[next(field for field in row if field.endswith("_rank"))]), int(row[count_field]), float(row[mean_field]) * scale, float(row[std_field] or 0.0) * scale)
        for row in rows
        if row.get(mean_field) not in (None, "") and int(row.get(count_field) or 0) > 0
    ]
    if len(measured) < 2:
        raise ValueError(f"{name} needs at least two measured rank targets")
    max_rank = max(rank for rank, _, _, _ in measured)
    mean_max = max(mean for _, _, mean, _ in measured)
    std_max = max(std for _, _, _, std in measured)
    positions = [
        (0.0 if max_rank == 1 else (rank - 1) / (max_rank - 1), mean / mean_max)
        for rank, _, mean, _ in measured
    ]
    deviations = [
        (0.0 if max_rank == 1 else (rank - 1) / (max_rank - 1), std / std_max if std_max else 0.0)
        for rank, _, _, std in measured
    ]
    return (
        curve_plotted(name, 0.0, mean_max, positions, std_max, deviations),
        {
            "max_rank": max_rank,
            "maximum_mean": mean_max,
            "maximum_std": std_max,
            "rank_sample_counts": {str(rank): count for rank, count, _, _ in measured},
            "profile": positions,
            "calibration_scale": scale,
        },
    )


def observed_tiller_angle(tiller_rows: list[dict[str, str]]) -> tuple[float, float]:
    angles = values(tiller_rows, "insertion_angle_deg_derived")
    return (
        statistics.fmean(angles) if angles else 25.0,
        statistics.pstdev(angles) if len(angles) > 1 else 0.0,
    )


def bootstrap_interval(samples: list[float], seed: int, replicates: int = 10000) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choice(samples) for _ in samples) for _ in range(replicates)
    )
    return means[int(0.025 * replicates)], means[min(replicates - 1, int(0.975 * replicates))]


def uncertainty(samples: list[float], seed: int) -> dict[str, object]:
    leave_one_out = [
        statistics.fmean(value for index, value in enumerate(samples) if index != excluded)
        for excluded in range(len(samples))
    ]
    low, high = bootstrap_interval(samples, seed)
    return {
        "n": len(samples),
        "mean": statistics.fmean(samples),
        "population_std": statistics.pstdev(samples),
        "leave_one_out_mean_min": min(leave_one_out),
        "leave_one_out_mean_max": max(leave_one_out),
        "bootstrap_mean_95_low": low,
        "bootstrap_mean_95_high": high,
    }


def scalar_block(text: str, name: str, mean: float, deviation: float) -> str:
    return replace_block(text, name, single(name, mean, deviation))


def build_descriptor(
    base_text: str,
    target: dict[str, str],
    leaf_ranks: list[dict[str, str]],
    internode_ranks: list[dict[str, str]],
    leaf_angle_ranks: list[dict[str, str]],
    tiller_rows: list[dict[str, str]],
    overrides: dict[str, float],
) -> tuple[str, dict[str, object]]:
    text = base_text
    leaf_mean = float(target["leaf_count_mean"])
    leaf_std = float(target["leaf_count_std"])
    tiller_mean = float(target["tiller_count_mean"])
    tiller_std = float(target["tiller_count_std"])
    lean_mean = float(target["main_culm_lean_deg_derived_mean"])
    lean_std = float(target["main_culm_lean_deg_derived_std"])
    text = scalar_block(text, "total_phytomer_count", leaf_mean, leaf_std)
    text = scalar_block(text, "main_culm_lean_angle", lean_mean, lean_std)
    text = scalar_block(text, "tiller_count", tiller_mean, tiller_std)
    text = re.sub(r"(?m)^tiller_count_min:.*$", f"tiller_count_min: {max(0, math.floor(tiller_mean - 2 * tiller_std))}", text)
    text = re.sub(r"(?m)^tiller_count_max:.*$", f"tiller_count_max: {max(1, math.ceil(tiller_mean + 2 * tiller_std))}", text)
    tiller_angle_mean, tiller_angle_std = observed_tiller_angle(tiller_rows)
    text = scalar_block(text, "tiller_insertion_angle", tiller_angle_mean, tiller_angle_std)
    text = replace_block(
        text,
        "leaf_bending",
        curve_plotted("leaf_bending", 0.0, 1.0, [(0.0, 0.0), (1.0, 0.0)], 0.0, [(0.0, 0.0), (1.0, 0.0)]),
    )
    text = scalar_block(text, "leaf_gravity_droop_compliance", UNMEASURED_LEAF_GRAVITY_COMPLIANCE, 0.0)

    distributions = {}
    for name, rows, mean_field, std_field, count_field, scale in (
        ("leaf_blade_length", leaf_ranks, "length_m_mean", "length_m_std", "length_m_n", float(overrides.get("leaf_length_scale", 1.0))),
        ("leaf_blade_max_width", leaf_ranks, "width_m_mean", "width_m_std", "width_m_n", float(overrides.get("leaf_width_scale", 1.0))),
        ("internode_length", internode_ranks, "internode_length_m_mean", "internode_length_m_std", "internode_length_m_n", float(overrides.get("internode_length_scale", 1.0))),
        ("internode_thickness", internode_ranks, "effective_diameter_m_mean", "effective_diameter_m_std", "effective_diameter_m_n", float(overrides.get("internode_thickness_scale", 1.0))),
        ("leaf_insertion_angle", leaf_angle_ranks, "insertion_angle_deg_derived_mean", "insertion_angle_deg_derived_std", "insertion_angle_deg_derived_n", 1.0),
    ):
        block, report = rank_distribution(rows, mean_field, std_field, count_field, name, scale)
        text = replace_block(text, name, block)
        distributions[name] = report
    text = re.sub(r"(?m)^leaf_width_scale:.*$", "leaf_width_scale: 1", text)
    return text, {
        "leaf_count_mean": leaf_mean,
        "leaf_count_std": leaf_std,
        "tiller_count_mean": tiller_mean,
        "tiller_count_std": tiller_std,
        "main_culm_lean_deg_derived_mean": lean_mean,
        "main_culm_lean_deg_derived_std": lean_std,
        "tiller_insertion_angle_deg_derived_mean": tiller_angle_mean,
        "tiller_insertion_angle_deg_derived_std": tiller_angle_std,
        "leaf_bending_policy": "neutral_zero_unmeasured",
        "leaf_gravity_droop_compliance": UNMEASURED_LEAF_GRAVITY_COMPLIANCE,
        "whole_plant_height_policy": "diagnostic_only_without_measured_leaf_curvature",
        "calibration_overrides": overrides,
        "distributions": distributions,
    }


def build_all(data_root: Path, assets_root: Path, base_descriptor: Path) -> list[dict[str, object]]:
    targets = read_csv(data_root / "descriptor_targets.csv")
    plants = read_csv(data_root / "plants.csv")
    leaf_targets = read_csv(data_root / "leaf_rank_targets.csv")
    internode_targets = read_csv(data_root / "internode_rank_targets.csv")
    leaf_angle_targets = read_csv(data_root / "leaf_angle_rank_targets.csv")
    tillers = read_csv(data_root / "tillers.csv")
    base_text = base_descriptor.read_text(encoding="utf-8")
    base_hash = sha256(base_descriptor)
    overrides_path = data_root / "descriptor_calibration_overrides.json"
    override_rows = json.loads(overrides_path.read_text(encoding="utf-8"))["descriptors"] if overrides_path.is_file() else {}
    try:
        technical_prior_path = base_descriptor.relative_to(assets_root).as_posix()
    except ValueError:
        technical_prior_path = str(base_descriptor)
    reports = []
    for target in targets:
        session_id = target["session_id"]
        genotype_id = target["genotype_id"]
        selected = lambda rows: [row for row in rows if row["session_id"] == session_id and row["genotype_id"] == genotype_id]
        text, parameters = build_descriptor(
            base_text,
            target,
            selected(leaf_targets),
            selected(internode_targets),
            selected(leaf_angle_targets),
            selected(tillers),
            {key: float(value) for key, value in override_rows.get(f"{session_id}|{genotype_id}", {}).items()},
        )
        relative = DESCRIPTOR_ROOT / session_id / f"{genotype_id}.sorghumls"
        output = assets_root / relative
        ensure_asset_folders(output.parent, assets_root)
        output.write_text(text, encoding="utf-8", newline="\n")
        file_metadata(output, assets_root)
        measured_plants = selected(plants)
        seed = int.from_bytes(hashlib.sha256(f"{session_id}|{genotype_id}".encode()).digest()[:4], "little")
        report = {
            "schema_version": 1,
            "experiment_id": EXPERIMENT_ID,
            "session_id": session_id,
            "genotype_id": genotype_id,
            "source_range_id": int(target["source_range_id"]),
            "descriptor_asset_path": relative.as_posix(),
            "descriptor_sha256": sha256(output),
            "technical_prior_asset_path": technical_prior_path,
            "technical_prior_sha256": base_hash,
            "technical_prior_is_biological_relationship": False,
            "measured_sample_count": len(measured_plants),
            "parameters": parameters,
            "source_uncertainty": {
                field: uncertainty(values(measured_plants, field), seed + index)
                for index, field in enumerate(("height_m", "leaf_count", "tiller_count"))
            },
            "provisional_assumptions": [
                "July 21 leaf widths interpreted as centimetres pending confirmation",
                "device Y angles converted as 90-abs(Y) pending coordinate confirmation",
                "leaf midrib curvature was not measured; intrinsic bending is neutral and gravity uses a shared 0.02 prior",
                "tallest-leaf height is diagnostic and is not fitted through gravity compliance",
                "BTX asset is a common technical serialization prior only; no pedigree relationship is assumed",
                "target GDD remains a technical finalized-snapshot parameter because 2026 GDD was not supplied",
            ],
        }
        reports.append(report)
    return reports


def write_reports(data_root: Path, reports: list[dict[str, object]]) -> None:
    (data_root / "descriptor_build_report.json").write_text(
        json.dumps({"schema_version": 1, "descriptors": reports}, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = []
    for report in reports:
        parameters = report["parameters"]
        rows.append(
            {
                "session_id": report["session_id"],
                "genotype_id": report["genotype_id"],
                "source_range_id": report["source_range_id"],
                "measured_sample_count": report["measured_sample_count"],
                "leaf_count_mean": parameters["leaf_count_mean"],
                "leaf_count_std": parameters["leaf_count_std"],
                "tiller_count_mean": parameters["tiller_count_mean"],
                "tiller_count_std": parameters["tiller_count_std"],
                "main_culm_lean_deg_derived_mean": parameters["main_culm_lean_deg_derived_mean"],
                "tiller_insertion_angle_deg_derived_mean": parameters["tiller_insertion_angle_deg_derived_mean"],
                "leaf_bending_policy": parameters["leaf_bending_policy"],
                "leaf_gravity_droop_compliance": parameters["leaf_gravity_droop_compliance"],
                "whole_plant_height_policy": parameters["whole_plant_height_policy"],
                "descriptor_asset_path": report["descriptor_asset_path"],
                "descriptor_sha256": report["descriptor_sha256"],
            }
        )
    with (data_root / "descriptor_parameters.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=project_root / "Data" / "Experiments" / EXPERIMENT_ID)
    parser.add_argument("--assets-root", type=Path, default=project_root / "Assets")
    parser.add_argument("--base-descriptor", type=Path, default=project_root / "Assets" / "ManualAssets" / "Descriptors" / "BTX.sorghumls")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    reports = build_all(args.data_root.resolve(), args.assets_root.resolve(), args.base_descriptor.resolve())
    write_reports(args.data_root.resolve(), reports)
    print(json.dumps({"descriptor_count": len(reports), "asset_paths": [report["descriptor_asset_path"] for report in reports]}, indent=2))


if __name__ == "__main__":
    main()
