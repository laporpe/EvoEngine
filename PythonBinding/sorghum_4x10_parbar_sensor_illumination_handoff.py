#!/usr/bin/env python3
"""Generate replicated five-stage 4x10 PARBAR illumination handoff CSVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sorghum_4x10_scene import (
    API_VERSION as SCENE_API_VERSION,
    COORDINATE_SYSTEM,
    FourByTenScene,
    grow_4x10_scene,
    prepare_4x10_scene,
    query_4x10_scene,
)
from sorghum_asset_layout import (
    DATE_ORDER,
    GENERATED_DESCRIPTOR_ROOT,
    GENERATED_REPORT_ROOT,
    MANUAL_4X10_SCENE,
    descriptor_path,
)


CULTIVARS = ("BTX", "Pawaga")
BAR_LEVELS = ("top", "middle", "bottom")
REFERENCE_4X10_SCENE = MANUAL_4X10_SCENE.as_posix()
MAX_SEED = 2_147_483_647
CHECKPOINT_VERSION = 1

SENSOR_NUMERIC_COLUMNS = [
    "illumination_total_simulated",
    "probe_position_x_m",
    "probe_position_y_m",
    "probe_position_z_m",
    "probe_normal_x",
    "probe_normal_y",
    "probe_normal_z",
    "represented_clump_count",
    "average_represented_root_elevation_m",
    "average_represented_plant_height_m",
    "height_fraction_of_average_height",
    "sensor_top_elevation_m",
]

SENSOR_COLUMNS = (
    [
        "date",
        "cultivar",
        "source_scene",
        "reference_scene",
        "calibrated_btx_descriptor",
        "calibrated_pawaga_descriptor",
        "sensor_bar_level",
        "probe_number",
        "height_rule",
        "replicate_count",
    ]
    + [
        f"{column}_{suffix}"
        for column in SENSOR_NUMERIC_COLUMNS
        for suffix in ("mean", "std")
    ]
    + [
        "illumination_total_simulated_sem",
        "illumination_total_simulated_ci95_low",
        "illumination_total_simulated_ci95_high",
        "ray_samples",
        "ray_bounces",
        "ray_seed_base",
        "ray_seed_last",
        "geometry_seed_base",
        "geometry_seed_last",
        "geometry_seed_stride",
        "plant_count_per_replicate",
        "push_normal_distance_m",
    ]
)


@contextmanager
def exclusive_file_lock(path: Path, conflict_message: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("a+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        lock_file.close()
        raise RuntimeError(conflict_message) from error
    try:
        yield
    finally:
        lock_file.seek(0)
        if os.name == "nt":
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


PLANT_COLUMNS = [
    "date",
    "cultivar",
    "original_position_id",
    "plant_id",
    "cluster_member_number",
    "plants_at_original_position",
    "plant_height_m",
    "source_final_height_m",
    "target_height_m",
    "height_error_m",
    "source_height_error_m",
    "leaf_count",
    "source_leaf_count",
    "primary_tiller_count",
    "target_leaf_modules_mean",
    "target_leaf_modules_stdev",
    "clump_mean_height_m",
    "source_clump_mean_height_m",
    "source_leaf_thickness_m",
    "leaf_thickness_scale",
    "leaf_thickness_m",
    "source_leaf_width_scale",
    "leaf_width_scale",
    "source_cluster_offset_x_m",
    "source_cluster_offset_z_m",
    "source_cluster_offset_radius_m",
    "cluster_offset_x_m",
    "cluster_offset_z_m",
    "cluster_offset_radius_m",
    "cluster_radius_scale",
    "cluster_outward_lean_degrees",
    "middle_parbar_top_elevation_m",
    "source_middle_parbar_top_elevation_m",
    "source_scene",
]

CLUMP_COLUMNS = [
    "date",
    "cultivar",
    "original_position_id",
    "plants_at_original_position",
    "extra_clustered_plants",
    "anchor_plant_id",
    "anchor_plant_height_m",
    "mean_plant_height_m",
    "min_plant_height_m",
    "max_plant_height_m",
    "mean_leaf_count",
    "min_leaf_count",
    "max_leaf_count",
    "member_plant_ids",
    "target_height_m",
    "target_leaf_modules_mean",
    "target_leaf_modules_stdev",
    "middle_parbar_top_elevation_m",
    "source_scene",
]

SEED_SCHEDULE_COLUMNS = [
    "date",
    "growth_stage_index",
    "replicate_number",
    "plant_count",
    "geometry_seed_first",
    "geometry_seed_last",
    "ray_seed",
]


@dataclass
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError(f"non-finite sample: {value}")
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def std(self) -> float:
        return (
            math.sqrt(max(0.0, self.m2 / (self.count - 1))) if self.count > 1 else 0.0
        )

    @property
    def sem(self) -> float:
        return self.std / math.sqrt(self.count) if self.count else 0.0

    @property
    def ci95(self) -> tuple[float, float]:
        margin = 1.96 * self.sem
        return self.mean - margin, self.mean + margin

    def to_dict(self) -> dict[str, int | float]:
        return {"count": self.count, "mean": self.mean, "m2": self.m2}

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RunningStats:
        return cls(int(value["count"]), float(value["mean"]), float(value["m2"]))


@dataclass
class SummaryAccumulator:
    base: dict[str, object]
    stats: dict[str, RunningStats] = field(default_factory=dict)

    def add(self, values: dict[str, float]) -> None:
        if set(values) != set(SENSOR_NUMERIC_COLUMNS):
            raise ValueError("sensor values do not match the summary schema")
        for column in SENSOR_NUMERIC_COLUMNS:
            value = values[column]
            self.stats.setdefault(column, RunningStats()).add(float(value))

    @property
    def count(self) -> int:
        counts = {stats.count for stats in self.stats.values()}
        if len(counts) > 1:
            raise ValueError(
                "summary accumulator columns have inconsistent sample counts"
            )
        return counts.pop() if counts else 0

    def to_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "stats": {column: stats.to_dict() for column, stats in self.stats.items()},
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> SummaryAccumulator:
        return cls(
            dict(value["base"]),
            {
                column: RunningStats.from_dict(stats)
                for column, stats in dict(value["stats"]).items()
            },
        )

    def row(self, args: argparse.Namespace) -> dict[str, object]:
        if self.count != args.replicates or set(self.stats) != set(
            SENSOR_NUMERIC_COLUMNS
        ):
            raise ValueError(
                f"incomplete summary accumulator: {self.count} of {args.replicates} replicates"
            )
        output = dict(self.base)
        output["replicate_count"] = self.count
        for column in SENSOR_NUMERIC_COLUMNS:
            stats = self.stats[column]
            output[f"{column}_mean"] = stats.mean
            output[f"{column}_std"] = stats.std
        illumination = self.stats["illumination_total_simulated"]
        output["illumination_total_simulated_sem"] = illumination.sem
        (
            output["illumination_total_simulated_ci95_low"],
            output["illumination_total_simulated_ci95_high"],
        ) = illumination.ci95
        date = str(self.base["date"])
        output.update(
            {
                "ray_samples": args.samples,
                "ray_bounces": args.bounces,
                "ray_seed_base": ray_seed_for_replicate(args.seed, date, 0),
                "ray_seed_last": ray_seed_for_replicate(
                    args.seed, date, args.replicates - 1
                ),
                "geometry_seed_base": geometry_seed_for_replicate(
                    args.geometry_seed, args.geometry_seed_stride, date, 0
                ),
                "geometry_seed_last": geometry_seed_for_replicate(
                    args.geometry_seed,
                    args.geometry_seed_stride,
                    date,
                    args.replicates - 1,
                )
                + args.expected_plant_count
                - 1,
                "geometry_seed_stride": args.geometry_seed_stride,
                "plant_count_per_replicate": args.expected_plant_count,
                "push_normal_distance_m": args.push_normal_distance,
            }
        )
        return output


def repo_root_from_script() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CMakeLists.txt").exists() and (
            parent / "Resources" / "DigitalAgricultureProject"
        ).exists():
            return parent
    return Path(__file__).resolve().parents[1]


def configure_engine_imports(repo_root: Path, build_dir: Path, config: str) -> None:
    paths = [
        build_dir / "PythonBinding" / config,
        build_dir / "EvoEngine_App" / config,
        build_dir / "EvoEngine_App" / config / "Packages",
        build_dir / "EvoEngine_SDK" / config,
        build_dir / "EvoEngine_Services" / "CudaModule" / config,
    ]
    sys.path.insert(0, str(paths[0]))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))
    sys.path.insert(0, str(repo_root / "PythonBinding"))


def parse_dates(value: str) -> list[str]:
    dates = [item.strip() for item in value.split(",") if item.strip()]
    if not dates:
        raise argparse.ArgumentTypeError("at least one date is required")
    unknown = [date for date in dates if date not in DATE_ORDER]
    if unknown:
        raise argparse.ArgumentTypeError(f"unsupported date(s): {', '.join(unknown)}")
    if len(dates) != len(set(dates)):
        raise argparse.ArgumentTypeError("--dates must not contain duplicates")
    return dates


def campaign_slot(date: str, replicate: int) -> int:
    if date not in DATE_ORDER or replicate < 0:
        raise ValueError(
            f"invalid campaign coordinate: date={date}, replicate={replicate}"
        )
    return replicate * len(DATE_ORDER) + DATE_ORDER.index(date)


def replicate_batch_stop(start: int, total: int, batch_size: int) -> int:
    if start < 0 or total <= 0 or start > total or batch_size < 0:
        raise ValueError("invalid engine replicate batch")
    return total if batch_size == 0 else min(total, start + batch_size)


def geometry_seed_for_replicate(
    seed_base: int, stride: int, date: str, replicate: int
) -> int:
    return seed_base + campaign_slot(date, replicate) * stride


def ray_seed_for_replicate(seed_base: int, date: str, replicate: int) -> int:
    return seed_base + campaign_slot(date, replicate)


def validate_seed_plan(
    geometry_seed: int,
    geometry_seed_stride: int,
    ray_seed: int,
    replicates: int,
    plant_counts: dict[str, int],
) -> None:
    if geometry_seed < 0 or ray_seed < 0:
        raise ValueError("seed bases must be non-negative")
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    if not plant_counts or any(
        date not in DATE_ORDER or count <= 0 for date, count in plant_counts.items()
    ):
        raise ValueError("plant counts must be positive and use supported dates")
    if geometry_seed_stride < max(plant_counts.values()):
        raise ValueError(
            "geometry seed stride must be at least the largest per-scene plant count"
        )
    last_geometry_seed = max(
        geometry_seed_for_replicate(
            geometry_seed, geometry_seed_stride, date, replicates - 1
        )
        + count
        - 1
        for date, count in plant_counts.items()
    )
    last_ray_seed = max(
        ray_seed_for_replicate(ray_seed, date, replicates - 1) for date in plant_counts
    )
    if last_geometry_seed > MAX_SEED or last_ray_seed > MAX_SEED:
        raise ValueError(
            "campaign seed plan exceeds the signed 32-bit engine API range"
        )


def seed_schedule_rows(
    args: argparse.Namespace, plant_counts: dict[str, int]
) -> list[dict[str, int | str]]:
    rows = []
    for replicate in range(args.replicates):
        for date in DATE_ORDER:
            if date not in plant_counts:
                continue
            first = geometry_seed_for_replicate(
                args.geometry_seed, args.geometry_seed_stride, date, replicate
            )
            rows.append(
                {
                    "date": date,
                    "growth_stage_index": DATE_ORDER.index(date),
                    "replicate_number": replicate + 1,
                    "plant_count": plant_counts[date],
                    "geometry_seed_first": first,
                    "geometry_seed_last": first + plant_counts[date] - 1,
                    "ray_seed": ray_seed_for_replicate(args.seed, date, replicate),
                }
            )
    return rows


def validate_seed_schedule(rows: list[dict[str, int | str]]) -> None:
    intervals = sorted(
        (int(row["geometry_seed_first"]), int(row["geometry_seed_last"]))
        for row in rows
    )
    if any(first > last for first, last in intervals):
        raise ValueError("invalid geometry seed interval")
    if any(
        current[0] <= previous[1] for previous, current in zip(intervals, intervals[1:])
    ):
        raise ValueError("overlapping geometry seed intervals")
    ray_seeds = [int(row["ray_seed"]) for row in rows]
    if len(ray_seeds) != len(set(ray_seeds)):
        raise ValueError("duplicate ray seeds")


def natural_key(value: str) -> tuple[str, int, str]:
    digits = "".join(ch if ch.isdigit() else " " for ch in value).split()
    return value.split("_LSystem_")[0], int(digits[-1]) if digits else -1, value


def unique_output_dir(path: Path) -> Path:
    if not path.exists():
        return path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.name}_{timestamp}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(file for file in path.rglob("*") if file.is_file())
    for file in files:
        digest.update(file.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def checkpoint_fingerprint(
    args: argparse.Namespace,
    date: str,
    scene_asset_path: str,
    expected_plant_count: int,
    assets_sha256: str | None = None,
) -> dict[str, object]:
    assets = args.project.parent / "Assets"
    binding_dir = args.build_dir / "PythonBinding" / args.config
    python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    bindings = list(binding_dir.glob(f"PyDigitalAgriculture.{python_tag}-*.pyd"))
    if len(bindings) != 1:
        raise FileNotFoundError(
            f"expected one {python_tag} PyDigitalAgriculture binding in {binding_dir}, got {len(bindings)}"
        )
    inputs = {
        "driver": Path(__file__).resolve(),
        "scene_handoff_api": Path(__file__).with_name("sorghum_4x10_scene.py"),
        "asset_layout_module": Path(__file__).with_name("sorghum_asset_layout.py"),
        "python_binding": bindings[0],
        "engine_sdk": binding_dir / "EvoEngine_SDK.dll",
        "cuda_module": binding_dir / "CudaModuleService.dll",
        "digital_agriculture_package": args.runtime_package_dir
        / "DigitalAgriculturePackage.dll",
        "lsystem_package": args.runtime_package_dir / "LSystemPackage.dll",
        "project": args.project,
        "manifest": args.source_root / "field_manifest.csv",
        "scene": assets / scene_asset_path,
        "reference_scene": assets / args.reference_scene,
        "btx_descriptor": assets / calibrated_descriptor(args, date, "BTX"),
        "pawaga_descriptor": assets / calibrated_descriptor(args, date, "Pawaga"),
    }
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "checkpoint input file(s) missing: " + ", ".join(missing)
        )
    return {
        "version": CHECKPOINT_VERSION,
        "date": date,
        "date_order": list(DATE_ORDER),
        "scene_asset_path": scene_asset_path,
        "expected_plant_count": expected_plant_count,
        "replicates": args.replicates,
        "probes_per_panel": args.probes_per_panel,
        "samples": args.samples,
        "bounces": args.bounces,
        "seed": args.seed,
        "geometry_seed": args.geometry_seed,
        "geometry_seed_stride": args.geometry_seed_stride,
        "push_normal_distance": args.push_normal_distance,
        "middle_panel_height_fraction": args.middle_panel_height_fraction,
        "after_panel_move_frames": args.after_panel_move_frames,
        "assets_tree": {
            "path": str(assets.resolve()),
            "sha256": assets_sha256 or directory_sha256(assets),
        },
        "inputs": {
            name: {"path": str(path.resolve()), "sha256": file_sha256(path)}
            for name, path in inputs.items()
        },
    }


def save_checkpoint(
    path: Path,
    fingerprint: dict[str, object],
    next_replicate: int,
    accumulators: dict[tuple[str, str, int], SummaryAccumulator],
) -> None:
    payload = {
        "fingerprint": fingerprint,
        "next_replicate": next_replicate,
        "accumulators": [
            {"key": list(key), "value": accumulator.to_dict()}
            for key, accumulator in sorted(accumulators.items())
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)


def load_checkpoint(
    path: Path, fingerprint: dict[str, object]
) -> tuple[int, dict[tuple[str, str, int], SummaryAccumulator]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fingerprint") != fingerprint:
        raise ValueError(f"checkpoint configuration or inputs changed: {path}")
    accumulators = {
        (
            str(entry["key"][0]),
            str(entry["key"][1]),
            int(entry["key"][2]),
        ): SummaryAccumulator.from_dict(entry["value"])
        for entry in payload.get("accumulators", [])
    }
    next_replicate = int(payload["next_replicate"])
    if next_replicate < 0:
        raise ValueError(f"invalid checkpoint replicate: {next_replicate}")
    if any(
        accumulator.count != next_replicate for accumulator in accumulators.values()
    ):
        raise ValueError(f"checkpoint accumulator count mismatch: {path}")
    return next_replicate, accumulators


def tail_text(path: Path, line_count: int = 80) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def collect_default_scene_side_effects(project: Path) -> set[Path]:
    assets = project.resolve().parent / "Assets"
    return {path.resolve() for path in assets.glob("New Scene*.evescene*")}


def cleanup_new_default_scene_side_effects(project: Path, before: set[Path]) -> None:
    assets = (project.resolve().parent / "Assets").resolve()
    for path in sorted(collect_default_scene_side_effects(project) - before):
        resolved = path.resolve()
        try:
            resolved.relative_to(assets)
        except ValueError:
            continue
        resolved.unlink(missing_ok=True)


def vec3(value: object) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def float_value(row: dict[str, str], column: str) -> float:
    return float(row[column])


def int_value(row: dict[str, str], column: str) -> int:
    return int(float(row[column]))


def load_height_manifest(source_root: Path, dates: list[str]) -> list[dict[str, str]]:
    path = source_root / "field_manifest.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"height-fit manifest not found: {path}\n"
            "Install the Sorghum L-System resource bundle so "
            "Resources/DigitalAgricultureProject/Assets/GeneratedAssets/Reports/field_manifest.csv exists, "
            "or pass --source-root."
        )
    rows = [row for row in read_csv(path) if row["date"] in dates]
    missing = [date for date in dates if not any(row["date"] == date for row in rows)]
    if missing:
        raise ValueError(
            f"height-fit manifest is missing date(s): {', '.join(missing)}"
        )
    return rows


def calibrated_descriptor(args: argparse.Namespace, date: str, cultivar: str) -> str:
    return descriptor_path(args.calibrated_descriptor_root, date, cultivar).as_posix()


def plant_counts_by_date(
    rows: list[dict[str, str]], dates: list[str]
) -> dict[str, int]:
    counts = {date: sum(row["date"] == date for row in rows) for date in dates}
    if any(count != 40 for count in counts.values()):
        raise ValueError(f"each 4x10 scene must contain exactly 40 plants: {counts}")
    for date in dates:
        date_rows = [row for row in rows if row["date"] == date]
        cultivar_counts = {
            cultivar: sum(row["cultivar"] == cultivar for row in date_rows)
            for cultivar in CULTIVARS
        }
        if cultivar_counts != {cultivar: 20 for cultivar in CULTIVARS}:
            raise ValueError(
                f"{date} must contain exactly 20 plants per cultivar: {cultivar_counts}"
            )
        plant_names = [row["plant_name"] for row in date_rows]
        position_names = [row["base_plant_name"] for row in date_rows]
        if len(set(plant_names)) != 40 or len(set(position_names)) != 40:
            raise ValueError(f"{date} must contain 40 unique rooted plant positions")
        if any(int_value(row, "cluster_index") != 0 for row in date_rows):
            raise ValueError(f"{date} contains legacy clustered plant instances")
    return counts


def plant_rows_from_manifest(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        output.append(
            {
                "date": row["date"],
                "cultivar": row["cultivar"],
                "original_position_id": row["base_plant_name"],
                "plant_id": row["plant_name"],
                "cluster_member_number": 1,
                "plants_at_original_position": 1,
                "plant_height_m": float_value(row, "final_height_m"),
                "source_final_height_m": float_value(row, "source_final_height_m"),
                "target_height_m": float_value(row, "target_height_m"),
                "height_error_m": float_value(row, "height_error_m"),
                "source_height_error_m": float_value(row, "source_height_error_m"),
                "leaf_count": int_value(row, "leaf_count"),
                "source_leaf_count": int_value(row, "source_leaf_count"),
                "primary_tiller_count": int_value(row, "primary_tiller_count"),
                "target_leaf_modules_mean": float_value(row, "leaf_modules_mean"),
                "target_leaf_modules_stdev": float_value(row, "leaf_modules_deviation"),
                "clump_mean_height_m": float_value(row, "clump_mean_height_m"),
                "source_clump_mean_height_m": float_value(
                    row, "source_clump_mean_height_m"
                ),
                "source_leaf_thickness_m": float_value(row, "source_leaf_thickness_m"),
                "leaf_thickness_scale": float_value(row, "leaf_thickness_scale"),
                "leaf_thickness_m": float_value(row, "leaf_thickness_m"),
                "source_leaf_width_scale": float_value(row, "source_leaf_width_scale"),
                "leaf_width_scale": float_value(row, "leaf_width_scale"),
                "source_cluster_offset_x_m": float_value(
                    row, "source_cluster_offset_x_m"
                ),
                "source_cluster_offset_z_m": float_value(
                    row, "source_cluster_offset_z_m"
                ),
                "source_cluster_offset_radius_m": float_value(
                    row, "source_cluster_offset_radius_m"
                ),
                "cluster_offset_x_m": float_value(row, "cluster_offset_x_m"),
                "cluster_offset_z_m": float_value(row, "cluster_offset_z_m"),
                "cluster_offset_radius_m": float_value(row, "cluster_offset_radius_m"),
                "cluster_radius_scale": float_value(row, "cluster_radius_scale"),
                "cluster_outward_lean_degrees": float_value(
                    row, "cluster_outward_lean_degrees"
                ),
                "middle_parbar_top_elevation_m": float_value(
                    row, "middle_parbar_top_elevation_m"
                ),
                "source_middle_parbar_top_elevation_m": float_value(
                    row, "source_middle_parbar_top_elevation_m"
                ),
                "source_scene": row["scene_asset_path"],
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["date"],
            row["cultivar"],
            natural_key(str(row["original_position_id"])),
            int(row["cluster_member_number"]),
        ),
    )


def clump_rows_from_plants(
    plant_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in plant_rows:
        groups[
            (str(row["date"]), str(row["cultivar"]), str(row["original_position_id"]))
        ].append(row)

    output: list[dict[str, object]] = []
    for (date, cultivar, original_position_id), members in groups.items():
        members = sorted(members, key=lambda row: int(row["cluster_member_number"]))
        heights = [float(row["plant_height_m"]) for row in members]
        leaves = [int(row["leaf_count"]) for row in members]
        anchor = next(
            (row for row in members if int(row["cluster_member_number"]) == 1),
            members[0],
        )
        output.append(
            {
                "date": date,
                "cultivar": cultivar,
                "original_position_id": original_position_id,
                "plants_at_original_position": len(members),
                "extra_clustered_plants": max(0, len(members) - 1),
                "anchor_plant_id": anchor["plant_id"],
                "anchor_plant_height_m": anchor["plant_height_m"],
                "mean_plant_height_m": statistics.fmean(heights),
                "min_plant_height_m": min(heights),
                "max_plant_height_m": max(heights),
                "mean_leaf_count": statistics.fmean(leaves),
                "min_leaf_count": min(leaves),
                "max_leaf_count": max(leaves),
                "member_plant_ids": ";".join(str(row["plant_id"]) for row in members),
                "target_height_m": members[0]["target_height_m"],
                "target_leaf_modules_mean": members[0]["target_leaf_modules_mean"],
                "target_leaf_modules_stdev": members[0]["target_leaf_modules_stdev"],
                "middle_parbar_top_elevation_m": members[0][
                    "middle_parbar_top_elevation_m"
                ],
                "source_scene": members[0]["source_scene"],
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["date"],
            row["cultivar"],
            natural_key(str(row["original_position_id"])),
        ),
    )


def sensor_values(record: object) -> dict[str, float]:
    position = vec3(record.position)
    normal = vec3(record.normal)
    return {
        "illumination_total_simulated": float(record.scalar),
        "probe_position_x_m": position[0],
        "probe_position_y_m": position[1],
        "probe_position_z_m": position[2],
        "probe_normal_x": normal[0],
        "probe_normal_y": normal[1],
        "probe_normal_z": normal[2],
        "represented_clump_count": float(record.represented_plant_count),
        "average_represented_root_elevation_m": float(
            record.average_represented_root_elevation_m
        ),
        "average_represented_plant_height_m": float(
            record.average_represented_plant_height_m
        ),
        "height_fraction_of_average_height": float(
            record.height_fraction_of_average_height
        ),
        "sensor_top_elevation_m": float(record.sensor_top_elevation_m),
    }


def sensor_base_row(
    args: argparse.Namespace, date: str, scene_asset_path: str, record: object
) -> dict[str, object]:
    return {
        "date": date,
        "cultivar": record.cultivar,
        "source_scene": scene_asset_path,
        "reference_scene": args.reference_scene,
        "calibrated_btx_descriptor": calibrated_descriptor(args, date, "BTX"),
        "calibrated_pawaga_descriptor": calibrated_descriptor(args, date, "Pawaga"),
        "sensor_bar_level": record.sensor_bar_level,
        "probe_number": int(record.column) + 1,
        "height_rule": record.height_rule,
    }


def expected_sensor_keys(probes_per_panel: int) -> set[tuple[str, str, int]]:
    return {
        (cultivar, level, column)
        for cultivar in CULTIVARS
        for level in BAR_LEVELS
        for column in range(probes_per_panel)
    }


def validate_sensor_records(records: list[object], probes_per_panel: int) -> None:
    keys = [
        (str(record.cultivar), str(record.sensor_bar_level), int(record.column))
        for record in records
    ]
    expected = expected_sensor_keys(probes_per_panel)
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate PARBAR sensor record key")
    missing = expected - set(keys)
    unexpected = set(keys) - expected
    if missing or unexpected:
        raise ValueError(
            f"PARBAR sensor record keys differ: missing={len(missing)}, unexpected={len(unexpected)}"
        )


def validate_checkpoint_accumulators(
    accumulators: dict[tuple[str, str, int], SummaryAccumulator],
    next_replicate: int,
    probes_per_panel: int,
    checkpoint_path: Path,
) -> None:
    if next_replicate and set(accumulators) != expected_sensor_keys(probes_per_panel):
        raise ValueError(f"checkpoint probe keys are incomplete: {checkpoint_path}")


def sensor_rows_for_date(
    evo: object,
    args: argparse.Namespace,
    scene: FourByTenScene,
) -> list[dict[str, object]]:
    date = scene.date
    scene_asset_path = scene.scene_asset_path
    args.expected_plant_count = scene.plant_count
    fingerprint = checkpoint_fingerprint(
        args, date, scene_asset_path, scene.plant_count
    )
    checkpoint_path = args.checkpoint_dir / f"{date}.json"
    start_replicate = 0
    accumulators: dict[tuple[str, str, int], SummaryAccumulator] = {}
    if checkpoint_path.exists():
        if not args.resume:
            raise FileExistsError(
                f"checkpoint already exists; pass --resume or choose another output: {checkpoint_path}"
            )
        start_replicate, accumulators = load_checkpoint(checkpoint_path, fingerprint)
        print(
            f"{date}: resumed_at_replicate={start_replicate} checkpoint={checkpoint_path}",
            flush=True,
        )
    if start_replicate > args.replicates:
        raise ValueError(
            f"checkpoint is beyond requested replicate count: {start_replicate}"
        )
    validate_checkpoint_accumulators(
        accumulators, start_replicate, args.probes_per_panel, checkpoint_path
    )
    if start_replicate == args.replicates:
        rows = [accumulator.row(args) for accumulator in accumulators.values()]
        return sorted(
            rows,
            key=lambda row: (
                row["date"],
                row["cultivar"],
                BAR_LEVELS.index(str(row["sensor_bar_level"])),
                int(row["probe_number"]),
            ),
        )
    stop_replicate = replicate_batch_stop(
        start_replicate, args.replicates, args.engine_batch_size
    )
    print(
        f"{date}: engine_batch={start_replicate + 1}-{stop_replicate}/{args.replicates}",
        flush=True,
    )

    project_bytes = args.project.read_bytes()
    side_effects_before = collect_default_scene_side_effects(args.project)
    sensors = None
    try:
        prepare_4x10_scene(
            evo,
            args.project,
            args.runtime_package_dir,
            scene,
            geometry_seed_for_replicate(
                args.geometry_seed, args.geometry_seed_stride, date, 0
            ),
            args.middle_panel_height_fraction,
            args.after_panel_move_frames,
            args.max_wait_frames,
        )
        sensors = evo.CreateParbarTopFaceSensorGroup(args.probes_per_panel)
        next_replicate = start_replicate
        started = time.perf_counter()
        try:
            for replicate in range(start_replicate, stop_replicate):
                geometry_seed = geometry_seed_for_replicate(
                    args.geometry_seed, args.geometry_seed_stride, date, replicate
                )
                ray_seed = ray_seed_for_replicate(args.seed, date, replicate)
                grow_4x10_scene(evo, scene, geometry_seed, args.max_wait_frames)
                evo.EstimatePARSensors(
                    sensors,
                    args.samples,
                    args.bounces,
                    args.push_normal_distance,
                    ray_seed,
                )
                records = evo.GetParbarTopFaceSensorResults(
                    sensors, args.probes_per_panel
                )
                validate_sensor_records(records, args.probes_per_panel)
                for record in records:
                    key = (
                        str(record.cultivar),
                        str(record.sensor_bar_level),
                        int(record.column),
                    )
                    if key not in accumulators:
                        accumulators[key] = SummaryAccumulator(
                            sensor_base_row(args, date, scene_asset_path, record)
                        )
                    accumulators[key].add(sensor_values(record))
                next_replicate = replicate + 1
                checkpoint_due = (
                    next_replicate % args.checkpoint_interval == 0
                    or next_replicate == stop_replicate
                )
                progress_due = (
                    next_replicate % args.progress_interval == 0
                    or next_replicate == stop_replicate
                )
                if checkpoint_due:
                    save_checkpoint(
                        checkpoint_path, fingerprint, next_replicate, accumulators
                    )
                if progress_due:
                    elapsed = time.perf_counter() - started
                    completed = next_replicate - start_replicate
                    remaining = (
                        (args.replicates - next_replicate) * elapsed / completed
                        if completed
                        else 0.0
                    )
                    print(
                        f"{date}: replicates={next_replicate}/{args.replicates} "
                        f"elapsed_s={elapsed:.1f} eta_s={remaining:.1f}",
                        flush=True,
                    )
        finally:
            if accumulators and all(
                accumulator.count == next_replicate
                for accumulator in accumulators.values()
            ):
                save_checkpoint(
                    checkpoint_path, fingerprint, next_replicate, accumulators
                )
        rows = (
            [accumulator.row(args) for accumulator in accumulators.values()]
            if next_replicate == args.replicates
            else []
        )
    finally:
        try:
            if sensors is not None and hasattr(evo, "DeleteRuntimeAsset"):
                evo.DeleteRuntimeAsset(sensors)
        except Exception:
            pass
        try:
            evo.Terminate()
        finally:
            args.project.write_bytes(project_bytes)
            cleanup_new_default_scene_side_effects(args.project, side_effects_before)
    return sorted(
        rows,
        key=lambda row: (
            row["date"],
            row["cultivar"],
            BAR_LEVELS.index(str(row["sensor_bar_level"])),
            int(row["probe_number"]),
        ),
    )


def worker_command(
    args: argparse.Namespace,
    date: str,
    sensor_csv: Path,
    worker_lock: Path,
    resume: bool,
) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(args.repo_root),
        "--build-dir",
        str(args.build_dir),
        "--config",
        args.config,
        "--runtime-package-dir",
        str(args.runtime_package_dir),
        "--project",
        str(args.project),
        "--source-root",
        str(args.source_root),
        "--calibrated-descriptor-root",
        str(args.calibrated_descriptor_root),
        "--reference-scene",
        args.reference_scene,
        "--output-dir",
        str(args.output_dir),
        "--dates",
        date,
        "--probes-per-panel",
        str(args.probes_per_panel),
        "--replicates",
        str(args.replicates),
        "--samples",
        str(args.samples),
        "--bounces",
        str(args.bounces),
        "--seed",
        str(args.seed),
        "--geometry-seed",
        str(args.geometry_seed),
        "--geometry-seed-stride",
        str(args.geometry_seed_stride),
        "--push-normal-distance",
        str(args.push_normal_distance),
        "--middle-panel-height-fraction",
        str(args.middle_panel_height_fraction),
        "--max-wait-frames",
        str(args.max_wait_frames),
        "--after-panel-move-frames",
        str(args.after_panel_move_frames),
        "--checkpoint-dir",
        str(args.checkpoint_dir),
        "--checkpoint-interval",
        str(args.checkpoint_interval),
        "--progress-interval",
        str(args.progress_interval),
        "--engine-batch-size",
        str(args.engine_batch_size),
        "--worker-sensor-csv",
        str(sensor_csv),
        "--worker-lock",
        str(worker_lock),
    ] + (["--resume"] if resume else [])


def verify_campaign_fingerprints(
    args: argparse.Namespace, fingerprints: dict[str, dict[str, object]]
) -> None:
    assets_sha256 = directory_sha256(args.project.parent / "Assets")
    current = {
        date: checkpoint_fingerprint(
            args,
            date,
            str(fingerprint["scene_asset_path"]),
            int(fingerprint["expected_plant_count"]),
            assets_sha256,
        )
        for date, fingerprint in fingerprints.items()
    }
    if current != fingerprints:
        raise RuntimeError(
            "campaign code, runtime, inputs, or settings changed while the run was active"
        )


def run_worker_process(
    command: list[str], cwd: Path, log_path: Path, append: bool, date: str
) -> int:
    with log_path.open(
        "a" if append else "w", encoding="utf-8", errors="replace"
    ) as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(f"[{date}] {line}", end="", flush=True)
            return process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def sensor_rows_with_workers(
    args: argparse.Namespace, fingerprints: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    worker_dir = args.checkpoint_dir / "workers"
    worker_dir.mkdir(parents=True, exist_ok=True)
    return sensor_rows_with_workers_locked(args, fingerprints, worker_dir)


def sensor_rows_with_workers_locked(
    args: argparse.Namespace,
    fingerprints: dict[str, dict[str, object]],
    worker_dir: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for date in args.dates:
        sensor_csv = worker_dir / f"{date}_sensors.csv"
        log_path = worker_dir / f"{date}_worker.log"
        worker_lock = worker_dir / f"{date}.lock"
        resume_worker = args.resume
        while True:
            verify_campaign_fingerprints(args, fingerprints)
            with exclusive_file_lock(
                worker_lock,
                f"{date} still has an active worker; wait before resuming",
            ):
                pass
            returncode = run_worker_process(
                worker_command(args, date, sensor_csv, worker_lock, resume_worker),
                args.repo_root,
                log_path,
                resume_worker,
                date,
            )
            if returncode != 0:
                raise RuntimeError(
                    f"{date} worker failed with exit code {returncode}. Log: {log_path}\n{tail_text(log_path)}"
                )
            verify_campaign_fingerprints(args, fingerprints)
            checkpoint_path = args.checkpoint_dir / f"{date}.json"
            next_replicate = int(
                json.loads(checkpoint_path.read_text(encoding="utf-8"))[
                    "next_replicate"
                ]
            )
            if next_replicate == args.replicates:
                break
            if args.engine_batch_size == 0 or next_replicate > args.replicates:
                raise RuntimeError(
                    f"{date} worker stopped at invalid replicate {next_replicate}"
                )
            print(
                f"{date}: restarting engine after replicate {next_replicate}",
                flush=True,
            )
            resume_worker = True
        date_rows = read_csv(sensor_csv)
        if len(date_rows) != len(CULTIVARS) * len(BAR_LEVELS) * args.probes_per_panel:
            raise RuntimeError(f"{date} worker wrote {len(date_rows)} sensor rows")
        print(f"{date}: sensor_rows={len(date_rows)} log={log_path}")
        rows.extend(date_rows)
    return sorted(
        rows,
        key=lambda row: (
            row["date"],
            row["cultivar"],
            BAR_LEVELS.index(str(row["sensor_bar_level"])),
            int(row["probe_number"]),
        ),
    )


def write_split_outputs(
    output_dir: Path,
    sensor_rows: list[dict[str, object]],
    plant_rows: list[dict[str, object]],
    clump_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    index_rows: list[dict[str, object]] = []

    def write_named(
        relative_path: Path,
        columns: list[str],
        rows: list[dict[str, object]],
        description: str,
    ) -> None:
        write_csv(output_dir / relative_path, columns, rows)
        index_rows.append(
            {
                "file": relative_path.as_posix(),
                "row_count": len(rows),
                "description": description,
            }
        )

    write_named(
        Path("all_parbar_sensors_summary.csv"),
        SENSOR_COLUMNS,
        sensor_rows,
        "All replicated PARBAR sensor probe summary rows.",
    )
    write_named(
        Path("all_individual_plants_long.csv"),
        PLANT_COLUMNS,
        plant_rows,
        "All fitted individual simulated plant layout/target rows.",
    )
    write_named(
        Path("all_clumps_long.csv"),
        CLUMP_COLUMNS,
        clump_rows,
        "All original-position clump layout/target summary rows.",
    )

    for date in DATE_ORDER:
        for cultivar in CULTIVARS:
            sensors = [
                row
                for row in sensor_rows
                if row["date"] == date and row["cultivar"] == cultivar
            ]
            plants = [
                row
                for row in plant_rows
                if row["date"] == date and row["cultivar"] == cultivar
            ]
            clumps = [
                row
                for row in clump_rows
                if row["date"] == date and row["cultivar"] == cultivar
            ]
            if sensors:
                write_named(
                    Path("sensors") / f"{date}_{cultivar}_parbar_sensors_summary.csv",
                    SENSOR_COLUMNS,
                    sensors,
                    f"{date} {cultivar} replicated PARBAR sensor probe summaries.",
                )
            if plants:
                write_named(
                    Path("plants") / f"{date}_{cultivar}_individual_plants.csv",
                    PLANT_COLUMNS,
                    plants,
                    f"{date} {cultivar} fitted individual simulated plant layout rows.",
                )
            if clumps:
                write_named(
                    Path("clumps") / f"{date}_{cultivar}_clump_summary.csv",
                    CLUMP_COLUMNS,
                    clumps,
                    f"{date} {cultivar} original-position clump summaries.",
                )
    return sorted(index_rows, key=lambda row: str(row["file"]))


def validate_outputs(
    sensor_rows: list[dict[str, object]],
    plant_rows: list[dict[str, object]],
    clump_rows: list[dict[str, object]],
    args: argparse.Namespace,
) -> None:
    expected_sensor_rows = (
        len(args.dates) * len(CULTIVARS) * len(BAR_LEVELS) * args.probes_per_panel
    )
    if len(sensor_rows) != expected_sensor_rows:
        raise ValueError(
            f"expected {expected_sensor_rows} sensor rows, got {len(sensor_rows)}"
        )
    for date in args.dates:
        date_rows = [row for row in sensor_rows if row["date"] == date]
        keys = {
            (
                str(row["cultivar"]),
                str(row["sensor_bar_level"]),
                int(row["probe_number"]) - 1,
            )
            for row in date_rows
        }
        if keys != expected_sensor_keys(args.probes_per_panel) or len(keys) != len(
            date_rows
        ):
            raise ValueError(f"{date}: summary probe keys are incomplete or duplicated")
        for row in date_rows:
            if int(row["replicate_count"]) != args.replicates:
                raise ValueError(f"{date}: summary row has the wrong replicate count")
            mean = float(row["illumination_total_simulated_mean"])
            std = float(row["illumination_total_simulated_std"])
            sem = float(row["illumination_total_simulated_sem"])
            ci_low = float(row["illumination_total_simulated_ci95_low"])
            ci_high = float(row["illumination_total_simulated_ci95_high"])
            if not all(
                math.isfinite(value) for value in (mean, std, sem, ci_low, ci_high)
            ):
                raise ValueError(f"{date}: non-finite illumination summary")
            if mean < 0.0 or std < 0.0 or sem < 0.0 or ci_low > mean or ci_high < mean:
                raise ValueError(f"{date}: invalid illumination summary")

    for date in args.dates:
        for cultivar in CULTIVARS:
            plants = [
                row
                for row in plant_rows
                if row["date"] == date and row["cultivar"] == cultivar
            ]
            clumps = [
                row
                for row in clump_rows
                if row["date"] == date and row["cultivar"] == cultivar
            ]
            expected_clumps = len({str(row["original_position_id"]) for row in plants})
            if not plants:
                raise ValueError(f"{date} {cultivar}: no plant rows")
            if len(clumps) != expected_clumps:
                raise ValueError(
                    f"{date} {cultivar}: expected {expected_clumps} position rows, got {len(clumps)}"
                )


def write_readme(
    path: Path,
    args: argparse.Namespace,
    sensor_rows: list[dict[str, object]],
    plant_rows: list[dict[str, object]],
    clump_rows: list[dict[str, object]],
) -> None:
    geometry_first = min(int(row["geometry_seed_base"]) for row in sensor_rows)
    geometry_last = max(int(row["geometry_seed_last"]) for row in sensor_rows)
    ray_first = min(int(row["ray_seed_base"]) for row in sensor_rows)
    ray_last = max(int(row["ray_seed_last"]) for row in sensor_rows)
    text = f"""# Replicated 4x10 PARBAR Illumination Handoff

