#!/usr/bin/env python3
"""Render a multi-view visual-fidelity review for the two 2026 6x10 scenes."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, repo_root_from_script
from sorghum_2026_6x10_scene import SEEDS, SESSIONS
from sorghum_4x10_presentation import DEFAULT_PROFILE, apply_photo_grade, configure_lighting, set_ground_extension
from sorghum_render_4x10_mobile_review import (
    apply_camera,
    fit_camera,
    geometry_bounds,
    plant_detail_cameras,
    sha256,
)


OVERVIEW_VIEWS = ("perspective", "near_top_down", "row_side")
GENOTYPE_VIEW_PREFIXES = {
    "GenotypeA": "genotype_a",
    "GenotypeB": "genotype_b",
    "GenotypeC": "genotype_c",
}
VIEWS = OVERVIEW_VIEWS + tuple(
    f"{prefix}_{detail}"
    for prefix in GENOTYPE_VIEW_PREFIXES.values()
    for detail in ("plant", "basal", "leaf")
)
VIEW_LABELS = {
    "perspective": "Field oblique overview",
    "near_top_down": "Near-top-down canopy",
    "row_side": "Row-level overview",
    **{
        f"{prefix}_{detail}": f"{genotype.replace('Genotype', 'Genotype ')} {label}"
        for genotype, prefix in GENOTYPE_VIEW_PREFIXES.items()
        for detail, label in (
            ("plant", "representative plant"),
            ("basal", "culm, sheath, and tillers"),
            ("leaf", "mid-canopy leaf surface"),
        )
    },
}
SESSION_LABELS = {
    "MeasurementStage01": "Measurement Stage 1 | July 15-16, 2026",
    "MeasurementStage02": "Measurement Stage 2 | July 21, 2026",
}


def scene_asset(session: str) -> Path:
    return (
        Path("GeneratedAssets/Experiments")
        / EXPERIMENT_ID
        / "Scenes"
        / f"Sorghum_6x10_{session}.evescene"
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


def camera_for_view(bounds: object, view: str, aspect: float) -> dict[str, object]:
    if view == "perspective":
        return fit_camera(bounds, (1.0, 0.36, 1.0), (0.0, 1.0, 0.0), 42.0, aspect, 1.04)
    if view == "near_top_down":
        return fit_camera(bounds, (0.20, 1.0, 0.16), (0.0, 0.0, -1.0), 44.0, aspect, 1.06)
    if view == "row_side":
        return fit_camera(bounds, (0.08, 0.16, 1.0), (0.0, 1.0, 0.0), 46.0, aspect, 1.03)
    raise ValueError(f"unsupported view: {view}")


def cameras_for_scene(
    records: list[object], bounds: object, aspect: float
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    cameras = {view: camera_for_view(bounds, view, aspect) for view in OVERVIEW_VIEWS}
    representatives: dict[str, dict[str, object]] = {}
    for genotype, prefix in GENOTYPE_VIEW_PREFIXES.items():
        record = representative_review_plant(records, genotype)
        representatives[genotype] = {
            "name": record.name,
            "height_m": float(record.plant_height_m),
            "seed": int(record.seed),
        }
        for detail, camera in plant_detail_cameras(record, aspect).items():
            cameras[f"{prefix}_{detail}"] = camera
    return cameras, representatives


def representative_review_plant(records: list[object], genotype: str) -> object:
    """Pick a typical plant offset from the plot-center PARBAR mast."""
    selected = [record for record in records if record.cultivar == genotype]
    if not selected:
        raise ValueError(f"no plants found for {genotype}")
    x_values = [float(record.global_position.x) for record in selected]
    center_x = statistics.fmean(x_values)
    span_x = max(x_values) - min(x_values)
    target_offset = 0.28 * span_x
    median_height = statistics.median(float(record.plant_height_m) for record in selected)
    return min(
        selected,
        key=lambda record: (
            abs(abs(float(record.global_position.x) - center_x) - target_offset) / max(span_x, 0.01)
            + 0.35
            * abs(float(record.plant_height_m) - median_height)
            / max(median_height, 0.01),
            record.name,
        ),
    )


def make_multiview_contact_sheet(session: str, views: list[dict[str, object]], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    columns = 3
    rows = 4
    margin = 24
    tile_width = 560
    tile_height = 315
    label_height = 42
    title_height = 86
    canvas_width = margin + columns * (tile_width + margin)
    canvas_height = title_height + rows * (tile_height + label_height + margin)
    canvas = Image.new("RGB", (canvas_width, canvas_height), (17, 24, 28))
    draw = ImageDraw.Draw(canvas)
    regular = Path(r"C:\Windows\Fonts\segoeui.ttf")
    bold = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    if regular.exists() and bold.exists():
        title_font = ImageFont.truetype(str(bold), 34)
        label_font = ImageFont.truetype(str(regular), 23)
    else:
        title_font = label_font = ImageFont.load_default()
    draw.text((margin, 22), f"2026 Sorghum 6x10 | {SESSION_LABELS[session]}", font=title_font, fill=(245, 248, 247))
    by_view = {str(row["view"]): row for row in views}
    for index, view in enumerate(VIEWS):
        row_index, column_index = divmod(index, columns)
        x = margin + column_index * (tile_width + margin)
        y = title_height + row_index * (tile_height + label_height + margin)
        draw.text((x, y), VIEW_LABELS[view], font=label_font, fill=(218, 227, 225))
        with Image.open(str(by_view[view]["output"])).convert("RGB") as source:
            source.thumbnail((tile_width, tile_height))
            image_x = x + (tile_width - source.width) // 2
            image_y = y + label_height + (tile_height - source.height) // 2
            canvas.paste(source, (image_x, image_y))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def image_metrics(path: Path) -> dict[str, object]:
    from PIL import Image, ImageStat

    with Image.open(path).convert("RGB") as image:
        stat = ImageStat.Stat(image)
        luminance = ImageStat.Stat(image.convert("L"))
        pixels = image.width * image.height
        nearly_white = sum(1 for pixel in image.getdata() if min(pixel) >= 245)
        return {
            "size": [image.width, image.height],
            "rgb_mean": [float(value) for value in stat.mean],
            "rgb_stddev": [float(value) for value in stat.stddev],
            "luminance_mean": float(luminance.mean[0]),
            "luminance_stddev": float(luminance.stddev[0]),
            "nearly_white_fraction": nearly_white / pixels,
        }


def render_worker(args: argparse.Namespace) -> dict[str, object]:
    build_dir = args.build_dir.resolve()
    configure_engine_imports(build_dir, args.config)
    os.chdir(build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    project_bytes = args.project.read_bytes()
    scene = scene_asset(args.session)
    scene_path = args.project_root / "Assets" / scene
    result: dict[str, object] = {
        "session_id": args.session,
        "scene_asset_path": scene.as_posix(),
        "scene_sha256": sha256(scene_path),
        "views": [],
    }
    try:
        if not evo.RunLSystemSorghumProject(args.project, args.runtime_package_dir, scene):
            raise RuntimeError(f"failed to load {scene}")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError(f"{args.session}: scene did not become idle")
        if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
            raise RuntimeError(f"{args.session}: PBR soil context is invalid")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError(f"{args.session}: restored plant geometry did not become idle")
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        if len(records) != 60 or any(not record.has_geometry for record in records):
            raise RuntimeError(f"{args.session}: expected 60 measurable plants")
        if {int(record.seed) for record in records} != set(range(SEEDS[args.session], SEEDS[args.session] + 60)):
            raise RuntimeError(f"{args.session}: persisted deterministic seeds do not match the scene contract")
        if {record.cultivar for record in records} != {"GenotypeA", "GenotypeB", "GenotypeC"}:
            raise RuntimeError(f"{args.session}: genotype metadata mismatch")
        bounds = geometry_bounds(records)
        result["geometry_bounds"] = {"minimum": list(bounds.minimum), "maximum": list(bounds.maximum)}
        cameras, representatives = cameras_for_scene(records, bounds, args.width / args.height)
        result["representative_plants"] = representatives
        configure_lighting(evo)
        if set_ground_extension(evo, True) != 1:
            raise RuntimeError(f"{args.session}: presentation ground extension was not created")
        for view in VIEWS:
            camera = cameras[view]
            apply_camera(evo, camera)
            evo.LoopFrames(args.warmup_frames)
            raw = args.output_dir / "raw" / f"{args.session}_{view}.png"
            final = args.output_dir / f"{args.session}_{view}.png"
            raw.parent.mkdir(parents=True, exist_ok=True)
            if not evo.CaptureCurrentSceneRayTraced(
                args.width, args.height, raw, args.samples, args.bounces, DEFAULT_PROFILE.gamma
            ):
                raise RuntimeError(f"{args.session}: capture failed for {view}")
            apply_photo_grade(raw, final)
            metrics = image_metrics(final)
            if metrics["luminance_stddev"] < 5.0:
                raise RuntimeError(f"{args.session}: {view} render appears blank or flat")
            result["views"].append(
                {
                    "view": view,
                    "output": str(final.resolve()),
                    "raw_output": str(raw.resolve()),
                    "camera": camera,
                    "metrics": metrics,
                    "samples": args.samples,
                    "bounces": args.bounces,
                }
            )
        multiview = args.output_dir / f"{args.session}_multiview.png"
        make_multiview_contact_sheet(args.session, result["views"], multiview)
        result["multiview_output"] = str(multiview.resolve())
        result["multiview_sha256"] = sha256(multiview)
        result["multiview_metrics"] = image_metrics(multiview)
        report = args.output_dir / f"{args.session}_render_report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    finally:
        evo.Terminate()
        args.project.write_bytes(project_bytes)
    return result


def valid_session_report(args: argparse.Namespace, session: str) -> dict[str, object] | None:
    report_path = args.output_dir / f"{session}_render_report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected_scene = args.project_root / "Assets" / scene_asset(session)
        if report["session_id"] != session or report["scene_sha256"] != sha256(expected_scene):
            return None
        if {row["view"] for row in report["views"]} != set(VIEWS):
            return None
        for row in report["views"]:
            output = Path(row["output"])
            if not output.is_file() or image_metrics(output)["size"] != [args.width, args.height]:
                return None
        multiview = Path(report["multiview_output"])
        if not multiview.is_file() or sha256(multiview) != report["multiview_sha256"]:
            return None
        return report
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def run_parent(args: argparse.Namespace) -> None:
    reports = []
    project_bytes = args.project.read_bytes()
    launched_worker = False
    for session in SESSIONS:
        if not args.force:
            cached = valid_session_report(args, session)
            if cached is not None:
                cached["cache_reused"] = True
                reports.append(cached)
                continue
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--session",
            session,
            "--project-root",
            str(args.project_root),
            "--project",
            str(args.project),
            "--build-dir",
            str(args.build_dir),
            "--config",
            args.config,
            "--runtime-package-dir",
            str(args.runtime_package_dir),
            "--output-dir",
            str(args.output_dir),
            "--width",
            str(args.width),
            "--height",
            str(args.height),
            "--samples",
            str(args.samples),
            "--bounces",
            str(args.bounces),
            "--warmup-frames",
            str(args.warmup_frames),
            "--max-wait-frames",
            str(args.max_wait_frames),
        ]
        if launched_worker:
            time.sleep(15.0)
        for attempt in range(2):
            try:
                completed = subprocess.run(command, check=False)
            finally:
                args.project.write_bytes(project_bytes)
            launched_worker = True
            session_report = valid_session_report(args, session)
            if session_report is not None:
                session_report["worker_exit_status"] = completed.returncode
                if completed.returncode != 0:
                    session_report["worker_teardown_warning"] = (
                        "OptiX worker exited after the completed render report was flushed; outputs and scene hash validated."
                    )
                break
            if attempt == 0:
                time.sleep(15.0)
        if session_report is None:
            raise RuntimeError(f"{session} render worker produced no valid completion report")
        reports.append(session_report)
    combined = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "renderer": "EvoEngine_OptiX",
        "presentation_only": True,
        "scientific_scene_assets_modified": False,
        "sessions": reports,
    }
    report = args.output_dir / "render_report.json"
    report.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    print(report.resolve())


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    project_root = repo_root / "Resources" / "DigitalAgricultureProject"
    build_dir = repo_root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--session", choices=SESSIONS, help=argparse.SUPPRESS)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj")
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="RelWithDebInfo")
    parser.add_argument("--runtime-package-dir", type=Path, default=build_dir / "EvoEngine_App/RelWithDebInfo/Packages")
    parser.add_argument("--output-dir", type=Path, default=repo_root / "out/realism_review/sorghum_2026_6x10")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--bounces", type=int, default=4)
    parser.add_argument("--warmup-frames", type=int, default=3)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--force", action="store_true", help="ignore valid scene-hash render caches")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.worker:
        if not args.session:
            raise SystemExit("--worker requires --session")
        render_worker(args)
    else:
        run_parent(args)


if __name__ == "__main__":
    main()
