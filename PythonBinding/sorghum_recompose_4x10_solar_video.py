#!/usr/bin/env python3
"""Recompose validated PARBAR panels over already-rendered Evo solar scenes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from sorghum_4x10_illumination_video import (
    DEFAULT_SPEC,
    MANIFEST_NAME,
    PANEL_ORDER,
    VIDEO_NAME,
    VIDEO_VERSION,
    assemble_video,
    require_dependencies,
    solar_frame_for_replicate,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_control_rows(control_dir: Path) -> list[dict[str, str]]:
    path = control_dir / "all_parbar_sensors_summary.csv"
    if not path.is_file():
        raise FileNotFoundError(f"fixed-sun control CSV is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"fixed-sun control CSV is empty: {path}")
    return rows


def final_values(
    rows: list[dict[str, str]], date: str, probes_per_panel: int
) -> list[float]:
    lookup = {
        (
            row["date"],
            row["cultivar"],
            row["sensor_bar_level"],
            int(row["probe_number"]),
        ): float(row["illumination_total_simulated_mean"])
        for row in rows
    }
    values = []
    for cultivar, level in PANEL_ORDER:
        for probe_number in range(1, probes_per_panel + 1):
            key = (date, cultivar, level, probe_number)
            if key not in lookup:
                raise ValueError(f"fixed-sun control is missing sensor row: {key}")
            values.append(lookup[key])
    return values


def extract_unique_scenes(
    source_video: Path,
    destination: Path,
    unique_frame_count: int,
    encoded_frames_per_unique: int,
    ffmpeg: str,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    pattern = destination / "scene_%04d.png"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(source_video),
            "-vf",
            (
                f"select=not(mod(n\\,{encoded_frames_per_unique})),"
                f"crop={DEFAULT_SPEC.width}:{DEFAULT_SPEC.scene_height}:0:0"
            ),
            "-fps_mode",
            "vfr",
            str(pattern),
        ],
        check=True,
    )
    scenes = sorted(destination.glob("scene_*.png"))
    if len(scenes) != unique_frame_count:
        raise RuntimeError(
            f"extracted {len(scenes)} unique scenes; expected {unique_frame_count}"
        )
    with Image.open(scenes[0]) as image:
        if image.size != (DEFAULT_SPEC.width, DEFAULT_SPEC.scene_height):
            raise RuntimeError(f"extracted scene has the wrong dimensions: {image.size}")
    return scenes


def stage_recomposition(
    staging: Path,
    scenes: list[Path],
    dates: list[str],
    replicates: int,
    probes_per_panel: int,
    control_rows: list[dict[str, str]],
) -> None:
    source_index = 0
    for date in dates:
        values = final_values(control_rows, date, probes_per_panel)
        for replicate_number in range(1, replicates + 1):
            scene_path = staging / date / "scenes" / f"{replicate_number:04d}.png"
            means_path = staging / date / "means" / f"{replicate_number:04d}.json"
            scene_path.parent.mkdir(parents=True, exist_ok=True)
            means_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(scenes[source_index], scene_path)
            source_index += 1
            means_path.write_text(
                json.dumps(
                    {
                        "version": VIDEO_VERSION,
                        "date": date,
                        "replicate_number": replicate_number,
                        "probes_per_panel": probes_per_panel,
                        "render_samples": 4,
                        "render_bounces": 2,
                        "illumination_running_means": values,
                        "dashboard_status": (
                            f"validated final mean: {replicates} fixed-sun fields"
                        ),
                        "solar_sweep": solar_frame_for_replicate(
                            date, replicate_number, replicates
                        ).to_dict(),
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-video", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, default=None)
    parser.add_argument("--scientific-control-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_video = args.source_video.resolve()
    source_manifest_path = (
        args.source_manifest.resolve()
        if args.source_manifest
        else source_video.with_name(MANIFEST_NAME)
    )
    control_dir = args.scientific_control_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not source_video.is_file() or not source_manifest_path.is_file():
        raise FileNotFoundError("source Evo video or its manifest is missing")
    if (output_dir / "visualizations" / VIDEO_NAME).exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_dir}")

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    dates = list(source_manifest["dates"])
    replicates = int(source_manifest["replicates_per_date"])
    probes_per_panel = int(source_manifest["probes_per_panel"])
    encoded_per_date = int(source_manifest["encoded_frames_per_date"])
    if encoded_per_date % replicates:
        raise ValueError("source video does not hold each unique scene equally")
    hold = encoded_per_date // replicates
    unique_frame_count = len(dates) * replicates
    control_rows = read_control_rows(control_dir)
    ffmpeg, _ = require_dependencies()

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sorghum_4x10_recompose_", dir=output_dir.parent
    ) as temporary:
        temporary_root = Path(temporary)
        scenes = extract_unique_scenes(
            source_video,
            temporary_root / "extracted",
            unique_frame_count,
            hold,
            ffmpeg,
        )
        staging = temporary_root / "staging"
        stage_recomposition(
            staging, scenes, dates, replicates, probes_per_panel, control_rows
        )
        video_path, manifest_path = assemble_video(
            output_dir,
            staging,
            dates,
            replicates,
            probes_per_panel,
            control_rows,
            int(source_manifest["camera_render"]["samples"]),
            int(source_manifest["camera_render"]["bounces"]),
            DEFAULT_SPEC,
            solar_sweep=True,
            black_first_panel=False,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    control_csv = control_dir / "all_parbar_sensors_summary.csv"
    manifest.update(
        {
            "layout": (
                "reused Evo scene upper 80%; validated final fixed-sun PARBAR "
                "means lower 20% in a 3x2 grid"
            ),
            "dashboard_mode": "validated_final_fixed_reference_means",
            "scientific_capture_isolation": (
                "no scientific estimation occurs during recomposition; dashboard "
                "values come from the independent fixed-sun control"
            ),
            "recomposition": {
                "source_evo_video": str(source_video),
                "source_evo_video_sha256": sha256(source_video),
                "source_manifest": str(source_manifest_path),
                "source_manifest_sha256": sha256(source_manifest_path),
                "fixed_sun_control_csv": str(control_csv),
                "fixed_sun_control_csv_sha256": sha256(control_csv),
                "encoded_frames_per_unique_scene": hold,
                "scene_pixels_rerendered": False,
                "blender_used": False,
            },
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"video={video_path}")
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
