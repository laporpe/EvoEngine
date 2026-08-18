#!/usr/bin/env python3
"""Build three endpoint-only A/B/C descriptors from the August 11 measurements."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from sorghum_2026_6x10_aug11_data import EXPERIMENT_ID, PRIOR_ROOT, SESSION_ID
from sorghum_2026_6x10_data import repo_root_from_script, sha256
from sorghum_2026_6x10_descriptors import (
    build_descriptor,
    ensure_asset_folders,
    file_metadata,
    read_csv,
)
from sorghum_migrate_fidelity_v4_descriptors import single


GENOTYPES = ("GenotypeA", "GenotypeB", "GenotypeC")
DESCRIPTOR_ROOT = Path("GeneratedAssets") / "Experiments" / EXPERIMENT_ID / "Descriptors" / "FinalSnapshot"
PANICLE_BRANCH_ANGLE_DEGREES = 32.0


def set_scalar(text: str, name: str, value: bool | float) -> str:
    rendered = str(value).lower() if isinstance(value, bool) else f"{value:.8g}"
    pattern = re.compile(rf"(?m)^{re.escape(name)}:.*$")
    return pattern.sub(f"{name}: {rendered}", text, count=1) if pattern.search(text) else f"{text.rstrip()}\n{name}: {rendered}\n"


def set_distribution(text: str, name: str, mean: float, deviation: float) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(name)}:.*?(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)")
    replacement = single(name, mean, deviation)
    return pattern.sub(replacement, text, count=1) if pattern.search(text) else f"{text.rstrip()}\n{replacement}"


def measured_panicle(text: str, target: dict[str, str]) -> tuple[str, dict[str, object]]:
    emergence_rate = float(target["panicle_emerged_rate"])
    if emergence_rate not in (0.0, 1.0):
        raise ValueError(f"mixed endpoint panicle emergence cannot be represented by one descriptor: {emergence_rate}")
    enabled = emergence_rate == 1.0
    text = set_scalar(text, "enable_panicle", enabled)
    report: dict[str, object] = {"enabled": enabled, "measured_emergence_rate": emergence_rate}
    if enabled:
        length_mean = float(target["panicle_length_m_mean"])
        length_std = float(target["panicle_length_m_std"])
        width_mean = float(target["panicle_width_m_mean"])
        width_std = float(target["panicle_width_m_std"])
        width_to_branch = 1.0 / (2.0 * math.sin(math.radians(PANICLE_BRANCH_ANGLE_DEGREES)))
        branch_mean, branch_std = width_mean * width_to_branch, width_std * width_to_branch
        text = set_distribution(text, "panicle_rachis_length_m", length_mean, length_std)
        text = set_distribution(text, "panicle_branch_length_m", branch_mean, branch_std)
        report.update(
            {
                "measured_length_m_mean": length_mean,
                "measured_length_m_std": length_std,
                "measured_width_m_mean": width_mean,
                "measured_width_m_std": width_std,
                "panicle_rachis_length_m_mean": length_mean,
                "panicle_branch_length_m_mean": branch_mean,
                "width_mapping": "branch_length = measured_width / (2*sin(branch_angle))",
                "branch_angle_degrees": PANICLE_BRANCH_ANGLE_DEGREES,
            }
        )
    return text, report


def build_all(data_root: Path, assets_root: Path, prior_assets_root: Path | None = None) -> list[dict[str, object]]:
    targets = read_csv(data_root / "descriptor_targets.csv")
    plants = read_csv(data_root / "plants.csv")
    leaf_targets = read_csv(data_root / "leaf_rank_targets.csv")
    internode_targets = read_csv(data_root / "internode_rank_targets.csv")
    leaf_angle_targets = read_csv(data_root / "leaf_angle_rank_targets.csv")
    tillers = read_csv(data_root / "tillers.csv")
    overrides_path = data_root / "descriptor_calibration_overrides.json"
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))["descriptors"] if overrides_path.is_file() else {}
    prior_assets_root = prior_assets_root or assets_root
    reports = []
    for target in targets:
        genotype_id = target["genotype_id"]
        prior_relative = Path(PRIOR_ROOT) / f"{genotype_id}.sorghumls"
        prior_path = prior_assets_root / prior_relative

        def selected(rows: list[dict[str, str]]) -> list[dict[str, str]]:
            return [row for row in rows if row["genotype_id"] == genotype_id]

        calibration = {key: float(value) for key, value in overrides.get(genotype_id, {}).items()}
        text, parameters = build_descriptor(
            prior_path.read_text(encoding="utf-8"),
            target,
            selected(leaf_targets),
            selected(internode_targets),
            selected(leaf_angle_targets),
            selected(tillers),
            calibration,
        )
        text, panicle = measured_panicle(text, target)
        text = set_scalar(text, "finalize_snapshot_morphology", True)
        relative = DESCRIPTOR_ROOT / f"{genotype_id}.sorghumls"
        output = assets_root / relative
        ensure_asset_folders(output.parent, assets_root)
        output.write_text(text, encoding="utf-8", newline="\n")
        file_metadata(output, assets_root)
        reports.append(
            {
                "schema_version": 1,
                "experiment_id": EXPERIMENT_ID,
                "session_id": SESSION_ID,
                "genotype_id": genotype_id,
                "source_range_id": int(target["source_range_id"]),
                "descriptor_asset_path": relative.as_posix(),
                "descriptor_sha256": sha256(output),
                "technical_prior_asset_path": prior_relative.as_posix(),
                "technical_prior_sha256": sha256(prior_path),
                "technical_prior_is_existing_btx_derived_genotype": True,
                "measured_sample_count": len(selected(plants)),
                "endpoint_only": True,
                "finalize_snapshot_morphology": True,
                "parameters": {**parameters, "panicle": panicle},
                "measured_targets": {
                    key: value
                    for key, value in target.items()
                    if key.endswith("_mean") or key.endswith("_std") or key.startswith("panicle_emerged")
                },
            }
        )
    if {report["genotype_id"] for report in reports} != set(GENOTYPES):
        raise ValueError("descriptor targets must cover GenotypeA, GenotypeB, and GenotypeC")
    return reports


def write_reports(data_root: Path, reports: list[dict[str, object]]) -> None:
    (data_root / "descriptor_build_report.json").write_text(
        json.dumps({"schema_version": 1, "experiment_id": EXPERIMENT_ID, "descriptors": reports}, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = []
    for report in reports:
        parameters = report["parameters"]
        rows.append(
            {
                "genotype_id": report["genotype_id"],
                "source_range_id": report["source_range_id"],
                "leaf_count_mean": parameters["leaf_count_mean"],
                "tiller_count_mean": parameters["tiller_count_mean"],
                "height_target_m": report["measured_targets"]["height_m_mean"],
                "panicle_enabled": parameters["panicle"]["enabled"],
                "panicle_length_target_m": parameters["panicle"].get("measured_length_m_mean"),
                "panicle_width_target_m": parameters["panicle"].get("measured_width_m_mean"),
                "endpoint_only": True,
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    reports = build_all(args.data_root.resolve(), args.assets_root.resolve())
    write_reports(args.data_root.resolve(), reports)
    print(json.dumps({"descriptor_count": len(reports), "asset_paths": [row["descriptor_asset_path"] for row in reports]}, indent=2))


if __name__ == "__main__":
    main()
