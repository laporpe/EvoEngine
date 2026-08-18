#!/usr/bin/env python3
"""Plant-level measurement validation for the 2026 two-stage 6x10 field.

The canonical six descriptors and two scenes are read-only inputs.  Leave-one-
plant-out descriptors live in a verified scratch directory under the project
assets only while EvoEngine is running and are removed after termination.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from sorghum_2026_6x10_data import EXPERIMENT_ID, repo_root_from_script, sha256, target_tables
from sorghum_2026_6x10_descriptors import (
    DESCRIPTOR_ROOT,
    build_descriptor,
    ensure_asset_folders,
    file_metadata,
)
from sorghum_2026_6x10_validate_descriptors import configure_engine_imports


TABLE_NAMES = ("plants", "leaves", "internodes", "tillers", "leaf_angles")
SCRATCH_RELATIVE = Path(
    "GeneratedAssets/Experiments/Sorghum2026_6x10/ValidationScratch"
)
GENOTYPES = ("GenotypeA", "GenotypeB", "GenotypeC")
SESSIONS = ("MeasurementStage01", "MeasurementStage02")
TRAIT_METADATA = {
    "main_culm_leaf_count": ("plant", "primary", "count"),
    "primary_tiller_count": ("plant", "primary", "count"),
    "leaf_blade_length_m": ("leaf_rank", "primary", "m"),
    "leaf_blade_width_m": ("leaf_rank", "primary", "m"),
    "internode_length_m": ("internode_rank", "primary", "m"),
    "internode_diameter_m": ("internode_rank", "primary", "m"),
    "tallest_leaf_height_m": ("plant", "diagnostic", "m"),
    "main_culm_lean_deg": ("plant", "provisional", "deg"),
    "leaf_insertion_angle_deg": ("leaf_rank", "provisional", "deg"),
    "tiller_insertion_angle_deg": ("tiller", "provisional", "deg"),
}


@dataclass(frozen=True)
class LeaveOneOutFold:
    fold_id: str
    session_id: str
    genotype_id: str
    held_out_plant_id: str
    training_tables: dict[str, list[dict[str, str]]]
    held_out_tables: dict[str, list[dict[str, str]]]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for name in row:
            if name not in fieldnames:
                fieldnames.append(name)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_normalized_tables(data_root: Path) -> dict[str, list[dict[str, str]]]:
    return {name: read_csv(data_root / f"{name}.csv") for name in TABLE_NAMES}


def leave_one_out_folds(
    tables: dict[str, list[dict[str, str]]],
) -> list[LeaveOneOutFold]:
    folds: list[LeaveOneOutFold] = []
    for plant in sorted(
        tables["plants"],
        key=lambda row: (row["session_id"], row["genotype_id"], row["plant_id"]),
    ):
        session_id = plant["session_id"]
        genotype_id = plant["genotype_id"]
        held_out_plant_id = plant["plant_id"]
        group_tables = {
            name: [
                row
                for row in tables[name]
                if row["session_id"] == session_id and row["genotype_id"] == genotype_id
            ]
            for name in TABLE_NAMES
        }
        training = {
            name: [row for row in rows if row.get("plant_id") != held_out_plant_id]
            for name, rows in group_tables.items()
        }
        held_out = {
            name: [row for row in rows if row.get("plant_id") == held_out_plant_id]
            for name, rows in group_tables.items()
        }
        if len(training["plants"]) != 4 or len(held_out["plants"]) != 1:
            raise AssertionError(
                f"{held_out_plant_id} does not form a four-train/one-test fold"
            )
        for name in TABLE_NAMES:
            if any(row.get("plant_id") == held_out_plant_id for row in training[name]):
                raise AssertionError(f"held-out plant leaked into {name}: {held_out_plant_id}")
        folds.append(
            LeaveOneOutFold(
                fold_id=f"{session_id}_{genotype_id}_{held_out_plant_id.rsplit('_', 1)[-1]}",
                session_id=session_id,
                genotype_id=genotype_id,
                held_out_plant_id=held_out_plant_id,
                training_tables=training,
                held_out_tables=held_out,
            )
        )
    return folds


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def empirical_crps(predictions: Sequence[float], observation: float) -> float:
    """Continuous ranked probability score for an empirical predictive sample."""
    if not predictions:
        return math.nan
    ordered = sorted(float(value) for value in predictions)
    count = len(ordered)
    absolute_error = statistics.fmean(abs(value - observation) for value in ordered)
    pairwise_half_expectation = sum(
        (2 * index - count + 1) * value for index, value in enumerate(ordered)
    ) / (count * count)
    return absolute_error - pairwise_half_expectation


def prediction_summary(
    predictions: Sequence[float],
    observation: float,
    expected_count: int,
    magnitude_reference: float,
) -> dict[str, object]:
    values = [float(value) for value in predictions if math.isfinite(float(value))]
    if not values:
        return {
            "prediction_count": 0,
            "prediction_availability_rate": 0.0,
            "predictive_mean": None,
            "predictive_std": None,
            "p05": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "predictive_percentile": None,
            "inside_50_percent_interval": None,
            "inside_90_percent_interval": None,
            "empirical_crps": None,
            "magnitude_normalized_crps": None,
            "magnitude_normalized_median_error": None,
        }
    p05 = quantile(values, 0.05)
    p25 = quantile(values, 0.25)
    p50 = quantile(values, 0.50)
    p75 = quantile(values, 0.75)
    p95 = quantile(values, 0.95)
    crps = empirical_crps(values, observation)
    scale = max(abs(float(magnitude_reference)), 1.0e-9)
    return {
        "prediction_count": len(values),
        "prediction_availability_rate": len(values) / max(expected_count, 1),
        "predictive_mean": statistics.fmean(values),
        "predictive_std": statistics.pstdev(values),
        "p05": p05,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p95": p95,
        "predictive_percentile": sum(value <= observation for value in values) / len(values),
        "inside_50_percent_interval": p25 <= observation <= p75,
        "inside_90_percent_interval": p05 <= observation <= p95,
        "empirical_crps": crps,
        "magnitude_normalized_crps": crps / scale,
        "magnitude_normalized_median_error": abs(observation - p50) / scale,
    }


def stable_seed(*parts: str) -> int:
    text = "|".join(parts)
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "little") & 0x7FFFFFFF


def numeric(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean_numeric(rows: Iterable[dict[str, str]], field: str) -> float | None:
    values = [value for row in rows if (value := numeric(row, field)) is not None]
    return statistics.fmean(values) if values else None


def fold_targets(fold: LeaveOneOutFold) -> dict[str, object]:
    # The normalizer builds targets before CSV serialization, where missing
    # measurements are ``None``.  Restore that representation after reading
    # the persisted CSVs so target construction follows the identical path.
    cleaned_tables = {
        name: [
            {field: (None if value == "" else value) for field, value in row.items()}
            for row in rows
        ]
        for name, rows in fold.training_tables.items()
    }
    targets = target_tables(cleaned_tables)
    return {
        "target": targets["descriptor_targets"][0],
        "leaf_ranks": targets["leaf_rank_targets"],
        "internode_ranks": targets["internode_rank_targets"],
        "leaf_angle_ranks": targets["leaf_angle_rank_targets"],
        "tillers": fold.training_tables["tillers"],
    }


def scratch_path_for(fold: LeaveOneOutFold, suffix: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", fold.fold_id)
    return SCRATCH_RELATIVE / f"{safe}_{suffix}.sorghumls"


def write_descriptor_asset(
    assets_root: Path, relative: Path, text: str
) -> Path:
    output = assets_root / relative
    ensure_asset_folders(output.parent, assets_root)
    output.write_text(text, encoding="utf-8", newline="\n")
    file_metadata(output, assets_root)
    return output


def descriptor_text(
    base_text: str,
    fold: LeaveOneOutFold,
    targets: dict[str, object],
    leaf_length_scale: float,
) -> tuple[str, dict[str, object]]:
    return build_descriptor(
        base_text,
        targets["target"],
        targets["leaf_ranks"],
        targets["internode_ranks"],
        targets["leaf_angle_ranks"],
        targets["tillers"],
        {"leaf_length_scale": leaf_length_scale},
    )


def verified_cleanup_scratch(assets_root: Path) -> None:
    scratch = (assets_root / SCRATCH_RELATIVE).resolve()
    expected = (
        assets_root
        / "GeneratedAssets"
        / "Experiments"
        / EXPERIMENT_ID
        / "ValidationScratch"
    ).resolve()
    if scratch != expected or scratch.name != "ValidationScratch":
        raise RuntimeError(f"refusing to remove unexpected scratch path: {scratch}")
    if scratch.exists():
        shutil.rmtree(scratch)


def canonical_hashes(project_root: Path) -> dict[str, str]:
    paths = list(
        (
            project_root
            / "Assets"
            / "GeneratedAssets"
            / "Experiments"
            / EXPERIMENT_ID
            / "Descriptors"
        ).rglob("*.sorghumls")
    )
    paths.extend(
        (
            project_root
            / "Assets"
            / "GeneratedAssets"
            / "Experiments"
            / EXPERIMENT_ID
            / "Scenes"
        ).glob("*.evescene")
    )
    return {
        path.relative_to(project_root).as_posix(): sha256(path)
        for path in sorted(paths)
    }


def source_hash_regression(data_root: Path) -> dict[str, object]:
    manifest = json.loads((data_root / "source_manifest.json").read_text(encoding="utf-8"))
    rows = []
    for source in manifest["workbooks"]:
        path = Path(manifest["source_directory"]) / source["file_name"]
        actual = sha256(path)
        rows.append(
            {
                "file_name": source["file_name"],
                "expected_sha256": source["sha256"],
                "actual_sha256": actual,
                "exact_match": actual == source["sha256"],
            }
        )
    return {"success": all(row["exact_match"] for row in rows), "sources": rows}


def main_axis(record: object) -> object | None:
    return next((axis for axis in record.axes if int(axis.axis_id) == 0), None)


def prediction_values(
    records: Sequence[object], trait_id: str, organ_rank: int | None
) -> list[float]:
    result: list[float] = []
    for record in records:
        if trait_id == "main_culm_leaf_count":
            result.append(float(record.main_culm_leaf_count))
        elif trait_id == "primary_tiller_count":
            result.append(float(record.primary_tiller_count))
        elif trait_id == "tallest_leaf_height_m":
            result.append(float(record.height_m))
        elif trait_id == "main_culm_lean_deg":
            axis = main_axis(record)
            if axis is not None:
                result.append(float(axis.culm_departure_degrees))
        elif trait_id in {
            "leaf_blade_length_m",
            "leaf_blade_width_m",
            "leaf_insertion_angle_deg",
        }:
            leaf = next(
                (
                    leaf
                    for leaf in record.leaves
                    if int(leaf.axis_id) == 0
                    and int(leaf.rank) + 1 == organ_rank
                    and bool(leaf.alive)
                ),
                None,
            )
            if leaf is None:
                continue
            if trait_id == "leaf_blade_length_m":
                result.append(float(leaf.blade_length_m))
            elif trait_id == "leaf_blade_width_m":
                result.append(float(leaf.blade_width_m))
            else:
                result.append(float(leaf.insertion_angle_degrees))
        elif trait_id in {"internode_length_m", "internode_diameter_m"}:
            internode = next(
                (
                    internode
                    for internode in record.internodes
                    if int(internode.axis_id) == 0 and int(internode.rank) + 1 == organ_rank
                ),
                None,
            )
            if internode is None:
                continue
            result.append(
                float(
                    internode.length_m
                    if trait_id == "internode_length_m"
                    else internode.diameter_m
                )
            )
        elif trait_id == "tiller_insertion_angle_deg":
            angles = [
                float(axis.culm_departure_degrees)
                for axis in record.axes
                if int(axis.axis_id) != 0
            ]
            if angles:
                result.append(statistics.fmean(angles))
        else:
            raise KeyError(trait_id)
    return result


def add_observation(
    rows: list[dict[str, object]],
    fold: LeaveOneOutFold,
    records: Sequence[object],
    trait_id: str,
    observed: float | None,
    organ_rank: int | None,
    source: str,
    magnitude_reference: float | None,
) -> None:
    if observed is None:
        return
    family, role, unit = TRAIT_METADATA[trait_id]
    predictions = prediction_values(records, trait_id, organ_rank)
    reference = magnitude_reference if magnitude_reference not in (None, 0.0) else observed
    summary = prediction_summary(predictions, observed, len(records), float(reference))
    rows.append(
        {
            "fold_id": fold.fold_id,
            "session_id": fold.session_id,
            "genotype_id": fold.genotype_id,
            "held_out_plant_id": fold.held_out_plant_id,
            "trait_id": trait_id,
            "trait_family": family,
            "trait_role": role,
            "unit": unit,
            "organ_rank": organ_rank,
            "observed": observed,
            "magnitude_reference": reference,
            "source": source,
            **summary,
        }
    )


def observations_for_fold(
    fold: LeaveOneOutFold, records: Sequence[object]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    plant = fold.held_out_tables["plants"][0]
    training_plants = fold.training_tables["plants"]
    add_observation(
        rows,
        fold,
        records,
        "main_culm_leaf_count",
        numeric(plant, "leaf_count"),
        None,
        plant["leaf_count_source"],
        mean_numeric(training_plants, "leaf_count"),
    )
    add_observation(
        rows,
        fold,
        records,
        "primary_tiller_count",
        numeric(plant, "tiller_count"),
        None,
        plant["tiller_count_source"],
        mean_numeric(training_plants, "tiller_count"),
    )
    add_observation(
        rows,
        fold,
        records,
        "tallest_leaf_height_m",
        numeric(plant, "height_m"),
        None,
        plant["height_source"],
        mean_numeric(training_plants, "height_m"),
    )
    add_observation(
        rows,
        fold,
        records,
        "main_culm_lean_deg",
        numeric(plant, "main_culm_lean_deg_derived"),
        None,
        plant["source_workbooks"],
        mean_numeric(training_plants, "main_culm_lean_deg_derived"),
    )

    training_leaves = fold.training_tables["leaves"]
    training_angles = fold.training_tables["leaf_angles"]
    for leaf in fold.held_out_tables["leaves"]:
        rank = int(leaf["leaf_rank"])
        peers = [row for row in training_leaves if int(row["leaf_rank"]) == rank]
        add_observation(
            rows,
            fold,
            records,
            "leaf_blade_length_m",
            numeric(leaf, "length_m"),
            rank,
            leaf["length_source"],
            mean_numeric(peers, "length_m"),
        )
        add_observation(
            rows,
            fold,
            records,
            "leaf_blade_width_m",
            numeric(leaf, "width_m"),
            rank,
            leaf["width_source"],
            mean_numeric(peers, "width_m"),
        )
    for angle in fold.held_out_tables["leaf_angles"]:
        rank = int(angle["leaf_rank"])
        peers = [row for row in training_angles if int(row["leaf_rank"]) == rank]
        add_observation(
            rows,
            fold,
            records,
            "leaf_insertion_angle_deg",
            numeric(angle, "insertion_angle_deg_derived"),
            rank,
            angle["source"],
            mean_numeric(peers, "insertion_angle_deg_derived"),
        )

    training_internodes = fold.training_tables["internodes"]
    for internode in fold.held_out_tables["internodes"]:
        rank = int(internode["internode_rank"])
        peers = [
            row for row in training_internodes if int(row["internode_rank"]) == rank
        ]
        add_observation(
            rows,
            fold,
            records,
            "internode_length_m",
            numeric(internode, "internode_length_m"),
            rank,
            internode["length_source"],
            mean_numeric(peers, "internode_length_m"),
        )
        add_observation(
            rows,
            fold,
            records,
            "internode_diameter_m",
            numeric(internode, "effective_diameter_m"),
            rank,
            ";".join(
                filter(
                    None,
                    (
                        internode["diameter_sheath_axis_source"],
                        internode["diameter_perpendicular_source"],
                    ),
                )
            ),
            mean_numeric(peers, "effective_diameter_m"),
        )

    held_tillers = [
        row
        for row in fold.held_out_tables["tillers"]
        if numeric(row, "insertion_angle_deg_derived") is not None
    ]
    training_tillers = fold.training_tables["tillers"]
    if held_tillers:
        add_observation(
            rows,
            fold,
            records,
            "tiller_insertion_angle_deg",
            mean_numeric(held_tillers, "insertion_angle_deg_derived"),
            None,
            ";".join(row["source"] for row in held_tillers),
            mean_numeric(training_tillers, "insertion_angle_deg_derived"),
        )
    return rows


def average(values: Iterable[float | int | bool | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    return statistics.fmean(filtered) if filtered else None


def aggregate_plant_trait_scores(
    observations: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in observations:
        groups[(str(row["fold_id"]), str(row["trait_id"]))].append(row)
    result = []
    for (fold_id, trait_id), rows in sorted(groups.items()):
        squared_errors = [
            (float(row["observed"]) - float(row["p50"])) ** 2
            for row in rows
            if row["p50"] is not None
        ]
        scale = average(row["magnitude_reference"] for row in rows)
        rmse = math.sqrt(statistics.fmean(squared_errors)) if squared_errors else None
        first = rows[0]
        result.append(
            {
                "fold_id": fold_id,
                "session_id": first["session_id"],
                "genotype_id": first["genotype_id"],
                "held_out_plant_id": first["held_out_plant_id"],
                "trait_id": trait_id,
                "trait_family": first["trait_family"],
                "trait_role": first["trait_role"],
                "unit": first["unit"],
                "observation_count": len(rows),
                "mean_prediction_availability_rate": average(
                    row["prediction_availability_rate"] for row in rows
                ),
                "coverage_50": average(row["inside_50_percent_interval"] for row in rows),
                "coverage_90": average(row["inside_90_percent_interval"] for row in rows),
                "mean_predictive_percentile": average(
                    row["predictive_percentile"] for row in rows
                ),
                "mean_empirical_crps": average(row["empirical_crps"] for row in rows),
                "mean_magnitude_normalized_crps": average(
                    row["magnitude_normalized_crps"] for row in rows
                ),
                "mean_magnitude_normalized_median_error": average(
                    row["magnitude_normalized_median_error"] for row in rows
                ),
                "rmse": rmse,
                "magnitude_normalized_rmse": (
                    rmse / max(abs(float(scale)), 1.0e-9)
                    if rmse is not None and scale is not None
                    else None
                ),
            }
        )
    return result


def aggregate_trait_summary(
    plant_scores: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in plant_scores:
        groups[str(row["trait_id"])].append(row)
    result = []
    for trait_id, rows in sorted(groups.items()):
        first = rows[0]
        coverage_90 = average(row["coverage_90"] for row in rows)
        percentile = average(row["mean_predictive_percentile"] for row in rows)
        red_flags = []
        if coverage_90 is not None and coverage_90 < 0.70:
            red_flags.append("coverage90_below_exploratory_guardrail")
        if percentile is not None and not 0.25 <= percentile <= 0.75:
            red_flags.append("predictive_percentile_outside_exploratory_guardrail")
        result.append(
            {
                "trait_id": trait_id,
                "trait_family": first["trait_family"],
                "trait_role": first["trait_role"],
                "unit": first["unit"],
                "held_out_plant_count": len({row["held_out_plant_id"] for row in rows}),
                "plant_trait_score_count": len(rows),
                "mean_observations_per_plant": average(row["observation_count"] for row in rows),
                "mean_prediction_availability_rate": average(
                    row["mean_prediction_availability_rate"] for row in rows
                ),
                "mean_coverage_50": average(row["coverage_50"] for row in rows),
                "mean_coverage_90": coverage_90,
                "mean_predictive_percentile": percentile,
                "mean_magnitude_normalized_crps": average(
                    row["mean_magnitude_normalized_crps"] for row in rows
                ),
                "mean_magnitude_normalized_median_error": average(
                    row["mean_magnitude_normalized_median_error"] for row in rows
                ),
                "mean_magnitude_normalized_rmse": average(
                    row["magnitude_normalized_rmse"] for row in rows
                ),
                "diagnostic_red_flags": ";".join(red_flags),
            }
        )
    return result


def plant_features(tables: dict[str, list[dict[str, str]]]) -> list[dict[str, object]]:
    result = []
    for plant in tables["plants"]:
        plant_id = plant["plant_id"]
        leaves = [row for row in tables["leaves"] if row["plant_id"] == plant_id]
        internodes = [row for row in tables["internodes"] if row["plant_id"] == plant_id]
        angles = [row for row in tables["leaf_angles"] if row["plant_id"] == plant_id]
        result.append(
            {
                "session_id": plant["session_id"],
                "genotype_id": plant["genotype_id"],
                "plant_id": plant_id,
                "main_culm_leaf_count": numeric(plant, "leaf_count"),
                "primary_tiller_count": numeric(plant, "tiller_count"),
                "tallest_leaf_height_m": numeric(plant, "height_m"),
                "mean_leaf_blade_length_m": mean_numeric(leaves, "length_m"),
                "mean_leaf_blade_width_m": mean_numeric(leaves, "width_m"),
                "mean_internode_length_m": mean_numeric(internodes, "internode_length_m"),
                "mean_internode_diameter_m": mean_numeric(internodes, "effective_diameter_m"),
                "mean_leaf_insertion_angle_deg": mean_numeric(
                    angles, "insertion_angle_deg_derived"
                ),
            }
        )
    return result


def hedges_g(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    df = len(left) + len(right) - 2
    pooled_variance = (
        (len(left) - 1) * statistics.variance(left)
        + (len(right) - 1) * statistics.variance(right)
    ) / df
    if pooled_variance <= 0.0:
        return None
    correction = 1.0 - 3.0 / (4.0 * df - 1.0)
    return correction * (statistics.fmean(left) - statistics.fmean(right)) / math.sqrt(
        pooled_variance
    )


def descriptive_genotype_contrasts(
    tables: dict[str, list[dict[str, str]]]
) -> list[dict[str, object]]:
    features = plant_features(tables)
    feature_names = [
        name for name in features[0] if name not in {"session_id", "genotype_id", "plant_id"}
    ]
    rows = []
    for session_id in SESSIONS:
        for left_index, left in enumerate(GENOTYPES):
            for right in GENOTYPES[left_index + 1 :]:
                for feature in feature_names:
                    left_values = [
                        float(row[feature])
                        for row in features
                        if row["session_id"] == session_id
                        and row["genotype_id"] == left
                        and row[feature] is not None
                    ]
                    right_values = [
                        float(row[feature])
                        for row in features
                        if row["session_id"] == session_id
                        and row["genotype_id"] == right
                        and row[feature] is not None
                    ]
                    if not left_values or not right_values:
                        continue
                    rows.append(
                        {
                            "session_id": session_id,
                            "feature": feature,
                            "left_genotype": left,
                            "right_genotype": right,
                            "left_n": len(left_values),
                            "right_n": len(right_values),
                            "left_mean": statistics.fmean(left_values),
                            "right_mean": statistics.fmean(right_values),
                            "raw_difference_left_minus_right": statistics.fmean(left_values)
                            - statistics.fmean(right_values),
                            "hedges_g": hedges_g(left_values, right_values),
                            "inference_policy": "descriptive_only_genotype_confounded_with_plot",
                        }
                    )
    return rows


def scene_typicality(
    data_root: Path,
    prediction_pools: dict[tuple[str, str], Sequence[object]],
    resample_count: int,
) -> list[dict[str, object]]:
    manifest = read_csv(data_root / "scene_manifest.csv")
    metric_fields = {
        "height_mean_m": "plant_height_m",
        "height_std_m": "plant_height_m",
        "leaf_count_mean": "main_culm_leaf_count",
        "leaf_count_std": "main_culm_leaf_count",
        "tiller_count_mean": "primary_tiller_count",
        "tiller_count_std": "primary_tiller_count",
    }
    rows: list[dict[str, object]] = []
    for key, pool in sorted(prediction_pools.items()):
        session_id, genotype_id = key
        scene_group = [
            row
            for row in manifest
            if row["session_id"] == session_id and row["genotype_id"] == genotype_id
        ]
        if len(scene_group) != 20:
            raise AssertionError(f"{key} scene block contains {len(scene_group)} plants")
        pool_values = {
            "plant_height_m": [float(record.height_m) for record in pool],
            "main_culm_leaf_count": [float(record.main_culm_leaf_count) for record in pool],
            "primary_tiller_count": [float(record.primary_tiller_count) for record in pool],
        }
        rng = random.Random(stable_seed(session_id, genotype_id, "scene_typicality"))
        for metric_id, field in metric_fields.items():
            actual_values = [float(row[field]) for row in scene_group]
            actual = (
                statistics.fmean(actual_values)
                if metric_id.endswith("_mean_m") or metric_id.endswith("_mean")
                else statistics.pstdev(actual_values)
            )
            synthetic = []
            for _ in range(resample_count):
                draw = [rng.choice(pool_values[field]) for _ in range(20)]
                synthetic.append(
                    statistics.fmean(draw)
                    if metric_id.endswith("_mean_m") or metric_id.endswith("_mean")
                    else statistics.pstdev(draw)
                )
            percentile = sum(value <= actual for value in synthetic) / len(synthetic)
            rows.append(
                {
                    "session_id": session_id,
                    "genotype_id": genotype_id,
                    "metric_id": metric_id,
                    "scene_plant_count": 20,
                    "descriptor_pool_count": len(pool),
                    "resample_count": resample_count,
                    "observed_scene_value": actual,
                    "synthetic_p05": quantile(synthetic, 0.05),
                    "synthetic_p50": quantile(synthetic, 0.50),
                    "synthetic_p95": quantile(synthetic, 0.95),
                    "scene_percentile": percentile,
                    "tail_flag": percentile < 0.05 or percentile > 0.95,
                    "interpretation": "descriptor_seed_typicality_not_measurement_fit",
                }
            )
    return rows


def photo_category(name: str) -> tuple[str, str]:
    stem = Path(name).stem
    if stem.upper().startswith("IMG_"):
        return "unclassified_original", "qualitative_pending_review"
    lowered = stem.lower()
    if any(token in lowered for token in ("cluster", "height", "internode", "calliper", "curvature", "tiller", "coleoptile")):
        return "scale_or_geometry_reference", "quantitative_candidate_pending_mapping"
    if any(token in lowered for token in ("green", "texture", "margin", "temperature")):
        return "appearance_reference", "qualitative_color_texture"
    return "annotated_field_reference", "qualitative_pending_mapping"


def photo_reference_manifest(photo_root: Path) -> list[dict[str, object]]:
    files = sorted(path for path in photo_root.rglob("*") if path.is_file())
    rows = []
    for path in files:
        match = re.search(r"(\d+)(?:\s+\d+)?$", path.stem)
        capture_id = match.group(1) if match else ""
        category, readiness = photo_category(path.name)
        rows.append(
            {
                "file_name": path.name,
                "relative_path": path.relative_to(photo_root).as_posix(),
                "extension": path.suffix.lower(),
                "file_size_bytes": path.stat().st_size,
                "filesystem_last_write": path.stat().st_mtime,
                "capture_id_from_name": capture_id,
                "reference_category": category,
                "quantitative_readiness": readiness,
                "measurement_date_match": "not_established",
                "plant_genotype_plot_mapping": "not_established",
                "current_use": "visual_truth_color_site_and_morphology_context",
            }
        )
    return rows


def create_figures(
    output_dir: Path,
    observations: Sequence[dict[str, object]],
    trait_summary: Sequence[dict[str, object]],
    scene_rows: Sequence[dict[str, object]],
) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    ordered = sorted(
        trait_summary,
        key=lambda row: (str(row["trait_role"]), str(row["trait_id"])),
    )
    labels = [str(row["trait_id"]).replace("_", " ") for row in ordered]
    coverage = [float(row["mean_coverage_90"] or 0.0) for row in ordered]
    errors = [
        float(row["mean_magnitude_normalized_median_error"] or 0.0) for row in ordered
    ]
    colors = [
        "#2878B5" if row["trait_role"] == "primary" else "#D97A2B"
        for row in ordered
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6), constrained_layout=True)
    positions = list(range(len(ordered)))
    axes[0].barh(positions, coverage, color=colors)
    axes[0].axvline(0.90, color="#333333", linestyle="--", linewidth=1, label="nominal 90%")
    axes[0].axvline(0.70, color="#B22222", linestyle=":", linewidth=1, label="red-flag guardrail")
    axes[0].set(yticks=positions, yticklabels=labels, xlim=(0, 1), xlabel="Mean held-out coverage")
    axes[0].invert_yaxis()
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].set_title("Held-out 90% predictive coverage")
    axes[1].barh(positions, errors, color=colors)
    axes[1].set(yticks=positions, yticklabels=[], xlabel="|observed - median| / training magnitude")
    axes[1].invert_yaxis()
    axes[1].set_title("Magnitude-normalized median error")
    figure = output_dir / "loo_trait_summary.png"
    fig.savefig(figure, dpi=220)
    plt.close(fig)
    created.append(figure.name)

    primary_traits = [
        "main_culm_leaf_count",
        "primary_tiller_count",
        "leaf_blade_length_m",
        "leaf_blade_width_m",
        "internode_length_m",
        "internode_diameter_m",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.5), constrained_layout=True)
    for axis, trait_id in zip(axes.flat, primary_traits):
        rows = [row for row in observations if row["trait_id"] == trait_id and row["p50"] is not None]
        observed = [float(row["observed"]) for row in rows]
        medians = [float(row["p50"]) for row in rows]
        lows = [float(row["p05"]) for row in rows]
        highs = [float(row["p95"]) for row in rows]
        axis.errorbar(
            observed,
            medians,
            yerr=[
                [median - low for median, low in zip(medians, lows)],
                [high - median for high, median in zip(highs, medians)],
            ],
            fmt="o",
            markersize=3,
            alpha=0.55,
            color="#2878B5",
            ecolor="#9EC4DE",
            linewidth=0.6,
        )
        if observed and medians:
            lower = min(observed + lows)
            upper = max(observed + highs)
            axis.plot([lower, upper], [lower, upper], color="#333333", linestyle="--", linewidth=0.8)
        axis.set_title(trait_id.replace("_", " "), fontsize=9)
        axis.set_xlabel("Measured")
        axis.set_ylabel("LOO predictive median (90% interval)")
    figure = output_dir / "loo_measured_vs_predicted.png"
    fig.savefig(figure, dpi=220)
    plt.close(fig)
    created.append(figure.name)

    fig, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
    labels = [
        f"{row['session_id'].replace('MeasurementStage', 'S')} {row['genotype_id'].replace('Genotype', '')} {row['metric_id']}"
        for row in scene_rows
    ]
    values = [float(row["scene_percentile"]) for row in scene_rows]
    colors = ["#B22222" if row["tail_flag"] else "#2878B5" for row in scene_rows]
    positions = list(range(len(scene_rows)))
    axis.scatter(values, positions, c=colors, s=24)
    axis.axvspan(0.05, 0.95, color="#DCEAF4", alpha=0.6)
    axis.axvline(0.5, color="#333333", linestyle="--", linewidth=0.8)
    axis.set(xlim=(0, 1), yticks=positions, yticklabels=labels, xlabel="Saved block percentile in 20-plant descriptor resamples")
    axis.invert_yaxis()
    axis.set_title("Persisted 6x10 block typicality (not measurement fit)")
    axis.tick_params(axis="y", labelsize=6)
    figure = output_dir / "scene_typicality.png"
    fig.savefig(figure, dpi=220)
    plt.close(fig)
    created.append(figure.name)
    return created


def run_engine_validation(args: argparse.Namespace) -> dict[str, object]:
    tables = load_normalized_tables(args.data_root)
    folds = leave_one_out_folds(tables)
    base_text = args.base_descriptor.read_text(encoding="utf-8")
    assets_root = args.project_root / "Assets"
    verified_cleanup_scratch(assets_root)
    fold_inputs: dict[str, dict[str, object]] = {}
    for fold in folds:
        targets = fold_targets(fold)
        text, parameters = descriptor_text(base_text, fold, targets, 1.0)
        relative = scratch_path_for(fold, "raw")
        write_descriptor_asset(assets_root, relative, text)
        fold_inputs[fold.fold_id] = {
            "targets": targets,
            "raw_relative": relative,
            "raw_parameters": parameters,
        }

    before_hashes = canonical_hashes(args.project_root)
    project_bytes = args.project.read_bytes()
    source_regression = source_hash_regression(args.data_root)
    observations: list[dict[str, object]] = []
    fold_reports: list[dict[str, object]] = []
    prediction_pools: dict[tuple[str, str], Sequence[object]] = {}
    configure_engine_imports(args.build_dir, args.config)
    import PyDigitalAgriculture as evo

    try:
        if not evo.RunLSystemSorghumProject(
            args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene
        ):
            raise RuntimeError("failed to start EvoEngine measurement-validation scene")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError("measurement-validation scene did not become idle")

        for index, fold in enumerate(folds, start=1):
            inputs = fold_inputs[fold.fold_id]
            raw_records = list(
                evo.SampleSorghumLsDescriptorAssetPhenotypes(
                    inputs["raw_relative"],
                    args.calibration_sample_count,
                    stable_seed(fold.fold_id, "calibration"),
                    True,
                    True,
                    -1.0,
                )
            )
            if len(raw_records) != args.calibration_sample_count:
                raise RuntimeError(f"{fold.fold_id} calibration sample count mismatch")
            training_leaf_max = max(
                float(row["length_m_mean"])
                for row in inputs["targets"]["leaf_ranks"]
                if row["length_m_mean"] is not None
            )
            sampled_max = statistics.fmean(
                float(record.main_culm_max_target_blade_length_m)
                for record in raw_records
            )
            leaf_scale = training_leaf_max / sampled_max if sampled_max > 0.0 else 1.0
            calibrated_text, calibrated_parameters = descriptor_text(
                base_text, fold, inputs["targets"], leaf_scale
            )
            calibrated_relative = scratch_path_for(fold, "calibrated")
            write_descriptor_asset(assets_root, calibrated_relative, calibrated_text)
            records = list(
                evo.SampleSorghumLsDescriptorAssetPhenotypes(
                    calibrated_relative,
                    args.prediction_sample_count,
                    stable_seed(fold.fold_id, "prediction"),
                    True,
                    True,
                    -1.0,
                )
            )
            if len(records) != args.prediction_sample_count:
                raise RuntimeError(f"{fold.fold_id} prediction sample count mismatch")
            fold_rows = observations_for_fold(fold, records)
            observations.extend(fold_rows)
            fold_reports.append(
                {
                    "fold_id": fold.fold_id,
                    "session_id": fold.session_id,
                    "genotype_id": fold.genotype_id,
                    "held_out_plant_id": fold.held_out_plant_id,
                    "training_plant_count": 4,
                    "calibration_sample_count": args.calibration_sample_count,
                    "prediction_sample_count": args.prediction_sample_count,
                    "leaf_length_scale_from_training_only": leaf_scale,
                    "observation_count": len(fold_rows),
                    "descriptor_parameters": calibrated_parameters,
                }
            )
            print(
                json.dumps(
                    {
                        "phase": "leave_one_out",
                        "completed": index,
                        "total": len(folds),
                        "fold_id": fold.fold_id,
                    }
                ),
                flush=True,
            )

        build_report = json.loads(
            (args.data_root / "descriptor_build_report.json").read_text(encoding="utf-8")
        )
        for descriptor in build_report["descriptors"]:
            key = (str(descriptor["session_id"]), str(descriptor["genotype_id"]))
            prediction_pools[key] = list(
                evo.SampleSorghumLsDescriptorAssetPhenotypes(
                    Path(descriptor["descriptor_asset_path"]),
                    args.scene_pool_sample_count,
                    stable_seed(*key, "scene_pool"),
                    True,
                    False,
                    -1.0,
                )
            )
            if len(prediction_pools[key]) != args.scene_pool_sample_count:
                raise RuntimeError(f"{key} scene descriptor pool count mismatch")
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)
        verified_cleanup_scratch(assets_root)

    after_hashes = canonical_hashes(args.project_root)
    if before_hashes != after_hashes:
        raise AssertionError("canonical 2026 descriptor or scene changed during validation")
    if args.project.read_bytes() != project_bytes:
        raise AssertionError("project manifest was not restored byte-for-byte")
    if not source_regression["success"]:
        raise AssertionError("one or more source workbooks changed")

    plant_scores = aggregate_plant_trait_scores(observations)
    trait_summary = aggregate_trait_summary(plant_scores)
    scene_rows = scene_typicality(
        args.data_root, prediction_pools, args.scene_resample_count
    )
    contrasts = descriptive_genotype_contrasts(tables)
    photos = photo_reference_manifest(args.photo_root)
    figure_names = create_figures(
        args.figure_dir, observations, trait_summary, scene_rows
    )

    write_csv(args.data_root / "loo_observations.csv", observations)
    write_csv(args.data_root / "loo_plant_trait_scores.csv", plant_scores)
    write_csv(args.data_root / "loo_trait_summary.csv", trait_summary)
    write_csv(args.data_root / "scene_typicality.csv", scene_rows)
    write_csv(args.data_root / "genotype_contrasts.csv", contrasts)
    write_csv(args.data_root / "photo_reference_manifest.csv", photos)
    regression = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "success": True,
        "source_workbooks": source_regression,
        "canonical_2026_file_count": len(before_hashes),
        "canonical_2026_hashes_before": before_hashes,
        "canonical_2026_hashes_after": after_hashes,
        "canonical_2026_exact_match": before_hashes == after_hashes,
        "project_manifest_byte_exact": args.project.read_bytes() == project_bytes,
        "scratch_removed": not (assets_root / SCRATCH_RELATIVE).exists(),
    }
    (args.data_root / "measurement_validation_regression.json").write_text(
        json.dumps(regression, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "analysis_id": "plant_level_leave_one_out_v1",
        "status": "complete",
        "source_workbook_count": 6,
        "measurement_stage_count": 2,
        "genotype_count": 3,
        "measured_plant_count": len(tables["plants"]),
        "leave_one_out_fold_count": len(folds),
        "training_plants_per_fold": 4,
        "prediction_sample_count_per_fold": args.prediction_sample_count,
        "observation_count": len(observations),
        "plant_trait_score_count": len(plant_scores),
        "trait_summary": trait_summary,
        "scene_typicality_row_count": len(scene_rows),
        "scene_tail_flag_count": sum(bool(row["tail_flag"]) for row in scene_rows),
        "descriptive_genotype_contrast_count": len(contrasts),
        "photo_reference_file_count": len(photos),
        "photo_extension_counts": {
            extension: sum(row["extension"] == extension for row in photos)
            for extension in sorted({str(row["extension"]) for row in photos})
        },
        "figure_files": figure_names,
        "folds": fold_reports,
        "regression": regression,
        "claim": "Descriptor populations are evaluated for representation of measured within-plot sample distributions; leave-one-plant-out results are robustness evidence, not independent external validation.",
        "limitations": [
            "Five sampled plants per genotype-stage group produce wide uncertainty.",
            "Each genotype-stage group has one source plot, so genotype and plot effects are confounded.",
            "July 21 leaf-width units and device-angle transformations remain provisional.",
            "Tallest-leaf height is diagnostic because leaf midrib curvature was not recorded in the workbooks.",
            "July 9 photographs are not numerically date- or plant-matched to the July 15/16 and July 21 measurement tables.",
        ],
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    data_root = project_root / "Data" / "Experiments" / EXPERIMENT_ID
    default_build = repo_root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=default_build)
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument(
        "--runtime-package-dir",
        type=Path,
        default=default_build / "EvoEngine_App" / "RelWithDebInfo" / "Packages",
    )
    parser.add_argument(
        "--base-scene",
        type=Path,
        default=Path("ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene"),
    )
    parser.add_argument("--data-root", type=Path, default=data_root)
    parser.add_argument(
        "--base-descriptor",
        type=Path,
        default=project_root / "Assets" / "ManualAssets" / "Descriptors" / "BTX.sorghumls",
    )
    parser.add_argument(
        "--photo-root",
        type=Path,
        default=Path(r"C:\Users\penan\Downloads\Photos-2026-07-09"),
    )
    parser.add_argument(
        "--figure-dir", type=Path, default=data_root / "measurement_validation_figures"
    )
    parser.add_argument(
        "--report", type=Path, default=data_root / "measurement_validation_report.json"
    )
    parser.add_argument("--calibration-sample-count", type=int, default=256)
    parser.add_argument("--prediction-sample-count", type=int, default=512)
    parser.add_argument("--scene-pool-sample-count", type=int, default=2048)
    parser.add_argument("--scene-resample-count", type=int, default=5000)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    for name in (
        "build_dir",
        "project_root",
        "project",
        "runtime_package_dir",
        "data_root",
        "base_descriptor",
        "photo_root",
        "figure_dir",
        "report",
    ):
        setattr(args, name, getattr(args, name).resolve())
    args.data_root.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    report = run_engine_validation(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "folds": report["leave_one_out_fold_count"],
                "observations": report["observation_count"],
                "scene_tail_flags": report["scene_tail_flag_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
