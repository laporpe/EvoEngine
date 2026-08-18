#!/usr/bin/env python3
"""Create the marker template and two measured-stage 2026 6x10 scenes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, ROW_GENOTYPES, repo_root_from_script
from sorghum_generate_calibrated_field_scenes import (
    cleanup_new_default_scene_side_effects,
    collect_default_scene_side_effects,
    discard_staged_scene,
    promote_staged_scene,
    staging_scene_target,
)


SESSIONS = ("MeasurementStage01", "MeasurementStage02")
GENOTYPES = ("GenotypeA", "GenotypeB", "GenotypeC")
SOURCE_SCENE = Path("ManualAssets/Scenes/Sorghum_4x10_PARBAR.evescene")
TEMPLATE_SCENE = Path("ManualAssets/Scenes/Sorghum_6x10_2026.evescene")
GENERATED_SCENE_ROOT = Path("GeneratedAssets/Experiments") / EXPERIMENT_ID / "Scenes"
SEEDS = {"MeasurementStage01": 202_607_150, "MeasurementStage02": 202_607_210}
MARKER_PATTERN = re.compile(r"^(Genotype[ABC])_LSystem_R([0-5])_C([0-9])$")
PARBAR_GENOTYPES = ("GenotypeA", "GenotypeB", "GenotypeC")
MANIFEST_COLUMNS = (
    "session_id",
    "collection_dates",
    "scene_asset_path",
    "plant_name",
    "genotype_id",
    "row",
    "column",
    "seed",
    "descriptor_asset_path",
    "x_m",
    "y_m",
    "z_m",
    "plant_height_m",
    "main_culm_leaf_count",
    "primary_tiller_count",
    "parbar_context_present",
    "illumination_estimation_performed",
)


def configure_engine_imports(build_dir: Path, config: str) -> None:
    paths = (
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    )
    sys.path.insert(0, str(paths[0]))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def descriptor_maps(build_report: dict[str, object]) -> dict[str, dict[str, Path]]:
    result: dict[str, dict[str, Path]] = defaultdict(dict)
    for row in build_report["descriptors"]:  # type: ignore[index]
        result[str(row["session_id"])][str(row["genotype_id"])] = Path(str(row["descriptor_asset_path"]))
    expected = {(session, genotype) for session in SESSIONS for genotype in GENOTYPES}
    actual = {(session, genotype) for session, rows in result.items() for genotype in rows}
    if actual != expected:
        raise ValueError(f"descriptor report coverage mismatch: missing={sorted(expected - actual)}")
    return dict(result)


def collection_dates(plants: list[dict[str, str]]) -> dict[str, dict[str, tuple[str, ...]]]:
    dates: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in plants:
        dates[row["session_id"]][row["genotype_id"]].add(row["collection_date"])
    return {
        session: {genotype: tuple(sorted(values)) for genotype, values in genotypes.items()}
        for session, genotypes in dates.items()
    }


def start_project(evo: object, args: argparse.Namespace, scene: Path) -> None:
    if not evo.RunLSystemSorghumProject(args.project.resolve(), args.runtime_package_dir.resolve(), scene):
        raise RuntimeError(f"failed to load source scene: {scene}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError(f"project did not become idle after loading {scene}")


def save_scene(evo: object, args: argparse.Namespace, target: Path) -> None:
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError(f"PBR soil context is invalid for {target}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError(f"project did not become idle before saving {target}")
    if not evo.SaveActiveSceneAsProjectAsset(target):
        raise RuntimeError(f"failed to save {target}")


def create_template(evo: object, args: argparse.Namespace) -> dict[str, object]:
    assets = args.project_root / "Assets"
    source_path = assets / SOURCE_SCENE
    source_hash = sha256(source_path)
    staged = staging_scene_target(TEMPLATE_SCENE)
    project_bytes = args.project.read_bytes()
    side_effects = collect_default_scene_side_effects(args.project)
    try:
        try:
            start_project(evo, args, SOURCE_SCENE)
            markers = int(evo.ConfigureSorghumLsReplicatedSixByTenProfile(list(GENOTYPES)))
            if markers != 60:
                raise RuntimeError(f"expected 60 planting markers, got {markers}")
            save_scene(evo, args, staged)
        finally:
            args.project.write_bytes(project_bytes)
            cleanup_new_default_scene_side_effects(args.project, side_effects)
            if sha256(source_path) != source_hash:
                raise RuntimeError("legacy 4x10 source scene changed while creating the 2026 template")
    except Exception:
        discard_staged_scene(args.project_root, staged)
        raise
    promote_staged_scene(args.project_root, staged, TEMPLATE_SCENE)
    template_text = (assets / TEMPLATE_SCENE).read_text(encoding="utf-8")
    if template_text.count("n: Genotype") != 60:
        raise RuntimeError("saved 2026 template failed marker validation")
    validate_parbar_scene_text(template_text)
    return {
        "asset_path": TEMPLATE_SCENE.as_posix(),
        "marker_count": 60,
        "profile_source": SOURCE_SCENE.as_posix(),
        "row_spacing_within_block_m": 1.10,
        "row_spacing_between_blocks_m": 2.20,
        "block_center_spacing_m": 3.30,
        "column_spacing_m": 0.76,
        "parbar_rig_count": 3,
        "sensor_bar_count": 9,
        "parbar_context_present": True,
        "parbar_geometry_ownership": "replicated_from_manual_4x10_profile_for_2026_visual_context",
    }


def validate_records(session: str, records: list[object]) -> None:
    if len(records) != 60:
        raise RuntimeError(f"{session}: expected 60 generated plants, got {len(records)}")
    names: set[str] = set()
    genotypes: Counter[str] = Counter()
    coordinates: set[tuple[int, int]] = set()
    seeds: set[int] = set()
    for record in records:
        match = MARKER_PATTERN.fullmatch(str(record.name))
        if not match:
            raise RuntimeError(f"{session}: invalid stable plant identity: {record.name}")
        genotype, row_text, column_text = match.groups()
        row, column = int(row_text), int(column_text)
        if ROW_GENOTYPES[row] != genotype or str(record.cultivar) != genotype:
            raise RuntimeError(f"{session}: genotype/row mismatch for {record.name}")
        if not bool(record.has_geometry):
            raise RuntimeError(f"{session}: missing geometry for {record.name}")
        names.add(str(record.name))
        genotypes[genotype] += 1
        coordinates.add((row, column))
        seeds.add(int(record.seed))
    if len(names) != 60 or len(coordinates) != 60 or len(seeds) != 60:
        raise RuntimeError(f"{session}: plant names, coordinates, and seeds must each be unique")
    if genotypes != Counter({genotype: 20 for genotype in GENOTYPES}):
        raise RuntimeError(f"{session}: genotype composition mismatch: {genotypes}")


def validate_profile_geometry(session: str, records: list[object], tolerance_m: float = 1e-3) -> None:
    rows: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for record in records:
        match = MARKER_PATTERN.fullmatch(str(record.name))
        if not match:
            raise RuntimeError(f"{session}: invalid profile identity: {record.name}")
        position = record.global_position
        rows[int(match.group(2))].append((float(position.x), float(position.z)))
    if set(rows) != set(range(6)) or any(len(values) != 10 for values in rows.values()):
        raise RuntimeError(f"{session}: profile must contain six complete ten-plant rows")

    row_z = []
    for row in range(6):
        values = sorted(rows[row])
        z_values = [value[1] for value in values]
        if max(z_values) - min(z_values) > tolerance_m:
            raise RuntimeError(f"{session}: row {row} is not straight in z")
        spacings = [values[index + 1][0] - values[index][0] for index in range(9)]
        if any(abs(spacing - 0.76) > tolerance_m for spacing in spacings):
            raise RuntimeError(f"{session}: row {row} does not preserve 0.76 m in-row spacing")
        row_z.append(sum(z_values) / len(z_values))

    deltas = [abs(row_z[index + 1] - row_z[index]) for index in range(5)]
    expected = (1.10, 2.20, 1.10, 2.20, 1.10)
    if any(abs(actual - target) > tolerance_m for actual, target in zip(deltas, expected)):
        raise RuntimeError(f"{session}: expected repeated 2x10 row deltas {expected}, got {tuple(deltas)}")


def validate_parbar_scene_text(scene_text: str) -> None:
    roots = re.findall(r"^\s*- n: PARBAR_(Genotype[ABC])\s*$", scene_text, re.MULTILINE)
    if Counter(roots) != Counter(PARBAR_GENOTYPES):
        raise RuntimeError(f"expected one complete PARBAR rig per genotype, got {Counter(roots)}")
    for genotype in PARBAR_GENOTYPES:
        for level in ("Top", "Middle", "Bottom"):
            name = f"n: PARBAR_{genotype}_{level}SensorBarMesh"
            if scene_text.count(name) != 1:
                raise RuntimeError(f"expected exactly one {name}")
    if "PARBAR_BTX" in scene_text or "PARBAR_Pawaga" in scene_text:
        raise RuntimeError("2026 profile retained a legacy cultivar label on replicated instrumentation")


def record_rows(
    session: str,
    target: Path,
    records: list[object],
    dates: dict[str, dict[str, tuple[str, ...]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in sorted(records, key=lambda value: value.name):
        genotype, row, column = MARKER_PATTERN.fullmatch(str(record.name)).groups()  # type: ignore[union-attr]
        position = record.global_position
        rows.append(
            {
                "session_id": session,
                "collection_dates": ";".join(dates[session][genotype]),
                "scene_asset_path": target.as_posix(),
                "plant_name": record.name,
                "genotype_id": genotype,
                "row": int(row),
                "column": int(column),
                "seed": int(record.seed),
                "descriptor_asset_path": record.descriptor_asset_path,
                "x_m": float(position.x),
                "y_m": float(position.y),
                "z_m": float(position.z),
                "plant_height_m": float(record.plant_height_m),
                "main_culm_leaf_count": int(record.main_culm_leaf_count),
                "primary_tiller_count": int(record.primary_tiller_count),
                "parbar_context_present": True,
                "illumination_estimation_performed": False,
            }
        )
    return rows


def generate_session(
    evo: object,
    args: argparse.Namespace,
    session: str,
    descriptors: dict[str, Path],
    dates: dict[str, dict[str, tuple[str, ...]]],
    reset_to_markers: bool,
) -> tuple[Path, list[dict[str, object]]]:
    target = GENERATED_SCENE_ROOT / f"Sorghum_6x10_{session}.evescene"
    staged = staging_scene_target(target)
    template_path = args.project_root / "Assets" / TEMPLATE_SCENE
    template_hash = sha256(template_path)
    try:
        if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != 60:
            raise RuntimeError(f"{session}: failed to instantiate 60 marker plants")
        if int(evo.ConformSorghumLsPlantsToGroundMesh()) != 60:
            raise RuntimeError(f"{session}: failed to conform 60 roots to the measured soil surface")
        if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, -1)) != 60:
            raise RuntimeError(f"{session}: failed to assign all three descriptor assets")
        if int(evo.GrowSorghumLsPlantsToAdulthood(SEEDS[session])) != 60:
            raise RuntimeError(f"{session}: failed to grow 60 plants")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError(f"{session}: geometry did not become idle")
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        validate_records(session, records)
        validate_profile_geometry(session, records)
        save_scene(evo, args, staged)
        if reset_to_markers and int(evo.ConvertSorghumLsPlantsToPlantingMarkers()) != 60:
            raise RuntimeError(f"{session}: failed to restore the shared template marker state")
        if sha256(template_path) != template_hash:
            raise RuntimeError(f"{session}: 2026 marker template changed during scene generation")
    except Exception:
        discard_staged_scene(args.project_root, staged)
        raise
    promote_staged_scene(args.project_root, staged, target)
    scene_text = (args.project_root / "Assets" / target).read_text(encoding="utf-8")
    validate_parbar_scene_text(scene_text)
    return target, record_rows(session, target, records, dates)


def write_manifest(data_root: Path, template: dict[str, object], rows: list[dict[str, object]]) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    csv_path = data_root / "scene_manifest.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "purpose": "rendering_morphology_and_replicated_instrument_context",
        "template": template,
        "scene_count": len({row["session_id"] for row in rows}),
        "plant_rows": len(rows),
        "parbar_context_present": True,
        "illumination_estimation_performed": False,
        "scientific_boundary": (
            "PARBAR geometry is a spatial replica of the manual 4x10 profile for visual context only; "
            "no 2026 PARBAR observation or illumination result is claimed."
        ),
    }
    (data_root / "scene_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    build_dir = repo_root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument("--runtime-package-dir", type=Path, default=build_dir / "EvoEngine_App/RelWithDebInfo/Packages")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    data_root = args.project_root / "Data" / "Experiments" / EXPERIMENT_ID
    build_report = json.loads((data_root / "descriptor_build_report.json").read_text(encoding="utf-8"))
    descriptors = descriptor_maps(build_report)
    dates = collection_dates(read_csv(data_root / "plants.csv"))
    build_dir = args.build_dir.resolve()
    configure_engine_imports(build_dir, args.config)
    os.chdir(build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    try:
        template = create_template(evo, args)
        rows: list[dict[str, object]] = []
        for index, session in enumerate(SESSIONS):
            target, session_rows = generate_session(
                evo, args, session, descriptors[session], dates, reset_to_markers=index + 1 < len(SESSIONS)
            )
            rows.extend(session_rows)
            print(f"{session}: {target.as_posix()} ({len(session_rows)} plants)")
        write_manifest(data_root, template, rows)
        print(f"manifest: {(data_root / 'scene_manifest.json').resolve()}")
    finally:
        evo.Terminate()


if __name__ == "__main__":
    main()