This folder contains replicated simulated PARBAR sensor illumination summaries plus rooted-plant and planting-position metadata for five growth-stage L-System sorghum scenes.

## Files

- `sensors/`: one CSV per date and cultivar with replicated PARBAR probe summary rows.
- `plants/`: one CSV per date and cultivar with one row per simulated plant from the source layout manifest.
- `clumps/`: compatibility CSVs with one row per planting position; every current position contains one rooted plant with biological tillers.
- `all_parbar_sensors_summary.csv`, `all_individual_plants_long.csv`, and `all_clumps_long.csv`: combined versions of the split CSVs.
- `handoff_file_index.csv`: file list and row counts.
- `run_manifest.json`: exact command, workload counts, configuration, and SHA-256 driver, runtime, and input fingerprints.
- `replicate_seed_schedule.csv`: one auditable row per date and replicate with every plant-seed interval and ray seed.

Legacy cluster-named columns are retained for compatibility, but `plants_at_original_position` and
`cluster_member_number` are both `1`. `primary_tiller_count` describes the current 3-5 biological tillers.

## Illumination Values

`illumination_total_simulated_mean`, `_std`, `_sem`, and `_ci95_*` summarize EvoEngine's scalar estimate for point probes on the top face of simulated PARBAR sensor bars. `_std` is the sample standard deviation with denominator `n-1`; the 95% interval uses `mean +/- 1.96 * SEM`. The values are simulated relative light estimates, not calibrated physical PAR units.

