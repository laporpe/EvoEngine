"""Small scene-recipe API for repeatable 4x10 sorghum realizations."""

from __future__ import annotations

import csv
import warnings
from dataclasses import dataclass
from pathlib import Path

from sorghum_asset_layout import DATE_ORDER, descriptor_path


API_VERSION = (1, 0)
COORDINATE_SYSTEM = "EvoEngine Y-up"
CULTIVARS = ("BTX", "Pawaga")

__all__ = [
    "COORDINATE_SYSTEM",
    "FourByTenScene",
    "PlantOrganIds",
    "grow_4x10_scene",
    "plant_organ_ids",
    "prepare_4x10_scene",
    "query_4x10_scene",
]


@dataclass(frozen=True)
class FourByTenScene:
    date: str
    scene_asset_path: str
    btx_descriptor: Path
    pawaga_descriptor: Path
    leaf_thickness_m: float
    leaf_width_scale: float
    plant_count: int
    coordinate_system: str = COORDINATE_SYSTEM


@dataclass(frozen=True)
class PlantOrganIds:
    plant_id: str
    main_culm_id: str
    tiller_ids: tuple[str, ...]
    leaf_ids: tuple[str, ...]


def check_compatibility(requested: tuple[int, int]) -> None:
    if requested[0] != API_VERSION[0]:
        raise RuntimeError(
            f"unsupported 4x10 scene API major version {requested[0]}; expected {API_VERSION[0]}"
        )
    if requested[1] > API_VERSION[1]:
        warnings.warn(
            f"4x10 scene API minor version {requested[1]} is newer than {API_VERSION[1]}",
            stacklevel=2,
        )


def query_4x10_scene(
    manifest_path: Path,
    descriptor_root: Path,
    date: str,
    api_version: tuple[int, int] = API_VERSION,
) -> FourByTenScene:
    check_compatibility(api_version)
    if date not in DATE_ORDER:
        raise ValueError(f"unsupported 4x10 date: {date}")
    with manifest_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = [row for row in csv.DictReader(stream) if row["date"] == date]
    counts = {
        cultivar: sum(row["cultivar"] == cultivar for row in rows)
        for cultivar in CULTIVARS
    }
    if len(rows) != 40 or counts != {cultivar: 20 for cultivar in CULTIVARS}:
        raise ValueError(f"{date} must contain 40 plants and 20 per cultivar: {counts}")

    def one(column: str, convert=str):
        values = {convert(row[column]) for row in rows}
        if len(values) != 1:
            raise ValueError(f"{date} has {len(values)} values for {column}")
        return values.pop()

    return FourByTenScene(
        date=date,
        scene_asset_path=one("scene_asset_path"),
        btx_descriptor=descriptor_path(descriptor_root, date, "BTX"),
        pawaga_descriptor=descriptor_path(descriptor_root, date, "Pawaga"),
        leaf_thickness_m=one("leaf_thickness_m", float),
        leaf_width_scale=one("leaf_width_scale", float),
        plant_count=len(rows),
    )


def prepare_4x10_scene(
    evo: object,
    project: Path,
    runtime_package_dir: Path,
    scene: FourByTenScene,
    geometry_seed: int,
    middle_panel_height_fraction: float,
    after_panel_move_frames: int,
    max_wait_frames: int,
) -> None:
    if not evo.RunLSystemSorghumProject(
        project.resolve(), runtime_package_dir.resolve(), Path(scene.scene_asset_path)
    ):
        raise RuntimeError(f"failed to start project scene: {scene.scene_asset_path}")
    if not evo.WaitForProjectIdle(max_wait_frames):
        raise RuntimeError(
            f"project did not become idle after loading {scene.scene_asset_path}"
        )
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError(f"scene is not illumination-ready: {scene.scene_asset_path}")

    assigned = int(
        evo.SetSorghumLsCultivarDescriptors(
            scene.btx_descriptor, scene.pawaga_descriptor, False, -1
        )
    )
    thickness = int(evo.SetSorghumLsLeafThickness(scene.leaf_thickness_m, False))
    width = int(evo.SetSorghumLsLeafWidthScale(scene.leaf_width_scale, False))
    grown = int(evo.GrowSorghumLsPlantsToAdulthood(geometry_seed, "", True, False))
    if (assigned, thickness, width, grown) != (scene.plant_count,) * 4:
        raise RuntimeError(
            f"{scene.date}: expected {scene.plant_count} prepared plants, got "
            f"assigned={assigned}, thickness={thickness}, width={width}, grown={grown}"
        )
    evo.LoopFrames(after_panel_move_frames)
    if not evo.WaitForProjectIdle(max_wait_frames):
        raise RuntimeError(f"project did not become idle after growth for {scene.date}")
    moved = int(
        evo.MoveParbarMiddlePanelsToPlantHeightFraction(middle_panel_height_fraction)
    )
    if moved != 2:
        raise RuntimeError(
            f"{scene.date}: expected 2 moved middle PARBAR panels, got {moved}"
        )
    evo.LoopFrames(after_panel_move_frames)
    if not evo.WaitForProjectIdle(max_wait_frames):
        raise RuntimeError(
            f"project did not become idle after moving middle panels for {scene.date}"
        )


def grow_4x10_scene(
    evo: object, scene: FourByTenScene, geometry_seed: int, max_wait_frames: int
) -> None:
    grown = int(evo.GrowSorghumLsPlantsToAdulthood(geometry_seed, "", True, False))
    if grown != scene.plant_count:
        raise RuntimeError(
            f"{scene.date}: expected {scene.plant_count} grown plants, got {grown}"
        )
    evo.LoopFrames(1)
    if not evo.WaitForProjectIdle(max_wait_frames):
        raise RuntimeError(
            f"project did not become idle after geometry seed {geometry_seed}"
        )


def plant_organ_ids(records: list[object]) -> list[PlantOrganIds]:
    result = []
    for record in records:
        axes = sorted(record.axes, key=lambda axis: int(axis.axis_id))
        if not axes or int(axes[0].axis_id) != 0:
            raise ValueError(f"plant has no main culm: {record.name}")
        result.append(
            PlantOrganIds(
                plant_id=str(record.name),
                main_culm_id=f"{record.name}/culm/0",
                tiller_ids=tuple(
                    f"{record.name}/tiller/{int(axis.axis_id)}" for axis in axes[1:]
                ),
                leaf_ids=tuple(
                    f"{record.name}/axis/{int(axis.axis_id)}/leaf/{rank}"
                    for axis in axes
                    for rank in range(1, int(axis.leaf_count) + 1)
                ),
            )
        )
    return result
