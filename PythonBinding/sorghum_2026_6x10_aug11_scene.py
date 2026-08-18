#!/usr/bin/env python3
"""Generate the endpoint-only August 11 A/A/B/B/C/C 6x10 field scene."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sorghum_2026_6x10_aug11_data import EXPERIMENT_ID, SESSION_ID
from sorghum_2026_6x10_data import repo_root_from_script
from sorghum_2026_6x10_scene import (
    GENOTYPES,
    TEMPLATE_SCENE,
    cleanup_new_default_scene_side_effects,
    collect_default_scene_side_effects,
    collection_dates,
    configure_engine_imports,
    descriptor_maps,
    generate_session,
    read_csv,
    start_project,
    write_manifest,
)


SCENE_ROOT = Path("GeneratedAssets") / "Experiments" / EXPERIMENT_ID / "Scenes"
FIELD_SEED = 202_608_110


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    build_dir = repo_root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="Debug")
    parser.add_argument("--runtime-package-dir", type=Path, default=None)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = (
        args.runtime_package_dir.resolve()
        if args.runtime_package_dir
        else args.build_dir / "EvoEngine_App" / args.config / "Packages"
    )
    data_root = args.project_root / "Data" / "Experiments" / EXPERIMENT_ID
    build_report = json.loads((data_root / "descriptor_build_report.json").read_text(encoding="utf-8"))
    descriptors = descriptor_maps(build_report, (SESSION_ID,), GENOTYPES)[SESSION_ID]
    dates = collection_dates(read_csv(data_root / "plants.csv"))
    configure_engine_imports(args.build_dir, args.config)
    os.chdir(args.build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    project_bytes = args.project.read_bytes()
    side_effects = collect_default_scene_side_effects(args.project)
    try:
        start_project(evo, args, TEMPLATE_SCENE)
        target, rows = generate_session(
            evo,
            args,
            SESSION_ID,
            descriptors,
            dates,
            False,
            scene_root=SCENE_ROOT,
            seed=FIELD_SEED,
        )
        template = {
            "asset_path": TEMPLATE_SCENE.as_posix(),
            "marker_count": 60,
            "rows": 6,
            "columns": 10,
            "row_genotypes": ["GenotypeA", "GenotypeA", "GenotypeB", "GenotypeB", "GenotypeC", "GenotypeC"],
            "column_spacing_m": 0.76,
            "parbar_rig_count": 3,
        }
        write_manifest(data_root, template, rows, EXPERIMENT_ID)
        print(json.dumps({"scene": target.as_posix(), "plants": len(rows)}, indent=2))
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)
        cleanup_new_default_scene_side_effects(args.project, side_effects)


if __name__ == "__main__":
    main()