Before tracing rays, each scene is repaired so `Ground Mesh` uses the PBR soil material through a `MeshRenderer`. Each date scene also swaps BTX and Pawaga plants onto the calibrated date/cultivar descriptors, then regenerates all 40 rooted plants for every replicate.

Geometry and ray seeds use the stable campaign slot `zero_based_replicate * 5 + growth_stage_index`, where `growth_stage_index` is zero-based in `replicate_seed_schedule.csv`. Consecutive per-plant seeds are assigned by EvoEngine, and the configured geometry stride prevents overlap between every growth stage, replicate, and plant.

Middle PARBAR panels are placed once per date scene at two-thirds of the represented rooted-plant height and remain fixed across replicate geometry draws.

Progress and ETA are streamed to the parent process. Atomic per-date checkpoints store the exact online statistics; pass `--resume` with the same output/checkpoint paths and configuration to continue an interrupted run. EvoEngine restarts after each configured replicate batch to bound memory without changing seeds or statistics. Resume refuses changed inputs or settings, and campaign/worker locks reject concurrent use of one checkpoint directory.

## Run Settings

- Source project: `{args.project}`
- Reference scene: `{args.reference_scene}`
- Source generated assets: `{args.source_root}`
- Calibrated descriptor root: `{args.calibrated_descriptor_root}`
- Dates: {', '.join(args.dates)}
- Replicates per summary row: {args.replicates}
- Probes per sensor bar: {args.probes_per_panel}
- Ray samples: {args.samples}
- Ray bounces: {args.bounces}
- Ray seed range: {ray_first} to {ray_last}
- Geometry plant-seed range: {geometry_first} to {geometry_last}
- Geometry seed stride: {args.geometry_seed_stride}
- EvoEngine replicate batch size: {args.engine_batch_size}
- Checkpoint directory: `{args.checkpoint_dir}`
- Push normal distance: {args.push_normal_distance} m

