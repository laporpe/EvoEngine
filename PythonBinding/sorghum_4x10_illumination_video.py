#!/usr/bin/env python3
"""Capture and assemble the optional 4x10 illumination-convergence video."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


PANEL_ORDER = tuple(
    (cultivar, level)
    for cultivar in ("Pawaga", "BTX")
    for level in ("top", "middle", "bottom")
)
VIDEO_VERSION = 2
VIDEO_NAME = "sorghum_4x10_illumination_convergence.mp4"
MANIFEST_NAME = "sorghum_4x10_illumination_convergence.json"


@dataclass(frozen=True)
class VideoSpec:
    width: int = 1920
    height: int = 1080
    fps: int = 60
    seconds_per_date: int = 5
    scene_fraction: float = 0.8

    @property
    def scene_height(self) -> int:
        return round(self.height * self.scene_fraction)

    @property
    def frames_per_date(self) -> int:
        return self.fps * self.seconds_per_date


DEFAULT_SPEC = VideoSpec()


def validate_configuration(
    dates: list[str], replicates: int, probes_per_panel: int, spec: VideoSpec = DEFAULT_SPEC
) -> None:
    if not dates or replicates <= 0 or probes_per_panel <= 0:
        raise ValueError("video requires dates, replicates, and probes")
    if replicates > spec.frames_per_date:
        raise ValueError(
            f"cannot show {replicates} realizations in {spec.frames_per_date} video frames"
        )
    if (
        spec.width <= 0
        or spec.height <= 0
        or spec.width % 2
        or spec.height % 2
        or spec.scene_height <= 0
        or spec.scene_height >= spec.height
    ):
        raise ValueError("video dimensions must be positive, even, and reserve a lower dashboard")


def require_dependencies() -> tuple[str, str]:
    try:
        from PIL import Image  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "video output requires Pillow; install PythonBinding/requirements-mobile-review.txt"
        ) from error
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("video output requires ffmpeg and ffprobe on PATH")
    return ffmpeg, ffprobe


def staging_root(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / "video_staging"


def _vec_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(x + y for x, y in zip(a, b))


def _vec_scale(value: tuple[float, float, float], scale: float) -> tuple[float, float, float]:
    return tuple(component * scale for component in value)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-9:
        raise ValueError("cannot normalize a zero-length vector")
    return _vec_scale(value, 1.0 / length)


def _camera_from_scene(evo: object, spec: VideoSpec) -> dict[str, object]:
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    if len(records) != 40 or any(not record.has_geometry for record in records):
        raise RuntimeError("video framing requires 40 generated 4x10 plants")
    minimum = tuple(
        min(float(getattr(record.geometry_min_position, axis)) for record in records)
        for axis in ("x", "y", "z")
    )
    maximum = tuple(
        max(float(getattr(record.geometry_max_position, axis)) for record in records)
        for axis in ("x", "y", "z")
    )
    center = tuple((low + high) * 0.5 for low, high in zip(minimum, maximum))
    front = _vec_scale(_normalize((1.0, 0.65, 1.0)), -1.0)
    right = _normalize(_cross(front, (0.0, 1.0, 0.0)))
    up = _normalize(_cross(right, front))
    fov_degrees = 50.0
    tan_vertical = math.tan(math.radians(fov_degrees) * 0.5)
    tan_horizontal = tan_vertical * spec.width / spec.scene_height
    distance = 0.1
    for x in (minimum[0], maximum[0]):
        for y in (minimum[1], maximum[1]):
            for z in (minimum[2], maximum[2]):
                relative = (x - center[0], y - center[1], z - center[2])
                along_front = _dot(relative, front)
                distance = max(
                    distance,
                    abs(_dot(relative, right)) / tan_horizontal - along_front,
                    abs(_dot(relative, up)) / tan_vertical - along_front,
                )
    return {
        "position": list(_vec_add(center, _vec_scale(front, -1.18 * distance))),
        "target": list(center),
        "up": list(up),
        "fov_degrees": fov_degrees,
    }


def _vec3(evo: object, values: list[float]) -> object:
    result = evo.Vec3()
    result.x, result.y, result.z = values
    return result


def prepare_capture_camera(
    evo: object, root: Path, date: str, spec: VideoSpec = DEFAULT_SPEC
) -> None:
    path = root / date / "camera.json"
    if path.exists():
        camera = json.loads(path.read_text(encoding="utf-8"))
    else:
        camera = _camera_from_scene(evo, spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(camera, indent=2), encoding="utf-8")
    if not evo.SetMainCameraLookAt(
        _vec3(evo, camera["position"]),
        _vec3(evo, camera["target"]),
        _vec3(evo, camera["up"]),
        float(camera["fov_degrees"]),
    ):
        raise RuntimeError(f"failed to apply the video camera for {date}")


def running_means(accumulators: dict[tuple[str, str, int], object], probes_per_panel: int) -> list[float]:
    values = []
    for cultivar, level in PANEL_ORDER:
        for probe in range(probes_per_panel):
            values.append(
                float(
                    accumulators[(cultivar, level, probe)]
                    .stats["illumination_total_simulated"]
                    .mean
                )
            )
    if not values or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("video running means must be finite and non-negative")
    return values


def capture_realization(
    evo: object,
    root: Path,
    date: str,
    replicate_number: int,
    values: list[float],
    probes_per_panel: int,
    samples: int,
    bounces: int,
    spec: VideoSpec = DEFAULT_SPEC,
) -> None:
    from PIL import Image

    date_root = root / date
    scene_path = date_root / "scenes" / f"{replicate_number:04d}.png"
    means_path = date_root / "means" / f"{replicate_number:04d}.json"
    if len(values) != len(PANEL_ORDER) * probes_per_panel:
        raise ValueError("video snapshot has the wrong number of PARBAR means")
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    means_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_scene = scene_path.with_name(f"{scene_path.stem}.tmp.png")
    if not evo.CaptureCurrentSceneRayTraced(
        spec.width, spec.scene_height, temporary_scene, samples, bounces, 2.2
    ):
        raise RuntimeError(f"scene video capture failed: {date} replicate {replicate_number}")
    with Image.open(temporary_scene) as image:
        if image.size != (spec.width, spec.scene_height):
            raise RuntimeError(f"scene video capture has the wrong dimensions: {temporary_scene}")
    temporary_scene.replace(scene_path)
    payload = {
        "version": VIDEO_VERSION,
        "date": date,
        "replicate_number": replicate_number,
        "probes_per_panel": probes_per_panel,
        "render_samples": samples,
        "render_bounces": bounces,
        "panel_order": [list(key) for key in PANEL_ORDER],
        "illumination_running_means": values,
    }
    temporary_means = means_path.with_suffix(".json.tmp")
    temporary_means.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary_means.replace(means_path)


def validate_staged_prefix(
    root: Path, date: str, replicates: int, probes_per_panel: int
) -> None:
    for replicate_number in range(1, replicates + 1):
        scene_path = root / date / "scenes" / f"{replicate_number:04d}.png"
        means_path = root / date / "means" / f"{replicate_number:04d}.json"
        if not scene_path.is_file() or not means_path.is_file():
            raise RuntimeError(
                f"video resume is missing {date} realization {replicate_number} artifacts"
            )
        payload = json.loads(means_path.read_text(encoding="utf-8"))
        if (
            payload.get("date") != date
            or payload.get("replicate_number") != replicate_number
            or payload.get("probes_per_panel") != probes_per_panel
            or len(payload.get("illumination_running_means", []))
            != len(PANEL_ORDER) * probes_per_panel
        ):
            raise RuntimeError(f"invalid staged video means: {means_path}")


def frame_allocations(replicates: int, spec: VideoSpec = DEFAULT_SPEC) -> list[int]:
    validate_configuration(["date"], replicates, 1, spec)
    base, remainder = divmod(spec.frames_per_date, replicates)
    return [base + (index < remainder) for index in range(replicates)]


def _color(value: float, low: float, high: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, (value - low) / (high - low))) if high > low else 0.5
    start, middle, end = (201, 48, 44), (242, 223, 90), (35, 139, 69)
    if t < 0.5:
        t *= 2.0
        return tuple(round(a + (b - a) * t) for a, b in zip(start, middle))
    t = (t - 0.5) * 2.0
    return tuple(round(a + (b - a) * t) for a, b in zip(middle, end))


def _font(size: int) -> object:
    from PIL import ImageFont

    return ImageFont.load_default(size=size)


def compose_frame(
    scene_path: Path,
    output_path: Path,
    date: str,
    replicate_number: int,
    replicates: int,
    probes_per_panel: int,
    values: list[float] | None,
    scale_min: float,
    scale_max: float,
    spec: VideoSpec = DEFAULT_SPEC,
) -> None:
    from PIL import Image, ImageDraw

    with Image.open(scene_path).convert("RGB") as scene:
        if scene.size != (spec.width, spec.scene_height):
            raise RuntimeError(f"refusing to distort scene frame: {scene_path}")
        frame = Image.new("RGB", (spec.width, spec.height), (12, 17, 20))
        frame.paste(scene, (0, 0))
    draw = ImageDraw.Draw(frame)
    dashboard_top = spec.scene_height
    dashboard_height = spec.height - dashboard_top
    title_size = max(12, round(dashboard_height * 0.105))
    label_size = max(10, round(dashboard_height * 0.072))
    status = "waiting for first illumination" if values is None else f"running mean: {replicate_number} fields"
    draw.text(
        (24, dashboard_top + 5),
        f"{date}   |   field {replicate_number:03d}/{replicates:03d}   |   {status}",
        fill=(240, 244, 245),
        font=_font(title_size),
    )
    draw.text(
        (spec.width - 420, dashboard_top + 7),
        f"low {scale_min:.3g}   red  ->  green   {scale_max:.3g} high",
        fill=(205, 215, 218),
        font=_font(label_size),
    )
    left, right, column_gap = 24, 24, 18
    panel_width = (spec.width - left - right - 2 * column_gap) / 3.0
    title_band = max(25, round(dashboard_height * 0.18))
    bottom_margin = max(8, round(dashboard_height * 0.04))
    row_gap = max(8, round(dashboard_height * 0.045))
    row_height = (dashboard_height - title_band - bottom_margin - row_gap) / 2.0
    for panel_index, (cultivar, level) in enumerate(PANEL_ORDER):
        row, column = divmod(panel_index, 3)
        x0 = left + column * (panel_width + column_gap)
        y0 = dashboard_top + title_band + row * (row_height + row_gap)
        draw.text(
            (round(x0), round(y0)),
            f"{cultivar} · {level}",
            fill=(207, 220, 222),
            font=_font(label_size),
        )
        grid_top = y0 + max(15, round(row_height * 0.29))
        grid_bottom = y0 + row_height
        for probe in range(probes_per_panel):
            cell_left = round(x0 + probe * panel_width / probes_per_panel)
            cell_right = round(x0 + (probe + 1) * panel_width / probes_per_panel) - 1
            color = (
                (0, 0, 0)
                if values is None
                else _color(
                    values[panel_index * probes_per_panel + probe], scale_min, scale_max
                )
            )
            draw.rectangle(
                (cell_left, round(grid_top), max(cell_left, cell_right), round(grid_bottom)),
                fill=color,
            )
        draw.rectangle(
            (round(x0), round(grid_top), round(x0 + panel_width), round(grid_bottom)),
            outline=(82, 96, 100),
            width=1,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(output_path, "PNG")


def _final_scale(sensor_rows: list[dict[str, object]]) -> tuple[float, float]:
    values = [float(row["illumination_total_simulated_mean"]) for row in sensor_rows]
    if not values or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("final video color scale requires finite non-negative means")
    low, high = min(values), max(values)
    return (low, high) if high > low else (low, low + 1.0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_video(path: Path, ffprobe: str) -> dict[str, object]:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def assemble_video(
    output_dir: Path,
    root: Path,
    dates: list[str],
    replicates: int,
    probes_per_panel: int,
    sensor_rows: list[dict[str, object]],
    render_samples: int,
    render_bounces: int,
    spec: VideoSpec = DEFAULT_SPEC,
) -> tuple[Path, Path]:
    ffmpeg, ffprobe = require_dependencies()
    validate_configuration(dates, replicates, probes_per_panel, spec)
    video_dir = output_dir / "visualizations"
    video_path = video_dir / VIDEO_NAME
    manifest_path = video_dir / MANIFEST_NAME
    expected_frames = len(dates) * spec.frames_per_date
    if video_path.is_file() and manifest_path.is_file():
        probe = _probe_video(video_path, ffprobe)
        stream = probe["streams"][0]
        if int(stream["nb_read_frames"]) != expected_frames:
            raise RuntimeError(f"existing campaign video has the wrong frame count: {video_path}")
        return video_path, manifest_path

    for date in dates:
        validate_staged_prefix(root, date, replicates, probes_per_panel)
    scale_min, scale_max = _final_scale(sensor_rows)
    composite_dir = root / "composites"
    if composite_dir.exists():
        shutil.rmtree(composite_dir)
    composite_dir.mkdir(parents=True)
    sequence_dir = root / "sequence"
    if sequence_dir.exists():
        shutil.rmtree(sequence_dir)
    sequence_dir.mkdir()
    global_index = 0
    video_frame = 0
    allocations = frame_allocations(replicates, spec)
    for date in dates:
        for replicate_number, allocated_frames in enumerate(allocations, start=1):
            scene_path = root / date / "scenes" / f"{replicate_number:04d}.png"
            means_path = root / date / "means" / f"{replicate_number:04d}.json"
            values = json.loads(means_path.read_text(encoding="utf-8"))[
                "illumination_running_means"
            ]
            global_index += 1
            composite_path = composite_dir / f"frame_{global_index:04d}.png"
            compose_frame(
                scene_path,
                composite_path,
                date,
                replicate_number,
                replicates,
                probes_per_panel,
                values,
                scale_min,
                scale_max,
                spec,
            )
            frame_sources = [composite_path] * allocated_frames
            if replicate_number == 1:
                black_path = composite_dir / f"frame_{global_index:04d}_black.png"
                compose_frame(
                    scene_path,
                    black_path,
                    date,
                    replicate_number,
                    replicates,
                    probes_per_panel,
                    None,
                    scale_min,
                    scale_max,
                    spec,
                )
                frame_sources[0] = black_path
            for source in frame_sources:
                video_frame += 1
                os.link(source, sequence_dir / f"frame_{video_frame:06d}.png")
    if video_frame != expected_frames:
        raise RuntimeError(f"video frame allocation produced {video_frame} of {expected_frames} frames")
    video_dir.mkdir(parents=True, exist_ok=True)
    temporary_video = video_path.with_name(f".{video_path.stem}.tmp.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-framerate",
            str(spec.fps),
            "-i",
            str(sequence_dir / "frame_%06d.png"),
            "-vf",
            "format=yuv420p",
            "-frames:v",
            str(expected_frames),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-movflags",
            "+faststart",
            str(temporary_video),
        ],
        check=True,
    )
    probe = _probe_video(temporary_video, ffprobe)
    stream = probe["streams"][0]
    if (
        int(stream["width"]) != spec.width
        or int(stream["height"]) != spec.height
        or int(stream["nb_read_frames"]) != expected_frames
        or stream["r_frame_rate"] != f"{spec.fps}/1"
    ):
        raise RuntimeError(f"encoded campaign video failed validation: {temporary_video}")
    temporary_video.replace(video_path)
    manifest = {
        "version": VIDEO_VERSION,
        "file": video_path.name,
        "sha256": _sha256(video_path),
        "dates": dates,
        "replicates_per_date": replicates,
        "probes_per_panel": probes_per_panel,
        "panel_order": [list(key) for key in PANEL_ORDER],
        "layout": "scene upper 80%; PARBAR running means lower 20% in a 3x2 grid",
        "color_scale": {
            "minimum": scale_min,
            "maximum": scale_max,
            "source": "shared range of final probe means across included dates",
            "low": "red",
            "high": "green",
        },
        "spec": asdict(spec),
        "camera_render": {
            "samples": render_samples,
            "bounces": render_bounces,
        },
        "frame_count": expected_frames,
        "duration_seconds": len(dates) * spec.seconds_per_date,
        "illumination_units": "relative simulated light; not calibrated physical PAR",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.rmtree(root)
    return video_path, manifest_path
