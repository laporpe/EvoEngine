"""Freeze and analyze one immutable 4x10 sorghum scene."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sorghum_4x10_illumination_video import (
    DEFAULT_SPEC,
    _camera_from_scene,
    _vec3 as _camera_vec3,
)
from sorghum_4x10_scene import (
    COORDINATE_SYSTEM,
    plant_organ_ids,
    save_loaded_4x10_scene_at_growth,
)


CONTRACT_VERSION = 1
_DLL_DIRECTORIES: list[object] = []
_ENGINE_SESSION_USED = False


@dataclass(frozen=True)
class SavedSceneSnapshot:
    scene: Path
    provenance: Path
    plant_count: int
    evaluation_gdd: float
    geometry_seed_first: int
    geometry_seed_last: int


@dataclass(frozen=True)
class SavedSceneAnalysis:
    scene: Path
    render: Path
    parbar_probes_csv: Path
    plants_csv: Path
    organs_csv: Path
    manifest: Path

    @property
    def csvs(self) -> tuple[Path, Path, Path]:
        return self.parbar_probes_csv, self.plants_csv, self.organs_csv


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _vec3(value: object) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def _apply_capture_camera(evo: object) -> dict[str, object]:
    camera = _camera_from_scene(evo, DEFAULT_SPEC)
    if not evo.SetMainCameraLookAt(
        _camera_vec3(evo, camera["position"]),
        _camera_vec3(evo, camera["target"]),
        _camera_vec3(evo, camera["up"]),
        float(camera["fov_degrees"]),
    ):
        raise RuntimeError("failed to frame the current 4x10 scene")
    return camera


def _natural_key(value: str) -> tuple[str, int, str]:
    digits = "".join(
        character if character.isdigit() else " " for character in value
    ).split()
    return value.split("_LSystem_")[0], int(digits[-1]) if digits else -1, value


def _scene_path(project: Path, scene: Path) -> Path:
    if scene.is_absolute() or ".." in scene.parts or scene.suffix != ".evescene":
        raise ValueError(
            "scene paths must be .evescene paths relative to project Assets"
        )
    return (project.resolve().parent / "Assets" / scene).resolve()


def _repo_root(project: Path) -> Path:
    for parent in project.resolve().parents:
        if (parent / "CMakeLists.txt").is_file():
            return parent
    raise ValueError(f"project is not inside an EvoEngine checkout: {project}")


def _configure_engine_imports(repo: Path, build_dir: Path, config: str) -> None:
    paths = [
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    ]
    sys.path.insert(0, str(paths[0]))
    sys.path.insert(0, str(repo / "PythonBinding"))
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORIES.extend(
            os.add_dll_directory(str(path)) for path in paths if path.is_dir()
        )


def _default_scene_side_effects(project: Path) -> set[Path]:
    return {
        path.resolve()
        for path in (project.resolve().parent / "Assets").glob("New Scene*.evescene*")
    }


def _asset_metadata(project: Path) -> dict[Path, bytes]:
    assets = project.resolve().parent / "Assets"
    return {
        path.resolve(): path.read_bytes()
        for pattern in ("*.evefilemeta", "*.evefoldermeta")
        for path in assets.rglob(pattern)
    }


@contextmanager
def _loaded_scene(
    project: Path,
    scene: Path,
    build_dir: Path | None,
    runtime_package_dir: Path | None,
    config: str,
    max_wait_frames: int,
):
    global _ENGINE_SESSION_USED
    project = project.resolve()
    scene_file = _scene_path(project, scene)
    if not project.is_file() or not scene_file.is_file():
        raise FileNotFoundError(project if not project.is_file() else scene_file)
    if _ENGINE_SESSION_USED:
        raise RuntimeError(
            "EvoEngine saved-scene operations require a fresh Python process"
        )
    _ENGINE_SESSION_USED = True
    repo = _repo_root(project)
    build_dir = (build_dir or repo / "out" / "build" / "vs2026-x64").resolve()
    runtime_package_dir = (
        runtime_package_dir or build_dir / "EvoEngine_App" / config / "Packages"
    ).resolve()
    _configure_engine_imports(repo, build_dir, config)
    evo = importlib.import_module("PyDigitalAgriculture")
    project_bytes = project.read_bytes()
    metadata = _asset_metadata(project)
    old_side_effects = _default_scene_side_effects(project)
    attempted = False
    try:
        attempted = True
        started = bool(
            evo.RunLSystemSorghumProject(project, runtime_package_dir, scene, False)
        )
        if not started:
            raise RuntimeError(f"failed to load scene: {scene}")
        if not evo.WaitForProjectIdle(max_wait_frames):
            raise RuntimeError(f"project did not become idle after loading: {scene}")
        if not evo.ValidateIlluminationContext():
            raise RuntimeError(f"saved scene is not illumination-ready: {scene}")
        yield evo
    finally:
        try:
            if attempted:
                evo.Terminate()
        finally:
            project.write_bytes(project_bytes)
            for path, content in metadata.items():
                if not path.is_file() or path.read_bytes() != content:
                    path.write_bytes(content)
            for path in _default_scene_side_effects(project) - old_side_effects:
                path.unlink(missing_ok=True)


def _descriptor_rows(records: list[object], assets: Path) -> list[dict[str, object]]:
    descriptors = {
        (str(record.descriptor_asset_path), int(record.descriptor_version))
        for record in records
    }
    rows = []
    for relative_path, version in sorted(descriptors):
        path = assets / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        rows.append(
            {
                "path": relative_path,
                "version": version,
                "sha256": _sha256(path),
            }
        )
    return rows


def _plant_identity_rows(records: list[object]) -> list[dict[str, object]]:
    return [
        {
            "plant_id": str(record.name),
            "cultivar": str(record.cultivar),
            "descriptor_asset_path": str(record.descriptor_asset_path),
            "descriptor_version": int(record.descriptor_version),
            "seed": int(record.seed),
            "evaluation_gdd": float(record.evaluation_gdd),
        }
        for record in sorted(records, key=lambda record: _natural_key(str(record.name)))
    ]


def save_4x10_scene_at_growth(
    *,
    project: Path,
    source_scene: Path,
    scene: Path,
    evaluation_gdd: float,
    geometry_seed: int,
    middle_panel_height_fraction: float = 2.0 / 3.0,
    build_dir: Path | None = None,
    runtime_package_dir: Path | None = None,
    config: str = "RelWithDebInfo",
    max_wait_frames: int = 30000,
) -> SavedSceneSnapshot:
    """Save a new immutable scene recipe at one explicit evaluation GDD."""
    project = project.resolve()
    source_file = _scene_path(project, source_scene)
    scene_file = _scene_path(project, scene)
    provenance = Path(f"{scene_file}.provenance.json")
    if source_file == scene_file:
        raise ValueError("source_scene and scene must differ")
    existing = [
        path
        for path in (scene_file, Path(f"{scene_file}.evefilemeta"), provenance)
        if path.exists()
    ]
    if existing:
        raise FileExistsError(existing[0])
    scene_file.parent.mkdir(parents=True, exist_ok=True)

    with _loaded_scene(
        project,
        source_scene,
        build_dir,
        runtime_package_dir,
        config,
        max_wait_frames,
    ) as evo:
        records = save_loaded_4x10_scene_at_growth(
            evo,
            scene,
            evaluation_gdd,
            geometry_seed,
            middle_panel_height_fraction=middle_panel_height_fraction,
            max_wait_frames=max_wait_frames,
        )
        plants = _plant_identity_rows(records)
        descriptors = _descriptor_rows(records, project.parent / "Assets")

    if not scene_file.is_file():
        raise RuntimeError(f"engine did not write saved scene: {scene_file}")
    payload = {
        "contract_version": CONTRACT_VERSION,
        "coordinate_system": COORDINATE_SYSTEM,
        "scene": scene.as_posix(),
        "scene_sha256": _sha256(scene_file),
        "source_scene": source_scene.as_posix(),
        "evaluation_gdd": evaluation_gdd,
        "geometry_seed_first": geometry_seed,
        "geometry_seed_last": geometry_seed + len(plants) - 1,
        "plant_count": len(plants),
        "descriptor_assets": descriptors,
        "plants": plants,
        "reconstruction": "descriptor asset + plant seed + evaluation GDD",
    }
    provenance.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SavedSceneSnapshot(
        scene_file,
        provenance,
        len(plants),
        evaluation_gdd,
        geometry_seed,
        geometry_seed + len(plants) - 1,
    )


def _verify_provenance(scene_file: Path, assets: Path) -> dict[str, object]:
    path = Path(f"{scene_file}.provenance.json")
    if not path.is_file():
        warnings.warn(f"saved-scene provenance is missing: {path}", stacklevel=2)
        return {"path": None, "verified": False}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mismatches = []
    if payload.get("scene_sha256") != _sha256(scene_file):
        mismatches.append("scene")
    for descriptor in payload.get("descriptor_assets", []):
        descriptor_path = assets / descriptor["path"]
        if not descriptor_path.is_file() or descriptor.get("sha256") != _sha256(
            descriptor_path
        ):
            mismatches.append(str(descriptor["path"]))
    if mismatches:
        warnings.warn(
            f"saved-scene inputs changed since freezing: {', '.join(mismatches)}",
            stacklevel=2,
        )
    return {"path": str(path), "verified": not mismatches, "mismatches": mismatches}


def _plant_rows(records: list[object]) -> list[dict[str, object]]:
    rows = []
    for record in sorted(records, key=lambda item: _natural_key(str(item.name))):
        local = _vec3(record.local_position)
        global_position = _vec3(record.global_position)
        minimum = _vec3(record.geometry_min_position)
        maximum = _vec3(record.geometry_max_position)
        rows.append(
            {
                "plant_id": str(record.name),
                "cultivar": str(record.cultivar),
                "descriptor_asset_path": str(record.descriptor_asset_path),
                "descriptor_version": int(record.descriptor_version),
                "seed": int(record.seed),
                "evaluation_gdd": float(record.evaluation_gdd),
                "local_x_m": local[0],
                "local_y_m": local[1],
                "local_z_m": local[2],
                "global_x_m": global_position[0],
                "global_y_m": global_position[1],
                "global_z_m": global_position[2],
                "geometry_min_x_m": minimum[0],
                "geometry_min_y_m": minimum[1],
                "geometry_min_z_m": minimum[2],
                "geometry_max_x_m": maximum[0],
                "geometry_max_y_m": maximum[1],
                "geometry_max_z_m": maximum[2],
                "plant_height_m": float(record.plant_height_m),
                "leaf_area_m2": float(record.leaf_area_m2),
                "leaf_count": int(record.leaf_count),
                "main_culm_leaf_count": int(record.main_culm_leaf_count),
                "tiller_leaf_count": int(record.tiller_leaf_count),
                "primary_tiller_count": int(record.primary_tiller_count),
                "leaf_width_scale": float(record.leaf_width_scale),
                "leaf_thickness_m": float(record.leaf_thickness_m),
                "middle_parbar_top_elevation_m": float(
                    record.middle_parbar_top_elevation_m
                ),
                "geometry_snapshot_schema_version": int(
                    record.geometry_snapshot_schema_version
                ),
                "geometry_snapshot_version": int(record.geometry_snapshot_version),
                "geometry_snapshot_organ_count": int(
                    record.geometry_snapshot_organ_count
                ),
                "leaf_vertex_count": int(record.leaf_vertex_count),
                "leaf_triangle_count": int(record.leaf_triangle_count),
                "culm_vertex_count": int(record.culm_vertex_count),
                "culm_triangle_count": int(record.culm_triangle_count),
            }
        )
    return rows


def _organ_rows(records: list[object]) -> list[dict[str, object]]:
    by_name = {str(record.name): record for record in records}
    rows = []
    for identifiers in plant_organ_ids(records):
        record = by_name[identifiers.plant_id]
        axes = sorted(record.axes, key=lambda axis: int(axis.axis_id))
        rows.append(
            {
                "plant_id": identifiers.plant_id,
                "cultivar": str(record.cultivar),
                "organ_id": identifiers.main_culm_id,
                "organ_type": "main_culm",
                "axis_id": 0,
                "leaf_rank": "",
            }
        )
        for axis in axes[1:]:
            rows.append(
                {
                    "plant_id": identifiers.plant_id,
                    "cultivar": str(record.cultivar),
                    "organ_id": f"{identifiers.plant_id}/tiller/{int(axis.axis_id)}",
                    "organ_type": "tiller",
                    "axis_id": int(axis.axis_id),
                    "leaf_rank": "",
                }
            )
        for axis in axes:
            for rank in range(1, int(axis.leaf_count) + 1):
                rows.append(
                    {
                        "plant_id": identifiers.plant_id,
                        "cultivar": str(record.cultivar),
                        "organ_id": f"{identifiers.plant_id}/axis/{int(axis.axis_id)}/leaf/{rank}",
                        "organ_type": "leaf",
                        "axis_id": int(axis.axis_id),
                        "leaf_rank": rank,
                    }
                )
    return rows


def _probe_rows(
    records: list[object], samples: int, bounces: int, seed: int
) -> list[dict[str, object]]:
    rows = []
    for record in records:
        position = _vec3(record.position)
        normal = _vec3(record.normal)
        energy = _vec3(record.energy)
        direction = _vec3(record.direction)
        rows.append(
            {
                "cultivar": str(record.cultivar),
                "model": str(record.model),
                "sensor_bar_level": str(record.sensor_bar_level),
                "probe_number": int(record.column) + 1,
                "height_rule": str(record.height_rule),
                "position_x_m": position[0],
                "position_y_m": position[1],
                "position_z_m": position[2],
                "normal_x": normal[0],
                "normal_y": normal[1],
                "normal_z": normal[2],
                "energy_x": energy[0],
                "energy_y": energy[1],
                "energy_z": energy[2],
                "direction_x": direction[0],
                "direction_y": direction[1],
                "direction_z": direction[2],
                "illumination_total_simulated": float(record.scalar),
                "normalized_within_scene": float(record.normalized),
                "represented_plant_count": int(record.represented_plant_count),
                "average_represented_root_elevation_m": float(
                    record.average_represented_root_elevation_m
                ),
                "average_represented_plant_height_m": float(
                    record.average_represented_plant_height_m
                ),
                "sensor_top_elevation_m": float(record.sensor_top_elevation_m),
                "height_fraction_of_average_height": float(
                    record.height_fraction_of_average_height
                ),
                "ray_samples": samples,
                "ray_bounces": bounces,
                "ray_seed": seed,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row["cultivar"]),
            ("top", "middle", "bottom").index(str(row["sensor_bar_level"])),
            int(row["probe_number"]),
        ),
    )


def analyze_saved_4x10_scene(
    *,
    project: Path,
    scene: Path,
    output_dir: Path,
    probes_per_panel: int = 100,
    illumination_samples: int = 64,
    illumination_bounces: int = 4,
    render_samples: int = 64,
    render_bounces: int = 4,
    render_width: int = 1920,
    render_height: int = 1080,
    ray_seed: int = 0,
    push_normal_distance_m: float = 0.001,
    build_dir: Path | None = None,
    runtime_package_dir: Path | None = None,
    config: str = "RelWithDebInfo",
    max_wait_frames: int = 30000,
) -> SavedSceneAnalysis:
    """Materialize a frozen scene recipe, then render and analyze its six PARBAR panels."""
    if (
        min(
            probes_per_panel,
            illumination_samples,
            render_samples,
            render_width,
            render_height,
        )
        <= 0
    ):
        raise ValueError("probe, sample, and render dimensions must be positive")
    if min(illumination_bounces, render_bounces, ray_seed) < 0:
        raise ValueError("bounce counts and ray_seed must be non-negative")

    project = project.resolve()
    scene_file = _scene_path(project, scene)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    render = output_dir / "scene.png"
    probes_csv = output_dir / "parbar_probes.csv"
    plants_csv = output_dir / "plants.csv"
    organs_csv = output_dir / "organs.csv"
    manifest = output_dir / "manifest.json"
    assets = project.parent / "Assets"
    provenance = _verify_provenance(scene_file, assets)

    with _loaded_scene(
        project,
        scene,
        build_dir,
        runtime_package_dir,
        config,
        max_wait_frames,
    ) as evo:
        saved_records = list(evo.GetSorghumLsPlantSceneMetadata(False))
        if len(saved_records) != 40 or any(
            not record.descriptor_asset_path for record in saved_records
        ):
            raise RuntimeError("saved 4x10 scene must contain 40 reproducible plants")
        materialized = int(evo.MaterializeSorghumLsPlantGeometry(False))
        if materialized != 40 or not evo.WaitForProjectIdle(max_wait_frames):
            raise RuntimeError("failed to materialize all 40 saved plants")
        plant_records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        if len(plant_records) != 40 or any(
            not record.has_geometry for record in plant_records
        ):
            raise RuntimeError("saved 4x10 plant geometry is incomplete")
        cultivar_counts = {
            cultivar: sum(record.cultivar == cultivar for record in plant_records)
            for cultivar in ("BTX", "Pawaga")
        }
        if cultivar_counts != {"BTX": 20, "Pawaga": 20}:
            raise RuntimeError(
                f"saved 4x10 scene must contain 20 plants per cultivar: {cultivar_counts}"
            )
        camera = _apply_capture_camera(evo)
        evo.LoopFrames(1)
        sensors = evo.CreateParbarTopFaceSensorGroup(probes_per_panel)
        try:
            evo.EstimatePARSensors(
                sensors,
                illumination_samples,
                illumination_bounces,
                push_normal_distance_m,
                ray_seed,
            )
            probe_records = list(
                evo.GetParbarTopFaceSensorResults(sensors, probes_per_panel)
            )
        finally:
            evo.DeleteRuntimeAsset(sensors)
        expected_probes = 6 * probes_per_panel
        if len(probe_records) != expected_probes:
            raise RuntimeError(
                f"expected {expected_probes} PARBAR probes, got {len(probe_records)}"
            )
        probe_keys = {
            (str(record.cultivar), str(record.sensor_bar_level), int(record.column))
            for record in probe_records
        }
        expected_probe_keys = {
            (cultivar, level, column)
            for cultivar in ("BTX", "Pawaga")
            for level in ("top", "middle", "bottom")
            for column in range(probes_per_panel)
        }
        if probe_keys != expected_probe_keys:
            raise RuntimeError("PARBAR probe identities are incomplete or duplicated")
        if not evo.CaptureCurrentSceneRayTraced(
            render_width,
            render_height,
            render,
            render_samples,
            render_bounces,
            2.2,
        ):
            raise RuntimeError("failed to render saved scene")

        plant_rows = _plant_rows(plant_records)
        organ_rows = _organ_rows(plant_records)
        probe_rows = _probe_rows(
            probe_records, illumination_samples, illumination_bounces, ray_seed
        )
        _write_csv(plants_csv, list(plant_rows[0]), plant_rows)
        _write_csv(organs_csv, list(organ_rows[0]), organ_rows)
        _write_csv(probes_csv, list(probe_rows[0]), probe_rows)
        descriptor_assets = _descriptor_rows(plant_records, assets)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "coordinate_system": COORDINATE_SYSTEM,
        "illumination_units": "EvoEngine relative simulated energy; no PPFD conversion",
        "project": str(project),
        "scene": scene.as_posix(),
        "scene_sha256": _sha256(scene_file),
        "saved_scene_provenance": provenance,
        "descriptor_assets": descriptor_assets,
        "plant_count": len(plant_rows),
        "probe_count": len(probe_rows),
        "camera": camera,
        "settings": {
            "probes_per_panel": probes_per_panel,
            "illumination_samples": illumination_samples,
            "illumination_bounces": illumination_bounces,
            "ray_seed": ray_seed,
            "push_normal_distance_m": push_normal_distance_m,
            "render_samples": render_samples,
            "render_bounces": render_bounces,
            "render_width": render_width,
            "render_height": render_height,
        },
        "artifacts": {
            path.name: {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in (render, probes_csv, plants_csv, organs_csv)
        },
    }
    manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SavedSceneAnalysis(
        scene_file, render, probes_csv, plants_csv, organs_csv, manifest
    )
