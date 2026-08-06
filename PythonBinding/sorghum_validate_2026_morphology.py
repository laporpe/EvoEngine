#!/usr/bin/env python3
"""Compare generated sorghum phenotypes with the unknown-genotype 2026 reference state."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import fmean

from sorghum_lsystem_calibrate_date_cultivar_descriptors import configure_engine_imports, summarize_records


EARLY_REFERENCE = {
    "main_culm_leaf_mean": 12.133,
    "whole_plant_height_mean_m": 0.631,
    "max_blade_length_mean_m": 0.607,
    "max_blade_width_mean_m": 0.0797,
    "mature_collar_height_ratio_mean": 0.418,
    "tiller_count_mean": 2.667,
    "tiller_leaf_ratio_mean": 0.699,
    "main_culm_departure_mean_degrees": 6.8,
    "tiller_culm_departure_mean_degrees": 18.2,
    "leaf_sheath_cross_section_ratio": 1.40,
}
REFERENCE_RANK_PROFILE = {
    0.0: {"length_fraction": 0.366, "width_fraction": 0.228},
    0.1: {"length_fraction": 0.426, "width_fraction": 0.307},
    0.2: {"length_fraction": 0.504, "width_fraction": 0.387},
    0.3: {"length_fraction": 0.635, "width_fraction": 0.453},
    0.4: {"length_fraction": 0.742, "width_fraction": 0.548},
    0.5: {"length_fraction": 0.863, "width_fraction": 0.664},
    0.6: {"length_fraction": 0.952, "width_fraction": 0.773},
    0.7: {"length_fraction": 0.925, "width_fraction": 0.914},
    0.8: {"length_fraction": 0.800, "width_fraction": 0.972},
}
SOURCE_WORKBOOKS = (
    "Resources/00_MySorghumProjectResources/2026-07-15-LEAVES_gsheet.xlsx",
    "Resources/00_MySorghumProjectResources/2026-07-15-INTERNODES_gsheet.xlsx",
    "Resources/00_MySorghumProjectResources/2026-07-15-ANGLES-TILLERS_gsheet.xlsx",
)


def repo_root_from_script() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CMakeLists.txt").exists() and (parent / "Resources" / "DigitalAgricultureProject").exists():
            return parent
    raise RuntimeError("could not locate repository root")


def read_early_2021_targets(path: Path) -> dict[str, dict[str, float]]:
    targets: dict[str, dict[str, float]] = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row["date"] != "2021-07-01" or row["cultivar"] in targets:
                continue
            targets[row["cultivar"]] = {
                "leaf_mean": float(row["target_leaf_mean"]),
                "height_mean_m": float(row["target_height_mean_m"]),
                "height_std_m": float(row["target_height_std_m"]),
            }
    if set(targets) != {"BTX", "Pawaga"}:
        raise RuntimeError(f"missing 2021-07-01 targets in {path}")
    return targets


def nearest_rank_bin(value: float) -> float:
    return min(REFERENCE_RANK_PROFILE, key=lambda point: abs(point - value))


def summarize_rank_profile(records: list[object]) -> list[dict[str, float | int]]:
    bins: dict[float, list[object]] = {point: [] for point in REFERENCE_RANK_PROFILE}
    for record in records:
        main_leaves = [leaf for leaf in record.leaves if int(leaf.axis_id) == 0 and bool(leaf.alive)]
        max_length = max((float(leaf.target_blade_length_m) for leaf in main_leaves), default=0.0)
        max_width = max((float(leaf.target_blade_width_m) for leaf in main_leaves), default=0.0)
        for leaf in main_leaves:
            point = nearest_rank_bin(float(leaf.normalized_rank))
            bins[point].append(
                (
                    float(leaf.blade_length_m) / max_length if max_length else 0.0,
                    float(leaf.target_blade_length_m) / max_length if max_length else 0.0,
                    float(leaf.blade_width_m) / max_width if max_width else 0.0,
                    float(leaf.target_blade_width_m) / max_width if max_width else 0.0,
                    float(leaf.growth_progress),
                    float(getattr(leaf, "collar_height_m", 0.0)),
                    float(getattr(leaf, "maximum_height_m", 0.0)),
                    float(getattr(leaf, "tip_height_m", 0.0)),
                    float(getattr(leaf, "chord_elevation_degrees", 0.0)),
                    float(getattr(leaf, "distal_elevation_degrees", 0.0)),
                )
            )
    rows = []
    for point, values in bins.items():
        reference = REFERENCE_RANK_PROFILE[point]
        rows.append(
            {
                "normalized_rank": point,
                "sample_count": len(values),
                "reference_length_fraction": reference["length_fraction"],
                "model_realized_length_fraction": fmean(value[0] for value in values) if values else 0.0,
                "model_target_length_fraction": fmean(value[1] for value in values) if values else 0.0,
                "reference_width_fraction": reference["width_fraction"],
                "model_realized_width_fraction": fmean(value[2] for value in values) if values else 0.0,
                "model_target_width_fraction": fmean(value[3] for value in values) if values else 0.0,
                "model_growth_progress": fmean(value[4] for value in values) if values else 0.0,
                "model_collar_height_mean_m": fmean(value[5] for value in values) if values else 0.0,
                "model_maximum_height_mean_m": fmean(value[6] for value in values) if values else 0.0,
                "model_tip_height_mean_m": fmean(value[7] for value in values) if values else 0.0,
                "model_chord_elevation_mean_degrees": fmean(value[8] for value in values) if values else 0.0,
                "model_distal_elevation_mean_degrees": fmean(value[9] for value in values) if values else 0.0,
            }
        )
    return rows


def comparison(metrics: dict[str, float | int], target: dict[str, float]) -> dict[str, object]:
    model = {
        "main_culm_leaf_mean": float(metrics["leaf_mean"]),
        "whole_plant_height_mean_m": float(metrics["height_mean_m"]),
        "max_blade_length_mean_m": float(metrics["main_culm_max_blade_length_mean_m"]),
        "max_target_blade_length_mean_m": float(metrics["main_culm_max_target_blade_length_mean_m"]),
        "max_blade_width_mean_m": float(metrics["main_culm_max_blade_width_mean_m"]),
        "max_target_blade_width_mean_m": float(metrics["main_culm_max_target_blade_width_mean_m"]),
        "culm_tip_height_ratio_mean": float(metrics["main_culm_tip_height_ratio_mean"]),
        "mature_collar_height_ratio_mean": float(metrics["main_culm_mature_collar_height_ratio_mean"]),
        "tiller_count_mean": float(metrics["tiller_count_mean"]),
        "tiller_leaf_ratio_mean": float(metrics["tiller_leaf_ratio_mean"]),
        "main_culm_departure_mean_degrees": float(metrics["main_culm_departure_mean_degrees"]),
        "tiller_culm_departure_mean_degrees": float(metrics["tiller_culm_departure_mean_degrees"]),
        "tiller_origin_height_max_m": float(metrics["tiller_origin_height_max_m"]),
    }
    return {
        "mandatory_2021": {
            "target": target,
            "model": {"leaf_mean": model["main_culm_leaf_mean"], "height_mean_m": model["whole_plant_height_mean_m"]},
            "relative_error": {
                "leaf_mean": abs(model["main_culm_leaf_mean"] - target["leaf_mean"]) / target["leaf_mean"],
                "height_mean_m": abs(model["whole_plant_height_mean_m"] - target["height_mean_m"])
                / target["height_mean_m"],
            },
        },
        "model": model,
        "unknown_genotype_2026_reference": EARLY_REFERENCE,
        "reference_ratios": {
            key: model[key] / value if value else 0.0
            for key, value in EARLY_REFERENCE.items()
            if key in model
        },
    }


def parser() -> argparse.ArgumentParser:
    root = repo_root_from_script()
    build = root / "out" / "build" / "vs2026-x64"
    project = root / "Resources" / "DigitalAgricultureProject"
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo-root", type=Path, default=root)
    result.add_argument("--build-dir", type=Path, default=build)
    result.add_argument("--config", default="Release")
    result.add_argument("--runtime-package-dir", type=Path, default=build / "EvoEngine_App" / "Release" / "Packages")
    result.add_argument("--project", type=Path, default=project / "test_lsystem_sorghum.eveproj")
    result.add_argument("--base-scene", default="ManualAssets/Scenes/Sorghum_4x10_Template.evescene")
    result.add_argument(
        "--target-report", type=Path, default=project / "Assets" / "GeneratedAssets" / "Reports" / "post_tiller_scene_validation.csv"
    )
    result.add_argument("--sample-count", type=int, default=1000)
    result.add_argument("--seed", type=int, default=720260715)
    result.add_argument("--finalize-snapshot", action="store_true")
    result.add_argument("--output", type=Path, default=project / "Assets" / "GeneratedAssets" / "Reports" / "morphology_2026_comparison.json")
    return result


def run(args: argparse.Namespace) -> dict[str, object]:
    targets = read_early_2021_targets(args.target_report)
    configure_engine_imports(args.repo_root.resolve(), args.build_dir.resolve(), args.config)
    import PyDigitalAgriculture as evo  # type: ignore

    project_bytes = args.project.read_bytes()
    if not evo.RunLSystemSorghumProject(args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene, False):
        raise RuntimeError("failed to start morphology validation scene")
    if not evo.WaitForProjectIdle(240):
        raise RuntimeError("project did not become idle")
    try:
        cultivars = {}
        for index, cultivar in enumerate(("BTX", "Pawaga")):
            descriptor = f"GeneratedAssets/Descriptors/GrowthStage01/{cultivar}.sorghumls"
            records = evo.SampleSorghumLsDescriptorAssetPhenotypes(
                descriptor, args.sample_count, args.seed + index * 100000, args.finalize_snapshot, True
            )
            metrics = summarize_records(records, args.sample_count)
            cultivars[cultivar] = {
                "descriptor": descriptor,
                "metrics": metrics,
                "comparison": comparison(metrics, targets[cultivar]),
                "rank_profile": summarize_rank_profile(records),
            }
        result = {
            "schema_version": 1,
            "interpretation": (
                "The 2021 leaf-count and height targets are mandatory. The unknown-genotype 2026 values are "
                "diagnostic priors, strongest for GrowthStage01, and are not pass/fail cultivar targets."
            ),
            "finalize_snapshot": args.finalize_snapshot,
            "sample_count_per_cultivar": args.sample_count,
            "source_workbooks": SOURCE_WORKBOOKS,
            "cultivars": cultivars,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)


def main() -> None:
    args = parser().parse_args()
    result = run(args)
    for cultivar, data in result["cultivars"].items():
        comparison_data = data["comparison"]
        model = comparison_data["model"]
        errors = comparison_data["mandatory_2021"]["relative_error"]
        print(
            f"{cultivar}: leaves={model['main_culm_leaf_mean']:.3f} "
            f"height={model['whole_plant_height_mean_m']:.3f}m "
            f"2021-errors=({errors['leaf_mean']:.2%}, {errors['height_mean_m']:.2%}) "
            f"blade={model['max_blade_length_mean_m']:.3f}m x {model['max_blade_width_mean_m']:.3f}m "
            f"collar/height={model['mature_collar_height_ratio_mean']:.3f} "
            f"tillers={model['tiller_count_mean']:.2f} @ {model['tiller_leaf_ratio_mean']:.3f} leaves/main"
        )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
