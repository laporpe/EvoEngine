#!/usr/bin/env python3
"""Normalize the August 11 endpoint measurements for the 2026 6x10 field."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from sorghum_2026_6x10_data import (
    GENOTYPE_BY_RANGE,
    GENOTYPE_LABELS,
    ROW_GENOTYPES,
    SourceWorkbook,
    indexed_rows,
    integer,
    iso_date,
    mean_std,
    numeric,
    repo_root_from_script,
    sha256,
    source_ref,
    token_status,
    write_csv,
)
from sorghum_xlsx import SourceRow, read_nonempty_cells, read_table


EXPERIMENT_ID = "Sorghum2026_6x10_2026-08-11"
SESSION_ID = "FinalSnapshot2026-08-11"
SOURCE_PREFIX = "2026-08-11"
FAMILIES = ("ANGLES-TILLERS", "INTERNODES", "LEAVES")
PRIOR_ROOT = "GeneratedAssets/Experiments/Sorghum2026_6x10/Descriptors/MeasurementStage02"


def load_sources(source_dir: Path) -> dict[str, SourceWorkbook]:
    sources = {}
    for family in FAMILIES:
        path = source_dir / f"{SOURCE_PREFIX}-{family}_gsheet.xlsx"
        if not path.is_file():
            raise FileNotFoundError(f"missing source workbook: {path}")
        rows = tuple(row for row in read_table(path) if numeric(row.values.get("Range")) is not None)
        if len(rows) != 15:
            raise ValueError(f"{path.name} has {len(rows)} measurement rows; expected 15")
        sources[family] = SourceWorkbook(SESSION_ID, family, path, sha256(path), rows)
    return sources


def field(row: SourceRow, *names: str) -> tuple[str, object]:
    for name in names:
        if name in row.values:
            return name, row.values[name]
    raise KeyError(f"none of {names} exists at row {row.row_number}")


def yes_no(value: object) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"yes", "y", "true", "1"}:
        return True
    if text in {"no", "n", "false", "0"}:
        return False
    return None


def maximum_rank(row: SourceRow, pattern: str) -> int:
    ranks = [int(match.group(1)) for name in row.values if (match := re.fullmatch(pattern, name))]
    return max(ranks, default=0)


def normalize_sources(sources: dict[str, SourceWorkbook]) -> dict[str, list[dict[str, object]]]:
    indexed = {family: indexed_rows(source) for family, source in sources.items()}
    plants: list[dict[str, object]] = []
    leaves: list[dict[str, object]] = []
    internodes: list[dict[str, object]] = []
    tillers: list[dict[str, object]] = []
    leaf_angles: list[dict[str, object]] = []

    for range_id in sorted(GENOTYPE_BY_RANGE, reverse=True):
        genotype_id = GENOTYPE_BY_RANGE[range_id]
        for plant_tag in range(1, 6):
            rows = {family: family_rows[(range_id, plant_tag)] for family, family_rows in indexed.items()}
            dates_by_family = {family: iso_date(row.values["Date"]) for family, row in rows.items()}
            dates = set(dates_by_family.values())
            plots = {integer(row.values.get("PlotID")) for row in rows.values()}
            if len(plots) != 1 or None in plots:
                raise ValueError(f"inconsistent plot for Range {range_id} Plant {plant_tag}")
            plant_id = f"{SESSION_ID}_{genotype_id}_P{plant_tag:02d}"
            internode_row, leaf_row, angle_row = rows["INTERNODES"], rows["LEAVES"], rows["ANGLES-TILLERS"]
            height_name, height_raw = field(
                internode_row,
                "Plant Height tallest point (leaf, or panicle if present)",
                "Plant Height tallest leaf unaltered",
            )
            panicle_name, panicle_raw = field(internode_row, "Panicle Emerged", "Panicle emerged")
            panicle_length = numeric(internode_row.values.get("PANICLE LENGTH"))
            panicle_width = numeric(internode_row.values.get("PANICLE WIDTH"))
            height_cm = numeric(height_raw)
            stem_y = numeric(angle_row.values.get("Stem Angle Y"))
            plants.append(
                {
                    "experiment_id": EXPERIMENT_ID,
                    "session_id": SESSION_ID,
                    "collection_date": max(dates),
                    "collection_dates": ";".join(sorted(dates)),
                    "collection_date_angles_tillers": dates_by_family["ANGLES-TILLERS"],
                    "collection_date_internodes": dates_by_family["INTERNODES"],
                    "collection_date_leaves": dates_by_family["LEAVES"],
                    "genotype_id": genotype_id,
                    "genotype_label": GENOTYPE_LABELS[genotype_id],
                    "source_range_id": range_id,
                    "source_plot_id": plots.pop(),
                    "source_plant_tag": plant_tag,
                    "plant_id": plant_id,
                    "height_m": height_cm / 100.0 if height_cm is not None else None,
                    "leaf_count": integer(leaf_row.values.get("LeafNumber")),
                    "visible_collared_leaf_count": integer(internode_row.values.get("Num leaves uppermost")),
                    "tiller_count": integer(angle_row.values.get("TillerNumber")),
                    "main_culm_lean_deg_derived": 90.0 - abs(stem_y) if stem_y is not None else None,
                    "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                    "panicle_emerged": yes_no(panicle_raw),
                    "panicle_length_m": panicle_length / 100.0 if panicle_length is not None else None,
                    "panicle_width_m": panicle_width / 100.0 if panicle_width is not None else None,
                    "height_source": source_ref(sources["INTERNODES"], internode_row, height_name),
                    "leaf_count_source": source_ref(sources["LEAVES"], leaf_row, "LeafNumber"),
                    "tiller_count_source": source_ref(sources["ANGLES-TILLERS"], angle_row, "TillerNumber"),
                    "panicle_emerged_source": source_ref(sources["INTERNODES"], internode_row, panicle_name),
                    "panicle_length_source": source_ref(sources["INTERNODES"], internode_row, "PANICLE LENGTH"),
                    "panicle_width_source": source_ref(sources["INTERNODES"], internode_row, "PANICLE WIDTH"),
                }
            )

            for rank in range(1, maximum_rank(leaf_row, r"LeafRankWidth(\d+)" ) + 1):
                width_name, length_name = f"LeafRankWidth{rank}", f"LeafRankLength{rank}"
                width_raw, length_raw = leaf_row.values.get(width_name), leaf_row.values.get(length_name)
                width, length = numeric(width_raw), numeric(length_raw)
                leaves.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "session_id": SESSION_ID,
                        "genotype_id": genotype_id,
                        "plant_id": plant_id,
                        "leaf_rank": rank,
                        "width_raw": width_raw,
                        "width_unit_policy": "cm_confirmed_by_companion_archive_protocol",
                        "width_m": width / 100.0 if width is not None else None,
                        "width_qc": token_status(width_raw),
                        "width_source": source_ref(sources["LEAVES"], leaf_row, width_name),
                        "length_raw": length_raw,
                        "length_unit_policy": "cm_confirmed_by_companion_archive_protocol",
                        "length_m": length / 100.0 if length is not None else None,
                        "length_qc": token_status(length_raw),
                        "length_source": source_ref(sources["LEAVES"], leaf_row, length_name),
                    }
                )

            cumulative_m = 0.0
            for rank in range(1, maximum_rank(internode_row, r"CollarRankLength(\d+)") + 1):
                length_name = f"CollarRankLength{rank}"
                major_name = f"CollarRankDiameter-sheeth-axis{rank}"
                minor_name = f"CollarRankDiameter-perpindicular{rank}"
                length_raw = internode_row.values.get(length_name)
                length = numeric(length_raw)
                length_m = length / 100.0 if length is not None else None
                if length_m is not None:
                    cumulative_m += length_m
                major, minor = numeric(internode_row.values.get(major_name)), numeric(internode_row.values.get(minor_name))
                internodes.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "session_id": SESSION_ID,
                        "genotype_id": genotype_id,
                        "plant_id": plant_id,
                        "internode_rank": rank,
                        "length_raw": length_raw,
                        "length_semantics": "individual_collar_length_cm",
                        "internode_length_m": length_m,
                        "collar_elevation_m": cumulative_m if length is not None else None,
                        "length_qc": token_status(length_raw),
                        "length_source": source_ref(sources["INTERNODES"], internode_row, length_name),
                        "diameter_sheath_axis_raw_mm": internode_row.values.get(major_name),
                        "diameter_sheath_axis_m": major / 1000.0 if major is not None else None,
                        "diameter_sheath_axis_source": source_ref(sources["INTERNODES"], internode_row, major_name),
                        "diameter_perpendicular_raw_mm": internode_row.values.get(minor_name),
                        "diameter_perpendicular_m": minor / 1000.0 if minor is not None else None,
                        "diameter_perpendicular_source": source_ref(sources["INTERNODES"], internode_row, minor_name),
                        "effective_diameter_m": math.sqrt(major * minor) / 1000.0 if major is not None and minor is not None else None,
                    }
                )

            for rank in range(1, maximum_rank(angle_row, r"Connects Above Ground Tiller(\d+)") + 1):
                y_name = f"Y Angle from Ground Tiller{rank}"
                y_angle = numeric(angle_row.values.get(y_name))
                tillers.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "session_id": SESSION_ID,
                        "genotype_id": genotype_id,
                        "plant_id": plant_id,
                        "tiller_rank": rank,
                        "connection_raw": angle_row.values.get(f"Connects Above Ground Tiller{rank}"),
                        "leaf_count_raw": angle_row.values.get(f"Num Leaves Tiller{rank}"),
                        "leaf_count": integer(angle_row.values.get(f"Num Leaves Tiller{rank}")),
                        "x_angle_deg": numeric(angle_row.values.get(f"X Angle from Ground Tiller{rank}")),
                        "y_angle_deg": y_angle,
                        "z_angle_deg": numeric(angle_row.values.get(f"Z Angle from Ground Tiller{rank}")),
                        "insertion_angle_deg_derived": 90.0 - abs(y_angle) if y_angle is not None and abs(y_angle) <= 90.0 else None,
                        "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                        "source": source_ref(sources["ANGLES-TILLERS"], angle_row, y_name),
                    }
                )

            for rank in range(1, maximum_rank(angle_row, r"Leaf(\d+)Y") + 1):
                y_name = f"Leaf{rank}Y"
                y_angle = numeric(angle_row.values.get(y_name))
                leaf_angles.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "session_id": SESSION_ID,
                        "genotype_id": genotype_id,
                        "plant_id": plant_id,
                        "leaf_rank": rank,
                        "x_angle_deg": numeric(angle_row.values.get(f"Leaf{rank}X")),
                        "y_angle_deg": y_angle,
                        "z_angle_deg": numeric(angle_row.values.get(f"Leaf{rank}Z")),
                        "insertion_angle_deg_derived": 90.0 - abs(y_angle) if y_angle is not None and abs(y_angle) <= 90.0 else None,
                        "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                        "source": source_ref(sources["ANGLES-TILLERS"], angle_row, y_name),
                    }
                )

    return {
        "plants": plants,
        "leaves": leaves,
        "internodes": internodes,
        "tillers": tillers,
        "leaf_angles": leaf_angles,
        "qc": [],
    }


def target_tables(normalized: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    plant_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in normalized["plants"]:
        plant_groups[str(row["genotype_id"])].append(row)
    descriptor_targets = []
    for genotype_id, rows in sorted(plant_groups.items()):
        record: dict[str, object] = {
            "experiment_id": EXPERIMENT_ID,
            "session_id": SESSION_ID,
            "genotype_id": genotype_id,
            "source_range_id": next(key for key, value in GENOTYPE_BY_RANGE.items() if value == genotype_id),
            "sample_count": len(rows),
            "technical_prior": f"{PRIOR_ROOT}/{genotype_id}.sorghumls",
            "endpoint_only": True,
        }
        for name in ("height_m", "leaf_count", "tiller_count", "main_culm_lean_deg_derived", "panicle_length_m", "panicle_width_m"):
            samples = [float(row[name]) for row in rows if row[name] is not None]
            mean, std = mean_std(samples)
            record[f"{name}_mean"], record[f"{name}_std"] = mean, std
        emergence = [bool(row["panicle_emerged"]) for row in rows if row["panicle_emerged"] is not None]
        record["panicle_emerged_n"] = len(emergence)
        record["panicle_emerged_rate"] = sum(emergence) / len(emergence) if emergence else None
        descriptor_targets.append(record)

    def rank_targets(table: str, rank_field: str, value_fields: tuple[str, ...]) -> list[dict[str, object]]:
        groups: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
        for row in normalized[table]:
            groups[(str(row["genotype_id"]), int(row[rank_field]))].append(row)
        result = []
        for (genotype_id, rank), rows in sorted(groups.items()):
            record: dict[str, object] = {
                "experiment_id": EXPERIMENT_ID,
                "session_id": SESSION_ID,
                "genotype_id": genotype_id,
                rank_field: rank,
            }
            for name in value_fields:
                samples = [float(row[name]) for row in rows if row[name] is not None]
                mean, std = mean_std(samples)
                record[f"{name}_n"], record[f"{name}_mean"], record[f"{name}_std"] = len(samples), mean, std
            result.append(record)
        return result

    return {
        "descriptor_targets": descriptor_targets,
        "leaf_rank_targets": rank_targets("leaves", "leaf_rank", ("length_m", "width_m")),
        "internode_rank_targets": rank_targets("internodes", "internode_rank", ("internode_length_m", "effective_diameter_m")),
        "leaf_angle_rank_targets": rank_targets("leaf_angles", "leaf_rank", ("insertion_angle_deg_derived",)),
    }


def write_outputs(source_dir: Path, output_dir: Path) -> dict[str, object]:
    sources = load_sources(source_dir)
    normalized = normalize_sources(sources)
    targets = target_tables(normalized)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = source_dir / "Digitized-Data-selected.zip"
    manifest = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "session_id": SESSION_ID,
        "source_directory": source_dir.name,
        "source_archive": {"file_name": archive.name, "sha256": sha256(archive)} if archive.is_file() else None,
        "workbooks": [
            {
                "family": source.family,
                "file_name": source.path.name,
                "sha256": source.sha256,
                "measurement_rows": len(source.rows),
                "sheet2_notes": [cell.value for cell in read_nonempty_cells(source.path, "Sheet2")],
            }
            for source in sources.values()
        ],
    }
    (output_dir / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    contract = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "endpoint_policy": "descriptor-authored final snapshot; intermediate growth trajectory is not calibrated",
        "source_range_mapping": {str(key): value for key, value in GENOTYPE_BY_RANGE.items()},
        "layout": {"rows": 6, "columns": 10, "row_genotypes": list(ROW_GENOTYPES), "plants_per_genotype": 20},
        "measurement_units": {"leaf_length_width": "cm", "internode_length": "cm", "diameters": "mm", "panicle_length_width": "cm"},
        "panicle_policy": "unanimous measured emergence controls endpoint enablement; measured C length and width control geometry",
        "angle_policy": "90-abs(device Y), pending coordinate-system confirmation",
    }
    (output_dir / "validation_contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    for name, rows in {**normalized, **targets}.items():
        write_csv(output_dir / f"{name}.csv", rows)
    summary = {
        "plant_rows": len(normalized["plants"]),
        "leaf_rows": len(normalized["leaves"]),
        "internode_rows": len(normalized["internodes"]),
        "tiller_rows": len(normalized["tillers"]),
        "leaf_angle_rows": len(normalized["leaf_angles"]),
        "descriptor_targets": len(targets["descriptor_targets"]),
    }
    (output_dir / "normalization_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=repo_root.parent / "sources" / EXPERIMENT_ID)
    parser.add_argument("--output-dir", type=Path, default=project_root / "Data" / "Experiments" / EXPERIMENT_ID)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(write_outputs(args.source_dir.resolve(), args.output_dir.resolve()), indent=2))


if __name__ == "__main__":
    main()
