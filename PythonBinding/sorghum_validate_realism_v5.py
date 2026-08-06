#!/usr/bin/env python3
"""Measure leaf-mechanics realism metrics for all ten promoted sorghum descriptors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sorghum_lsystem_calibrate_date_cultivar_descriptors import configure_engine_imports, summarize_records


STAGES = tuple(f"GrowthStage{index:02d}" for index in range(1, 6))
CULTIVARS = ("BTX", "Pawaga")


def repo_root_from_script() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CMakeLists.txt").exists() and (parent / "Resources" / "DigitalAgricultureProject").exists():
            return parent
    raise RuntimeError("could not locate repository root")


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
    result.add_argument("--sample-count", type=int, default=100)
    result.add_argument("--seed", type=int, default=5071901)
    result.add_argument("--label", default="candidate")
    result.add_argument("--gravity-compliance", type=float, default=-1.0)
    result.add_argument("--dynamic-growth", action="store_true")
    result.add_argument("--baseline", type=Path)
    result.add_argument("--output", type=Path, default=root / "out" / "realism_review" / "v5" / "metrics.json")
    return result


def relative(candidate: float, baseline: float) -> float:
    return candidate / baseline if abs(baseline) > 1.0e-9 else 0.0


def run(args: argparse.Namespace) -> dict[str, object]:
    configure_engine_imports(args.repo_root.resolve(), args.build_dir.resolve(), args.config)
    import PyDigitalAgriculture as evo  # type: ignore

    project_bytes = args.project.read_bytes()
    if not evo.RunLSystemSorghumProject(args.project.resolve(), args.runtime_package_dir.resolve(), args.base_scene, False):
        raise RuntimeError("failed to start leaf-realism validation scene")
    if not evo.WaitForProjectIdle(240):
        raise RuntimeError("project did not become idle")
    try:
        descriptors: dict[str, object] = {}
        for stage_index, stage in enumerate(STAGES):
            for cultivar_index, cultivar in enumerate(CULTIVARS):
                descriptor = f"GeneratedAssets/Descriptors/{stage}/{cultivar}.sorghumls"
                seed = args.seed + stage_index * 200000 + cultivar_index * 100000
                records = evo.SampleSorghumLsDescriptorAssetPhenotypes(
                    descriptor, args.sample_count, seed, not args.dynamic_growth, True, args.gravity_compliance
                )
                descriptors[f"{stage}/{cultivar}"] = {
                    "descriptor": descriptor,
                    "metrics": summarize_records(records, args.sample_count),
                }

        result: dict[str, object] = {
            "schema_version": 1,
            "label": args.label,
            "sample_count_per_descriptor": args.sample_count,
            "finalize_snapshot_morphology": not args.dynamic_growth,
            "gravity_compliance_override": args.gravity_compliance,
            "descriptors": descriptors,
        }
        if args.baseline:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            comparison = {}
            for key, data in descriptors.items():
                current = data["metrics"]
                previous = baseline["descriptors"][key]["metrics"]
                comparison[key] = {
                    "gravity_tip_deflection_ratio": relative(
                        float(current["main_culm_gravity_tip_deflection_mean_m"]),
                        float(previous["main_culm_gravity_tip_deflection_mean_m"]),
                    ),
                    "centerline_lateral_span_ratio": relative(
                        float(current["main_culm_centerline_lateral_span_mean_m"]),
                        float(previous["main_culm_centerline_lateral_span_mean_m"]),
                    ),
                    "surface_waviness_rms_ratio": relative(
                        float(current["main_culm_surface_waviness_rms_mean_m"]),
                        float(previous["main_culm_surface_waviness_rms_mean_m"]),
                    ),
                    "height_ratio": relative(float(current["height_mean_m"]), float(previous["height_mean_m"])),
                }
            result["comparison_to_baseline"] = comparison

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)


def main() -> None:
    args = parser().parse_args()
    result = run(args)
    for key, data in result["descriptors"].items():
        metrics = data["metrics"]
        print(
            f"{key}: gravity={metrics['main_culm_gravity_tip_deflection_mean_m']:.4f}m "
            f"lateral={metrics['main_culm_centerline_lateral_span_mean_m']:.4f}m "
            f"waviness={metrics['main_culm_surface_waviness_rms_mean_m']:.4f}m "
            f"height={metrics['height_mean_m']:.3f}m"
        )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
