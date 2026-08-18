#!/usr/bin/env python3
"""Normalize the two-session, three-genotype 2026 sorghum measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sorghum_xlsx import SourceRow, read_nonempty_cells, read_table


EXPERIMENT_ID = "Sorghum2026_6x10"
SESSION_PREFIXES = {
    "MeasurementStage01": "2026-07-15",
    "MeasurementStage02": "2026-07-21",
}
FAMILIES = ("ANGLES-TILLERS", "INTERNODES", "LEAVES")
GENOTYPE_BY_RANGE = {75: "GenotypeA", 74: "GenotypeB", 73: "GenotypeC"}
GENOTYPE_LABELS = {
    "GenotypeA": "Genotype A (75)",
    "GenotypeB": "Genotype B (74)",
    "GenotypeC": "Genotype C (73)",
}
ROW_GENOTYPES = (
    "GenotypeA",
    "GenotypeA",
    "GenotypeB",
    "GenotypeB",
    "GenotypeC",
    "GenotypeC",
)
MISSING_TOKENS = {
    "": "blank",
    "na": "not_applicable",
    "x": "not_measured",
    "u": "unknown",
    "unmeasured": "not_measured",
    "unmeasurable": "unmeasurable",
    "r": "rolled_unmeasured",
    "baby": "immature_unmeasured",
}


@dataclass(frozen=True)
class SourceWorkbook:
    session_id: str
    family: str
    path: Path
    sha256: str
    rows: tuple[SourceRow, ...]


def repo_root_from_script() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CMakeLists.txt").exists() and (parent / "Resources" / "DigitalAgricultureProject").exists():
            return parent
    return Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def workbook_name(prefix: str, family: str) -> str:
    return f"{prefix}-{family}_gsheet.xlsx"


def load_sources(source_dir: Path) -> dict[tuple[str, str], SourceWorkbook]:
    sources = {}
    for session_id, prefix in SESSION_PREFIXES.items():
        for family in FAMILIES:
            path = source_dir / workbook_name(prefix, family)
            if not path.is_file():
                raise FileNotFoundError(f"missing source workbook: {path}")
            rows = tuple(
                row
                for row in read_table(path)
                if numeric(row.values.get("Range")) is not None
            )
            if len(rows) != 15:
                raise ValueError(f"{path.name} has {len(rows)} measurement rows; expected 15")
            sources[(session_id, family)] = SourceWorkbook(
                session_id, family, path, sha256(path), rows
            )
    return sources


def numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def integer(value: object) -> int | None:
    number = numeric(value)
    return int(number) if number is not None and number.is_integer() else None


def iso_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return (date(1899, 12, 30) + timedelta(days=float(value))).isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"unsupported source date: {value}")


def token_status(value: object) -> str:
    if numeric(value) is not None:
        return "measured"
    return MISSING_TOKENS.get(str(value or "").strip().lower(), "annotation")


def source_ref(source: SourceWorkbook, row: SourceRow, field: str) -> str:
    cell = row.cells.get(field)
    return f"{source.path.name}|Sheet1|{cell.coordinate if cell else ''}"


def key_for(row: SourceRow) -> tuple[int, int]:
    range_id = integer(row.values.get("Range"))
    plant_tag = integer(row.values.get("PlantTag"))
    if range_id not in GENOTYPE_BY_RANGE or plant_tag is None:
        raise ValueError(f"invalid Range/PlantTag at source row {row.row_number}")
    return range_id, plant_tag


def indexed_rows(source: SourceWorkbook) -> dict[tuple[int, int], SourceRow]:
    rows = {key_for(row): row for row in source.rows}
    if len(rows) != len(source.rows):
        raise ValueError(f"duplicate Range/PlantTag keys in {source.path.name}")
    expected = {(range_id, tag) for range_id in GENOTYPE_BY_RANGE for tag in range(1, 6)}
    if set(rows) != expected:
        raise ValueError(f"unexpected plant keys in {source.path.name}: {sorted(set(rows) ^ expected)}")
    return rows


def mean_std(values: list[float]) -> tuple[float | None, float | None]:
    return (
        (statistics.fmean(values), statistics.pstdev(values))
        if values
        else (None, None)
    )


def normalize_sources(sources: dict[tuple[str, str], SourceWorkbook]) -> dict[str, list[dict[str, object]]]:
    plants: list[dict[str, object]] = []
    leaves: list[dict[str, object]] = []
    internodes: list[dict[str, object]] = []
    tillers: list[dict[str, object]] = []
    leaf_angles: list[dict[str, object]] = []
    qc: list[dict[str, object]] = []

    for session_id in SESSION_PREFIXES:
        family_rows = {
            family: indexed_rows(sources[(session_id, family)]) for family in FAMILIES
        }
        for range_id in sorted(GENOTYPE_BY_RANGE, reverse=True):
            genotype_id = GENOTYPE_BY_RANGE[range_id]
            for plant_tag in range(1, 6):
                rows = {family: values[(range_id, plant_tag)] for family, values in family_rows.items()}
                source_set = {sources[(session_id, family)].path.name for family in FAMILIES}
                dates = {iso_date(row.values["Date"]) for row in rows.values()}
                plots = {integer(row.values["PlotID"]) for row in rows.values()}
                if len(dates) != 1 or len(plots) != 1 or None in plots:
                    raise ValueError(f"inconsistent date/plot for {session_id} Range {range_id} Plant {plant_tag}")
                plant_id = f"{session_id}_{genotype_id}_P{plant_tag:02d}"
                internode_row = rows["INTERNODES"]
                leaves_row = rows["LEAVES"]
                angles_row = rows["ANGLES-TILLERS"]
                height_cm = numeric(internode_row.values.get("Plant Height tallest leaf unaltered"))
                leaf_count = integer(leaves_row.values.get("LeafNumber"))
                tiller_count = integer(angles_row.values.get("TillerNumber"))
                stem_y = numeric(angles_row.values.get("Stem Angle Y"))
                plants.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "session_id": session_id,
                        "collection_date": dates.pop(),
                        "genotype_id": genotype_id,
                        "genotype_label": GENOTYPE_LABELS[genotype_id],
                        "source_range_id": range_id,
                        "source_plot_id": plots.pop(),
                        "source_plant_tag": plant_tag,
                        "plant_id": plant_id,
                        "height_m": height_cm / 100.0 if height_cm is not None else None,
                        "leaf_count": leaf_count,
                        "visible_collared_leaf_count": integer(internode_row.values.get("Num leaves uppermost")),
                        "tiller_count": tiller_count,
                        "main_culm_lean_deg_derived": 90.0 - abs(stem_y) if stem_y is not None else None,
                        "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                        "panicle_emerged": internode_row.values.get("Panicle emerged"),
                        "source_workbooks": ";".join(sorted(source_set)),
                        "height_source": source_ref(
                            sources[(session_id, "INTERNODES")],
                            internode_row,
                            "Plant Height tallest leaf unaltered",
                        ),
                        "leaf_count_source": source_ref(
                            sources[(session_id, "LEAVES")], leaves_row, "LeafNumber"
                        ),
                        "tiller_count_source": source_ref(
                            sources[(session_id, "ANGLES-TILLERS")], angles_row, "TillerNumber"
                        ),
                    }
                )

                leaf_source = sources[(session_id, "LEAVES")]
                max_leaf_rank = 15 if session_id == "MeasurementStage01" else 16
                for rank in range(1, max_leaf_rank + 1):
                    width_field = f"LeafRankWidth{rank}"
                    length_field = f"LeafRankLength{rank}"
                    width_raw = leaves_row.values.get(width_field)
                    length_raw = leaves_row.values.get(length_field)
                    width_number = numeric(width_raw)
                    length_number = numeric(length_raw)
                    width_qc = token_status(width_raw)
                    length_qc = token_status(length_raw)
                    if session_id == "MeasurementStage01":
                        width_m = width_number / 1000.0 if width_number is not None else None
                        width_unit = "mm_declared"
                    else:
                        width_m = width_number / 100.0 if width_number is not None else None
                        width_unit = "cm_assumed_pending_confirmation"
                        if width_number is not None:
                            width_qc = "unit_assumption_pending_confirmation"
                    leaves.append(
                        {
                            "experiment_id": EXPERIMENT_ID,
                            "session_id": session_id,
                            "genotype_id": genotype_id,
                            "plant_id": plant_id,
                            "leaf_rank": rank,
                            "width_raw": width_raw,
                            "width_unit_policy": width_unit,
                            "width_m": width_m,
                            "width_qc": width_qc,
                            "width_source": source_ref(leaf_source, leaves_row, width_field),
                            "length_raw": length_raw,
                            "length_unit_policy": "cm_declared" if session_id == "MeasurementStage01" else "cm_inferred_from_continuity",
                            "length_m": length_number / 100.0 if length_number is not None else None,
                            "length_qc": length_qc,
                            "length_source": source_ref(leaf_source, leaves_row, length_field),
                        }
                    )

                internode_source = sources[(session_id, "INTERNODES")]
                max_internode_rank = 10 if session_id == "MeasurementStage01" else 16
                cumulative_m = 0.0
                previous_elevation_cm: float | None = None
                for rank in range(1, max_internode_rank + 1):
                    length_field = f"CollarRankLength{rank}"
                    major_field = f"CollarRankDiameter-sheeth-axis{rank}"
                    minor_field = f"CollarRankDiameter-perpindicular{rank}"
                    length_raw = internode_row.values.get(length_field)
                    length_number = numeric(length_raw)
                    if session_id == "MeasurementStage01":
                        collar_elevation_m = max(0.0, length_number - 1.0) / 100.0 if length_number is not None else None
                        internode_length_m = (
                            max(0.0, length_number - (previous_elevation_cm if previous_elevation_cm is not None else 1.0)) / 100.0
                            if length_number is not None
                            else None
                        )
                        length_semantics = "cumulative_collar_elevation_cm_minus_1cm_meter_offset"
                        if length_number is not None:
                            previous_elevation_cm = length_number
                    else:
                        internode_length_m = length_number / 100.0 if length_number is not None else None
                        if internode_length_m is not None:
                            cumulative_m += internode_length_m
                        collar_elevation_m = cumulative_m if length_number is not None else None
                        length_semantics = "individual_collar_length_cm"
                    major = numeric(internode_row.values.get(major_field))
                    minor = numeric(internode_row.values.get(minor_field))
                    internodes.append(
                        {
                            "experiment_id": EXPERIMENT_ID,
                            "session_id": session_id,
                            "genotype_id": genotype_id,
                            "plant_id": plant_id,
                            "internode_rank": rank,
                            "length_raw": length_raw,
                            "length_semantics": length_semantics,
                            "internode_length_m": internode_length_m,
                            "collar_elevation_m": collar_elevation_m,
                            "length_qc": token_status(length_raw),
                            "length_source": source_ref(internode_source, internode_row, length_field),
                            "diameter_sheath_axis_raw_mm": internode_row.values.get(major_field),
                            "diameter_sheath_axis_m": major / 1000.0 if major is not None else None,
                            "diameter_sheath_axis_source": source_ref(internode_source, internode_row, major_field),
                            "diameter_perpendicular_raw_mm": internode_row.values.get(minor_field),
                            "diameter_perpendicular_m": minor / 1000.0 if minor is not None else None,
                            "diameter_perpendicular_source": source_ref(internode_source, internode_row, minor_field),
                            "effective_diameter_m": math.sqrt(major * minor) / 1000.0 if major is not None and minor is not None else None,
                        }
                    )

                angle_source = sources[(session_id, "ANGLES-TILLERS")]
                for rank in range(1, 6):
                    connection_field = f"Connects Above Ground Tiller{rank}"
                    leaves_field = f"Num Leaves Tiller{rank}"
                    x_field = f"X Angle from Ground Tiller{rank}"
                    y_field = f"Y Angle from Ground Tiller{rank}"
                    z_field = f"Z Angle from Ground Tiller{rank}"
                    y_angle = numeric(angles_row.values.get(y_field))
                    tillers.append(
                        {
                            "experiment_id": EXPERIMENT_ID,
                            "session_id": session_id,
                            "genotype_id": genotype_id,
                            "plant_id": plant_id,
                            "tiller_rank": rank,
                            "connection_raw": angles_row.values.get(connection_field),
                            "leaf_count_raw": angles_row.values.get(leaves_field),
                            "leaf_count": integer(angles_row.values.get(leaves_field)),
                            "x_angle_deg": numeric(angles_row.values.get(x_field)),
                            "y_angle_deg": y_angle,
                            "z_angle_deg": numeric(angles_row.values.get(z_field)),
                            "insertion_angle_deg_derived": 90.0 - abs(y_angle) if y_angle is not None and abs(y_angle) <= 90.0 else None,
                            "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                            "source": source_ref(angle_source, angles_row, y_field),
                        }
                    )
                max_angle_rank = 15 if session_id == "MeasurementStage01" else 16
                for rank in range(1, max_angle_rank + 1):
                    y_field = f"Leaf{rank}Y"
                    y_angle = numeric(angles_row.values.get(y_field))
                    leaf_angles.append(
                        {
                            "experiment_id": EXPERIMENT_ID,
                            "session_id": session_id,
                            "genotype_id": genotype_id,
                            "plant_id": plant_id,
                            "leaf_rank": rank,
                            "x_angle_deg": numeric(angles_row.values.get(f"Leaf{rank}X")),
                            "y_angle_deg": y_angle,
                            "z_angle_deg": numeric(angles_row.values.get(f"Leaf{rank}Z")),
                            "insertion_angle_deg_derived": 90.0 - abs(y_angle) if y_angle is not None and abs(y_angle) <= 90.0 else None,
                            "angle_derivation_qc": "device_y_axis_assumption_pending_confirmation",
                            "source": source_ref(angle_source, angles_row, y_field),
                        }
                    )

    grouped_leaf_lengths: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for row in leaves:
        if row["length_m"] is not None:
            grouped_leaf_lengths[(str(row["session_id"]), str(row["genotype_id"]), int(row["leaf_rank"]))].append(float(row["length_m"]))
    for row in leaves:
        length = row["length_m"]
        peers = grouped_leaf_lengths[(str(row["session_id"]), str(row["genotype_id"]), int(row["leaf_rank"]))]
        peer_median = statistics.median([value for value in peers if value != length]) if len(peers) > 1 else None
        if (
            row["session_id"] == "MeasurementStage02"
            and length is not None
            and float(length) < 0.05
            and peer_median is not None
            and peer_median >= 0.30
            and float(length) < peer_median * 0.35
        ):
            row["length_m"] = None
            row["length_qc"] = "suspected_decimal_transcription_outlier_excluded"
            qc.append(
                {
                    "severity": "blocking_field",
                    "session_id": row["session_id"],
                    "genotype_id": row["genotype_id"],
                    "plant_id": row["plant_id"],
                    "field": f"leaf_length_rank_{row['leaf_rank']}",
                    "raw_value": row["length_raw"],
                    "source": row["length_source"],
                    "action": "excluded_from_calibration_without_correction",
                    "reason": f"value is less than 35% of peer median {peer_median:.4g} m",
                }
            )

    for row in leaves:
        if row["width_qc"] == "unit_assumption_pending_confirmation":
            qc.append(
                {
                    "severity": "assumption",
                    "session_id": row["session_id"],
                    "genotype_id": row["genotype_id"],
                    "plant_id": row["plant_id"],
                    "field": f"leaf_width_rank_{row['leaf_rank']}",
                    "raw_value": row["width_raw"],
                    "source": row["width_source"],
                    "action": "interpreted_as_cm_for_provisional_calibration",
                    "reason": "July 21 workbook omits units; magnitude is consistent with centimetres",
                }
            )

    return {
        "plants": plants,
        "leaves": leaves,
        "internodes": internodes,
        "tillers": tillers,
        "leaf_angles": leaf_angles,
        "qc": qc,
    }


def target_tables(normalized: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    plant_groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in normalized["plants"]:
        plant_groups[(str(row["session_id"]), str(row["genotype_id"]))].append(row)
    summary = []
    for (session_id, genotype_id), rows in sorted(plant_groups.items()):
        record: dict[str, object] = {
            "experiment_id": EXPERIMENT_ID,
            "session_id": session_id,
            "genotype_id": genotype_id,
            "source_range_id": next(key for key, value in GENOTYPE_BY_RANGE.items() if value == genotype_id),
            "sample_count": len(rows),
            "technical_prior": "ManualAssets/Descriptors/BTX.sorghumls",
            "technical_prior_is_biological_relationship": False,
        }
        for field in ("height_m", "leaf_count", "tiller_count", "main_culm_lean_deg_derived"):
            values = [float(row[field]) for row in rows if row[field] is not None]
            mean, std = mean_std(values)
            record[f"{field}_mean"] = mean
            record[f"{field}_std"] = std
        summary.append(record)

    def rank_targets(table: str, rank_field: str, value_fields: tuple[str, ...]) -> list[dict[str, object]]:
        groups: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
        for row in normalized[table]:
            groups[(str(row["session_id"]), str(row["genotype_id"]), int(row[rank_field]))].append(row)
        result = []
        for (session_id, genotype_id, rank), rows in sorted(groups.items()):
            record: dict[str, object] = {
                "experiment_id": EXPERIMENT_ID,
                "session_id": session_id,
                "genotype_id": genotype_id,
                rank_field: rank,
            }
            for field in value_fields:
                values = [float(row[field]) for row in rows if row[field] is not None]
                mean, std = mean_std(values)
                record[f"{field}_n"] = len(values)
                record[f"{field}_mean"] = mean
                record[f"{field}_std"] = std
            result.append(record)
        return result

    return {
        "descriptor_targets": summary,
        "leaf_rank_targets": rank_targets("leaves", "leaf_rank", ("length_m", "width_m")),
        "internode_rank_targets": rank_targets(
            "internodes", "internode_rank", ("internode_length_m", "effective_diameter_m")
        ),
        "leaf_angle_rank_targets": rank_targets(
            "leaf_angles", "leaf_rank", ("insertion_angle_deg_derived",)
        ),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validation_contract(sources: dict[tuple[str, str], SourceWorkbook]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "status": "approved_defaults_with_flagged_source_assumptions",
        "source_contract": {
            "workbook_count": 6,
            "plants_per_workbook": 15,
            "plants_per_genotype_session": 5,
            "original_workbooks_immutable": True,
            "sha256": {source.path.name: source.sha256 for source in sources.values()},
        },
        "layout_contract": {
            "rows": 6,
            "columns": 10,
            "plant_count": 60,
            "row_genotypes": list(ROW_GENOTYPES),
            "plants_per_genotype": 20,
            "column_spacing_m": 0.76,
            "row_spacing_within_block_m": 1.10,
            "row_spacing_between_blocks_m": 2.20,
            "block_center_spacing_m": 3.30,
            "profile_source": "ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene",
        },
        "instrumentation_contract": {
            "parbar_rigs": 3,
            "sensor_bars_per_rig": 3,
            "geometry_policy": "replicated_spatial_context_from_manual_4x10_profile",
            "measurement_policy": "no_2026_parbar_observations_or_illumination_results_claimed",
        },
        "metadata_contract": {
            "genotype_aliases": GENOTYPE_LABELS,
            "source_range_mapping": {str(key): value for key, value in GENOTYPE_BY_RANGE.items()},
            "pedigree": "unknown",
            "relationship_to_BTx623_Pawaga_or_2021": "none_assumed",
            "selection_basis": "provisional_aridity_index_pending_confirmation",
            "calendar_dates_remain_row_level": True,
        },
        "qc_contract": {
            "july21_leaf_width_units": "provisionally_cm_pending_confirmation",
            "suspected_decimal_outliers": "exclude_without_correction",
            "july15_collar_elevation": "subtract_1cm_then_difference_for_internode_length",
            "july21_collar_length": "individual_length_as_recorded",
            "device_angle_transform": "90_minus_abs_y_pending_confirmation",
        },
        "leaf_shape_contract": {
            "midrib_curvature": "unmeasured_neutral_zero_intrinsic_bending",
            "gravity_droop_compliance": 0.02,
            "gravity_policy": "shared_technical_prior_not_height_fitting",
            "tallest_leaf_height": "diagnostic_only_without_measured_curvature",
            "culm_tip_and_mature_collar_heights": "reported_separately_without_unmeasured_targets",
        },
        "validation": {
            "descriptor_population": "leave_one_out_and_bootstrap_intervals_due_to_n5",
            "scene_identity": "60_unique_roots_20_per_genotype_stable_row_column_seed_ids",
            "legacy_regression": "2021_4x10_assets_and_scientific_outputs_exactly_unchanged",
            "visual_comparison": "sanity_check_only_unless_date_matched_reference_photos_are_supplied",
        },
    }


def write_outputs(source_dir: Path, output_dir: Path) -> dict[str, object]:
    sources = load_sources(source_dir)
    normalized = normalize_sources(sources)
    targets = target_tables(normalized)
    contract = validation_contract(sources)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "validation_contract.json").write_text(
        json.dumps(contract, indent=2) + "\n", encoding="utf-8"
    )
    def notes_for(source: SourceWorkbook) -> list[object]:
        try:
            return [cell.value for cell in read_nonempty_cells(source.path, "Sheet2")]
        except ValueError:
            return []

    notes = {source.path.name: notes_for(source) for source in sources.values()}
    source_manifest = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "source_directory": str(source_dir.resolve()),
        "workbooks": [
            {
                "session_id": source.session_id,
                "family": source.family,
                "file_name": source.path.name,
                "sha256": source.sha256,
                "measurement_rows": len(source.rows),
            }
            for source in sources.values()
        ],
        "source_notes": {
            source.path.name: notes[source.path.name]
            for source in sources.values()
            if notes[source.path.name]
        },
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8"
    )
    for name, rows in {**normalized, **targets}.items():
        write_csv(output_dir / f"{name}.csv", rows)
    summary = {
        "plant_rows": len(normalized["plants"]),
        "leaf_rows": len(normalized["leaves"]),
        "internode_rows": len(normalized["internodes"]),
        "tiller_rows": len(normalized["tillers"]),
        "leaf_angle_rows": len(normalized["leaf_angles"]),
        "qc_rows": len(normalized["qc"]),
        "descriptor_targets": len(targets["descriptor_targets"]),
    }
    (output_dir / "normalization_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=repo_root.parent / "sources")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / "Resources"
        / "DigitalAgricultureProject"
        / "Data"
        / "Experiments"
        / EXPERIMENT_ID,
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = write_outputs(args.source_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
