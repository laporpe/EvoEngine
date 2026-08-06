#!/usr/bin/env python3
"""Fit culm length without changing authored sorghum leaf dimensions."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml

from sorghum_lsystem_calibrate_date_cultivar_descriptors import configure_engine_imports, repo_root_from_script
from sorghum_validate_2026_morphology import summarize_records


STAGE_DATE = {
    "GrowthStage01": "2021-07-01",
    "GrowthStage02": "2021-07-14",
    "GrowthStage03": "2021-08-18",
    "GrowthStage04": "2021-08-30",
    "GrowthStage05": "2021-09-02",
}
def targets(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {
            (row["date"], row["cultivar"]): {
                "height_mean_m": float(row["target_height_mean_m"]),
                "height_std_m": float(row["target_height_std_m"]),
            }
            for row in csv.DictReader(source)
        }


def descriptor_leaf_budget(path: Path) -> tuple[float, float]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))["total_phytomer_count"]
    return float(value["mean"]), float(value["deviation"])


def sample(
    evo,
    asset_path: str,
    leaf_mean: float,
    leaf_deviation: float,
    mean_scale: float,
    deviation_scale: float,
    gravity_compliance: float,
    count: int,
    seed: int,
):
    records = evo.SampleSorghumLsDescriptorPhenotypes(
        asset_path,
        leaf_mean,
        leaf_deviation,
        mean_scale,
        deviation_scale,
        count,
        seed,
        1.0,
        0.0,
        0.90,
        0.90,
        False,
        False,
        1.0,
        deviation_scale,
        gravity_compliance,
    )
    return summarize_records(records, count)


def fit_scale(
    evaluate,
    target: float,
    low: float = 0.2,
    high: float = 3.0,
    iterations: int = 8,
    metric: str = "height_mean_m",
):
    candidates = [(low, evaluate(low)), (high, evaluate(high))]
    for _ in range(iterations):
        middle = (low + high) * 0.5
        metrics = evaluate(middle)
        candidates.append((middle, metrics))
        if metrics[metric] < target:
            low = middle
        else:
            high = middle
    return min(candidates, key=lambda item: abs(item[1][metric] - target))


def score(metrics: dict[str, float], target: dict[str, float]) -> float:
    height_error = (metrics["height_mean_m"] - target["height_mean_m"]) / target["height_mean_m"]
    height_std_error = (metrics["height_std_m"] - target["height_std_m"]) / target["height_std_m"]
    return (height_error / 0.02) ** 2 + (height_std_error / 0.15) ** 2


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
        "--target-report",
        type=Path,
        default=project / "Assets" / "GeneratedAssets" / "Reports" / "post_tiller_scene_validation.csv",
    )
    result.add_argument("--sample-count", type=int, default=100)
    result.add_argument("--seed", type=int, default=720260718)
    result.add_argument("--stage", action="append", choices=tuple(STAGE_DATE))
    result.add_argument("--gravity-compliance", type=float, action="append")
    result.add_argument("--apply", action="store_true")
    result.add_argument("--validate-only", action="store_true")
    result.add_argument(
        "--output",
        type=Path,
        default=project / "Assets" / "GeneratedAssets" / "Reports" / "morphology_allocation_calibration.json",
    )
    return result


def run(args: argparse.Namespace) -> dict[str, object]:
    configure_engine_imports(args.repo_root.resolve(), args.build_dir.resolve(), args.config)
    import PyDigitalAgriculture as evo  # type: ignore

    target_values = targets(args.target_report)
    assets = args.project.resolve().parent / "Assets"
    stages = args.stage or list(STAGE_DATE)
    project_bytes = args.project.read_bytes()
    if not evo.RunLSystemSorghumProject(args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene, False):
        raise RuntimeError("failed to start morphology calibration scene")
    if not evo.WaitForProjectIdle(240):
        raise RuntimeError("project did not become idle")
    try:
        results = []
        for stage in stages:
            stage_index = list(STAGE_DATE).index(stage)
            for cultivar_index, cultivar in enumerate(("BTX", "Pawaga")):
                relative = f"GeneratedAssets/Descriptors/{stage}/{cultivar}.sorghumls"
                leaf_mean, leaf_deviation = descriptor_leaf_budget(assets / relative)
                target = target_values[(STAGE_DATE[stage], cultivar)]
                seed = args.seed + stage_index * 100000 + cultivar_index * 10000
                cache = {}

                def evaluate(mean_scale: float, deviation_scale: float, gravity: float):
                    key = round(mean_scale, 8), round(deviation_scale, 8), gravity
                    if key not in cache:
                        cache[key] = sample(
                            evo,
                            relative,
                            leaf_mean,
                            leaf_deviation,
                            mean_scale,
                            deviation_scale,
                            gravity,
                            args.sample_count,
                            seed,
                        )
                    return cache[key]

                trials = []
                for gravity in args.gravity_compliance or (1.0,):
                    if args.validate_only:
                        mean_scale, deviation_scale, metrics = 1.0, 1.0, evaluate(1.0, 1.0, gravity)
                        candidates = ((mean_scale, deviation_scale, metrics),)
                    else:
                        mean_scale, metrics = fit_scale(
                            lambda value, gravity=gravity: evaluate(value, 1.0, gravity), target["height_mean_m"]
                        )
                        deviation_scale = min(
                            2.0,
                            max(0.1, target["height_std_m"] / max(metrics["height_std_m"], 1e-6)),
                        )
                        adjusted_mean_scale, adjusted_metrics = fit_scale(
                            lambda value, gravity=gravity: evaluate(value, deviation_scale, gravity),
                            target["height_mean_m"],
                        )
                        candidates = (
                            (mean_scale, 1.0, metrics),
                            (adjusted_mean_scale, deviation_scale, adjusted_metrics),
                        )
                    for mean_scale, deviation_scale, metrics in candidates:
                        trials.append(
                            {
                                "internode_length_scale": mean_scale,
                                "internode_deviation_scale": deviation_scale,
                                "leaf_gravity_droop_compliance": gravity,
                                "metrics": metrics,
                                "score": score(metrics, target),
                            }
                        )
                selected = min(trials, key=lambda trial: trial["score"])
                scale = selected["internode_length_scale"]
                deviation_scale = selected["internode_deviation_scale"]
                gravity = selected["leaf_gravity_droop_compliance"]
                metrics = selected["metrics"]
                if args.apply and not args.validate_only and not evo.ScaleSorghumLsDescriptorOrganLengths(
                    relative, scale, deviation_scale, 1.0, deviation_scale, gravity
                ):
                    raise RuntimeError(f"failed to scale {relative}")
                results.append(
                    {
                        "stage": stage,
                        "date": STAGE_DATE[stage],
                        "cultivar": cultivar,
                        "descriptor": relative,
                        "applied": args.apply and not args.validate_only,
                        "internode_length_scale": scale,
                        "internode_deviation_scale": deviation_scale,
                        "leaf_gravity_droop_compliance": gravity,
                        "target": target,
                        "candidate": metrics,
                        "trials": trials,
                    }
                )
        result = {"schema_version": 1, "sample_count": args.sample_count, "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)


def main() -> None:
    args = parser().parse_args()
    result = run(args)
    for row in result["results"]:
        print(
            f"{row['stage']} {row['cultivar']}: scale={row['internode_length_scale']:.4f} "
            f"gravity={row['leaf_gravity_droop_compliance']:.1f} "
            f"height={row['candidate']['height_mean_m']:.3f}m target={row['target']['height_mean_m']:.3f}m"
        )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
