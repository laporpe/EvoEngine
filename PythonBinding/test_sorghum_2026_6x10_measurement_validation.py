from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sorghum_2026_6x10_data import EXPERIMENT_ID  # noqa: E402
from sorghum_2026_6x10_measurement_validation import (  # noqa: E402
    TABLE_NAMES,
    empirical_crps,
    leave_one_out_folds,
    load_normalized_tables,
    prediction_summary,
)


REPO_ROOT = SCRIPT_DIR.parent
DATA_ROOT = (
    REPO_ROOT
    / "Resources"
    / "DigitalAgricultureProject"
    / "Data"
    / "Experiments"
    / EXPERIMENT_ID
)


def test_contract_freezes_plant_level_design() -> None:
    contract = json.loads((DATA_ROOT / "measurement_validation_contract.json").read_text(encoding="utf-8"))
    assert contract["design"]["leave_one_out_fold_count"] == 30
    assert contract["design"]["training_plants_per_fold"] == 4
    assert contract["design"]["resampling_unit"] == "plant"
    assert contract["design"]["organ_rows_are_independent_replicates"] is False
    assert contract["aggregation"]["single_composite_fidelity_score"] is False


def test_leave_one_out_folds_have_no_plant_leakage() -> None:
    tables = load_normalized_tables(DATA_ROOT)
    folds = leave_one_out_folds(tables)
    assert len(folds) == 30
    assert {fold.held_out_plant_id for fold in folds} == {
        row["plant_id"] for row in tables["plants"]
    }
    for fold in folds:
        assert len(fold.training_tables["plants"]) == 4
        for table_name in TABLE_NAMES:
            assert all(
                row.get("plant_id") != fold.held_out_plant_id
                for row in fold.training_tables[table_name]
            )
        assert {
            row["session_id"] for row in fold.training_tables["plants"]
        } == {fold.session_id}
        assert {
            row["genotype_id"] for row in fold.training_tables["plants"]
        } == {fold.genotype_id}


def test_empirical_prediction_metrics_are_deterministic() -> None:
    predictions = [1.0, 2.0, 3.0, 4.0]
    assert empirical_crps(predictions, 2.5) == 0.375
    summary = prediction_summary(predictions, 2.5, 4, 10.0)
    assert summary["prediction_count"] == 4
    assert summary["prediction_availability_rate"] == 1.0
    assert summary["predictive_percentile"] == 0.5
    assert summary["inside_50_percent_interval"] is True
    assert summary["inside_90_percent_interval"] is True
    assert summary["magnitude_normalized_median_error"] == 0.0


def test_published_measurement_validation_report_is_complete() -> None:
    report = json.loads(
        (DATA_ROOT / "measurement_validation_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "complete"
    assert report["measured_plant_count"] == 30
    assert report["leave_one_out_fold_count"] == 30
    assert report["training_plants_per_fold"] == 4
    assert report["prediction_sample_count_per_fold"] == 512
    assert report["observation_count"] == 1647
    assert report["plant_trait_score_count"] == 298
    assert report["scene_typicality_row_count"] == 36
    assert report["scene_tail_flag_count"] == 4
    assert report["photo_reference_file_count"] == 138
    assert report["photo_extension_counts"] == {".heic": 68, ".png": 70}
    assert {row["trait_id"] for row in report["trait_summary"]} == {
        "internode_diameter_m",
        "internode_length_m",
        "leaf_blade_length_m",
        "leaf_blade_width_m",
        "leaf_insertion_angle_deg",
        "main_culm_leaf_count",
        "main_culm_lean_deg",
        "primary_tiller_count",
        "tallest_leaf_height_m",
        "tiller_insertion_angle_deg",
    }
    assert "not independent external validation" in report["claim"]


def test_measurement_validation_preserves_scientific_inputs() -> None:
    regression = json.loads(
        (DATA_ROOT / "measurement_validation_regression.json").read_text(encoding="utf-8")
    )
    assert regression["success"] is True
    assert regression["source_workbooks"]["success"] is True
    assert all(
        row["exact_match"] for row in regression["source_workbooks"]["sources"]
    )
    assert regression["canonical_2026_file_count"] == 8
    assert regression["canonical_2026_exact_match"] is True
    assert regression["project_manifest_byte_exact"] is True
    assert regression["scratch_removed"] is True