## Row Counts

- Sensor summary rows: {len(sensor_rows)}
- Individual plant rows: {len(plant_rows)}
- Clump summary rows: {len(clump_rows)}
"""
    path.write_text(text, encoding="utf-8")


def write_run_manifest(
    path: Path,
    args: argparse.Namespace,
    plant_counts: dict[str, int],
    fingerprints: dict[str, dict[str, object]],
) -> None:
    payload = {
        "scene_api_version": ".".join(map(str, SCENE_API_VERSION)),
        "coordinate_system": COORDINATE_SYSTEM,
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "dates": args.dates,
        "replicates_per_date": args.replicates,
        "plant_counts_per_replicate": plant_counts,
        "total_field_replicates": args.replicates * len(args.dates),
        "total_plant_instances": args.replicates * sum(plant_counts.values()),
        "fingerprints": fingerprints,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    source_project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--build-dir", type=Path, default=repo_root / "out" / "build" / "vs2026-x64"
    )
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument(
        "--runtime-package-dir",
        type=Path,
        default=repo_root
        / "out"
        / "build"
        / "vs2026-x64"
        / "EvoEngine_App"
        / "RelWithDebInfo"
        / "Packages",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=source_project_root / "test_lsystem_sorghum.eveproj",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=source_project_root / "Assets" / GENERATED_REPORT_ROOT,
    )
    parser.add_argument(
        "--calibrated-descriptor-root", type=Path, default=GENERATED_DESCRIPTOR_ROOT
    )
    parser.add_argument("--reference-scene", default=REFERENCE_4X10_SCENE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root
        / "out"
        / "handoff"
        / "sorghum_4x10_parbar_sensor_illumination_handoff",
    )
    parser.add_argument("--dates", type=parse_dates, default=list(DATE_ORDER))
    parser.add_argument("--probes-per-panel", type=int, default=100)
    parser.add_argument("--replicates", type=int, default=10000)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--bounces", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--geometry-seed", type=int, default=2_000_000)
    parser.add_argument("--geometry-seed-stride", type=int, default=1000)
    parser.add_argument("--push-normal-distance", type=float, default=0.001)
    parser.add_argument("--middle-panel-height-fraction", type=float, default=2.0 / 3.0)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--after-panel-move-frames", type=int, default=2)
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--checkpoint-interval", type=int, default=100)
    parser.add_argument("--progress-interval", type=int, default=10)
    parser.add_argument(
        "--engine-batch-size",
        type=int,
        default=10,
        help="Restart EvoEngine after this many replicates to bound memory; 0 disables restarts.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument(
        "--worker-sensor-csv", type=Path, default=None, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--worker-lock", type=Path, default=None, help=argparse.SUPPRESS
    )
    return parser


def run_parent_campaign(
    args: argparse.Namespace,
    plant_counts: dict[str, int],
    fingerprints: dict[str, dict[str, object]],
    plant_rows: list[dict[str, object]],
    clump_rows: list[dict[str, object]],
) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"output_dir={args.output_dir}", flush=True)
    print(f"checkpoint_dir={args.checkpoint_dir}", flush=True)
    run_manifest_path = args.output_dir / "run_manifest.json"
    if args.resume and run_manifest_path.exists():
        prior_fingerprints = json.loads(
            run_manifest_path.read_text(encoding="utf-8")
        ).get("fingerprints")
        if prior_fingerprints != fingerprints:
            raise ValueError(
                "resume refused because the frozen campaign fingerprints changed"
            )
    else:
        write_run_manifest(run_manifest_path, args, plant_counts, fingerprints)

    sensor_rows = sensor_rows_with_workers(args, fingerprints)
    validate_outputs(sensor_rows, plant_rows, clump_rows, args)
    index_rows = write_split_outputs(
        args.output_dir, sensor_rows, plant_rows, clump_rows
    )
    seed_rows = seed_schedule_rows(args, plant_counts)
    validate_seed_schedule(seed_rows)
    write_csv(
        args.output_dir / "replicate_seed_schedule.csv",
        SEED_SCHEDULE_COLUMNS,
        seed_rows,
    )
    index_rows.extend(
        [
            {
                "file": "replicate_seed_schedule.csv",
                "row_count": len(seed_rows),
                "description": "Globally unique plant and ray seed schedule for every replicate.",
            },
            {
                "file": "run_manifest.json",
                "row_count": 1,
                "description": "Reproducible run configuration and input hashes.",
            },
        ]
    )
    write_csv(
        args.output_dir / "handoff_file_index.csv",
        ["file", "row_count", "description"],
        index_rows,
    )
    write_readme(
        args.output_dir / "README.md", args, sensor_rows, plant_rows, clump_rows
    )

    print(f"output_dir={args.output_dir}")
    print(f"sensor_summary_rows={len(sensor_rows)}")
    print(f"plant_rows={len(plant_rows)}")
    print(f"clump_rows={len(clump_rows)}")


def main() -> None:
    args = build_parser().parse_args()
    args.repo_root = args.repo_root.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.project = args.project.resolve()
    args.source_root = args.source_root.resolve()
    requested_output_dir = args.output_dir.resolve()
    args.output_dir = (
        requested_output_dir
        if args.worker_sensor_csv or args.resume
        else unique_output_dir(requested_output_dir)
    )
    args.checkpoint_dir = (
        args.checkpoint_dir.resolve()
        if args.checkpoint_dir
        else args.output_dir.with_name(f".{args.output_dir.name}_checkpoints")
    )
    if args.worker_lock:
        args.worker_lock = args.worker_lock.resolve()
    if args.probes_per_panel <= 0:
        raise ValueError("--probes-per-panel must be positive")
    if args.replicates <= 0:
        raise ValueError("--replicates must be positive")
    if args.geometry_seed_stride <= 0:
        raise ValueError("--geometry-seed-stride must be positive")
    if args.samples <= 0 or args.bounces <= 0:
        raise ValueError("--samples and --bounces must be positive")
    if args.checkpoint_interval <= 0 or args.progress_interval <= 0:
        raise ValueError("checkpoint and progress intervals must be positive")
    if args.engine_batch_size < 0:
        raise ValueError("--engine-batch-size must be nonnegative")
    if args.smoke:
        args.dates = args.dates[:1]
        args.probes_per_panel = min(args.probes_per_panel, 2)
        args.replicates = min(args.replicates, 2)
        args.samples = min(args.samples, 1)

    manifest_rows = load_height_manifest(args.source_root, args.dates)
    plant_counts = plant_counts_by_date(manifest_rows, args.dates)
    scenes = {
        date: query_4x10_scene(
            args.source_root / "field_manifest.csv",
            args.calibrated_descriptor_root,
            date,
        )
        for date in args.dates
    }
    validate_seed_plan(
        args.geometry_seed,
        args.geometry_seed_stride,
        args.seed,
        args.replicates,
        plant_counts,
    )
    plant_rows = plant_rows_from_manifest(manifest_rows)
    clump_rows = clump_rows_from_plants(plant_rows)
    assets_sha256 = directory_sha256(args.project.parent / "Assets")
    fingerprints = {
        date: checkpoint_fingerprint(
            args,
            date,
            scenes[date].scene_asset_path,
            scenes[date].plant_count,
            assets_sha256,
        )
        for date in args.dates
    }
    if args.worker_sensor_csv:
        if len(args.dates) != 1:
            raise ValueError("--worker-sensor-csv requires exactly one date")
        if not args.worker_lock:
            raise ValueError("--worker-sensor-csv requires --worker-lock")
        with exclusive_file_lock(
            args.worker_lock,
            f"another engine worker is already using {args.worker_lock}",
        ):
            configure_engine_imports(args.repo_root, args.build_dir, args.config)
            import PyDigitalAgriculture as evo

            try:
                sensor_rows = sensor_rows_for_date(
                    evo,
                    args,
                    scenes[args.dates[0]],
                )
            finally:
                try:
                    evo.Terminate()
                except Exception:
                    pass
            if not sensor_rows:
                print(f"worker_checkpoint_only={args.dates[0]}")
                return
            validate_outputs(sensor_rows, plant_rows, clump_rows, args)
            write_csv(args.worker_sensor_csv, SENSOR_COLUMNS, sensor_rows)
            print(f"worker_sensor_csv={args.worker_sensor_csv}")
            print(f"sensor_rows={len(sensor_rows)}")
        return

    with exclusive_file_lock(
        args.checkpoint_dir / "campaign.lock",
        f"another campaign parent is already using {args.checkpoint_dir}",
    ):
        run_parent_campaign(args, plant_counts, fingerprints, plant_rows, clump_rows)


if __name__ == "__main__":
    main()
