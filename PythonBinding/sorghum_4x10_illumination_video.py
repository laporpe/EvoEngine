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
from datetime import date as CalendarDate
from pathlib import Path

from sorghum_4x10_presentation import (
    DEFAULT_PROFILE,
    apply_photo_grade,
    camera_for_style,
    set_ground_extension,
)


PANEL_ORDER = tuple(
    (cultivar, level)
    for cultivar in ("Pawaga", "BTX")
    for level in ("top", "middle", "bottom")
)
VIDEO_VERSION = 5
VIDEO_NAME = "sorghum_4x10_illumination_convergence.mp4"
MANIFEST_NAME = "sorghum_4x10_illumination_convergence.json"
REFERENCE_SUN_ANGLES_DEGREES = (90.0, 0.0, 0.0)
SUNRISE_SUNSET_ELEVATION_DEGREES = -0.833


@dataclass(frozen=True)
class SolarSite:
    name: str
    latitude_degrees: float
    longitude_degrees: float
    utc_offset_hours: float
    timezone_label: str


# The original illumination driver names its NSRDB source
# 524042_33.08_-111.97_2021.csv. Arizona remains on UTC-7 in summer.
DEFAULT_SOLAR_SITE = SolarSite(
    name="NSRDB 524042 Arizona field site",
    latitude_degrees=33.08,
    longitude_degrees=-111.97,
    utc_offset_hours=-7.0,
    timezone_label="MST",
)


@dataclass(frozen=True)
class SolarFrame:
    frame_number: int
    frame_count: int
    local_minutes: float
    local_time: str
    elevation_degrees: float
    azimuth_degrees: float
    sun_angles_degrees: tuple[float, float, float]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["sun_angles_degrees"] = list(self.sun_angles_degrees)
        return payload


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


def _solar_terms(day: CalendarDate) -> tuple[float, float]:
    days_in_year = 366 if day.replace(month=12, day=31).timetuple().tm_yday == 366 else 365
    gamma = 2.0 * math.pi / days_in_year * (day.timetuple().tm_yday - 1)
    equation_of_time_minutes = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination_radians = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    return equation_of_time_minutes, declination_radians


def _solar_day_bounds(
    day: CalendarDate, site: SolarSite = DEFAULT_SOLAR_SITE
) -> tuple[float, float, float]:
    equation_of_time, declination = _solar_terms(day)
    latitude = math.radians(site.latitude_degrees)
    zenith = math.radians(90.0 - SUNRISE_SUNSET_ELEVATION_DEGREES)
    cosine_hour_angle = (
        math.cos(zenith) / (math.cos(latitude) * math.cos(declination))
        - math.tan(latitude) * math.tan(declination)
    )
    if not -1.0 <= cosine_hour_angle <= 1.0:
        raise ValueError(f"site has no sunrise/sunset on {day.isoformat()}")
    hour_angle_degrees = math.degrees(math.acos(cosine_hour_angle))
    solar_noon = (
        720.0
        - equation_of_time
        - 4.0 * site.longitude_degrees
        + 60.0 * site.utc_offset_hours
    )
    return (
        solar_noon - 4.0 * hour_angle_degrees,
        solar_noon,
        solar_noon + 4.0 * hour_angle_degrees,
    )


def _solar_position(
    day: CalendarDate,
    local_minutes: float,
    site: SolarSite = DEFAULT_SOLAR_SITE,
) -> tuple[float, float]:
    equation_of_time, declination = _solar_terms(day)
    latitude = math.radians(site.latitude_degrees)
    true_solar_minutes = (
        local_minutes
        + equation_of_time
        + 4.0 * site.longitude_degrees
        - 60.0 * site.utc_offset_hours
    ) % 1440.0
    hour_angle = math.radians(true_solar_minutes / 4.0 - 180.0)
    cosine_zenith = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    zenith = math.acos(max(-1.0, min(1.0, cosine_zenith)))
    elevation = 90.0 - math.degrees(zenith)
    azimuth = (
        math.degrees(
            math.atan2(
                math.sin(hour_angle),
                math.cos(hour_angle) * math.sin(latitude)
                - math.tan(declination) * math.cos(latitude),
            )
        )
        + 180.0
    ) % 360.0
    return elevation, azimuth


def _clock_label(local_minutes: float) -> str:
    total_seconds = round(local_minutes * 60.0) % (24 * 60 * 60)
    hour, remainder = divmod(total_seconds, 60 * 60)
    minute, second = divmod(remainder, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def solar_sweep_for_date(
    date: str,
    frame_count: int,
    site: SolarSite = DEFAULT_SOLAR_SITE,
) -> list[SolarFrame]:
    if frame_count < 2:
        raise ValueError("solar sweep requires at least two frames")
    day = CalendarDate.fromisoformat(date)
    sunrise, _, sunset = _solar_day_bounds(day, site)
    frames = []
    for frame_number in range(1, frame_count + 1):
        fraction = (frame_number - 1) / (frame_count - 1)
        local_minutes = sunrise + fraction * (sunset - sunrise)
        elevation, azimuth = _solar_position(day, local_minutes, site)
        frames.append(
            SolarFrame(
                frame_number=frame_number,
                frame_count=frame_count,
                local_minutes=local_minutes,
                local_time=_clock_label(local_minutes),
                elevation_degrees=elevation,
                azimuth_degrees=azimuth,
                sun_angles_degrees=(elevation, azimuth, 0.0),
            )
        )
    return frames


def solar_frame_for_replicate(
    date: str,
    replicate_number: int,
    replicates: int,
    site: SolarSite = DEFAULT_SOLAR_SITE,
) -> SolarFrame:
    if not 1 <= replicate_number <= replicates:
        raise ValueError("solar frame is outside the realization range")
    return solar_sweep_for_date(date, replicates, site)[replicate_number - 1]


def validate_configuration(
    dates: list[str],
    replicates: int,
    probes_per_panel: int,
    spec: VideoSpec = DEFAULT_SPEC,
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
        raise ValueError(
            "video dimensions must be positive, even, and reserve a lower dashboard"
        )


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


def _vec_add(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(x + y for x, y in zip(a, b))


def _vec_scale(
    value: tuple[float, float, float], scale: float
) -> tuple[float, float, float]:
    return tuple(component * scale for component in value)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
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
    if not records or any(not record.has_geometry for record in records):
        raise RuntimeError("video framing requires generated 4x10 plants")
    return camera_for_style(
        DEFAULT_PROFILE.camera_style, spec.width, spec.scene_height
    )


def _vec3(evo: object, values: list[float]) -> object:
    result = evo.Vec3()
    result.x, result.y, result.z = values
    return result


def prepare_capture_camera(
    evo: object, root: Path, date: str, spec: VideoSpec = DEFAULT_SPEC
) -> None:
    path = root / date / "camera.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        camera = payload.get("camera", payload)
    else:
        camera = _camera_from_scene(evo, spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": VIDEO_VERSION,
                    "camera": camera,
                    "presentation": DEFAULT_PROFILE.to_dict(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    if not evo.SetMainCameraLookAt(
        _vec3(evo, camera["position"]),
        _vec3(evo, camera["target"]),
        _vec3(evo, camera["up"]),
        float(camera["fov_degrees"]),
    ):
        raise RuntimeError(f"failed to apply the video camera for {date}")


def running_means(
    accumulators: dict[tuple[str, str, int], object], probes_per_panel: int
) -> list[float]:
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
    solar_frame: SolarFrame | None = None,
) -> None:
    from PIL import Image

    date_root = root / date
    scene_path = date_root / "scenes" / f"{replicate_number:04d}.png"
    means_path = date_root / "means" / f"{replicate_number:04d}.json"
    if len(values) != len(PANEL_ORDER) * probes_per_panel:
        raise ValueError("video snapshot has the wrong number of PARBAR means")
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    means_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_render = scene_path.with_name(f"{scene_path.stem}.tmp.render.png")
    temporary_scene = scene_path.with_name(f"{scene_path.stem}.tmp.png")
    ground_extended = 0
    try:
        if solar_frame:
            evo.SetSunDirection(_vec3(evo, list(solar_frame.sun_angles_degrees)))
            evo.LoopFrames(1)
        ground_extended = set_ground_extension(evo, True)
        if hasattr(evo, "ConfigurePresentationGroundExtension") and ground_extended != 1:
            raise RuntimeError("failed to create the presentation ground extension")
        evo.LoopFrames(1)
        if not evo.CaptureCurrentSceneRayTraced(
            spec.width,
            spec.scene_height,
            temporary_render,
            samples,
            bounces,
            DEFAULT_PROFILE.gamma,
        ):
            raise RuntimeError(
                f"scene video capture failed: {date} replicate {replicate_number}"
            )
        apply_photo_grade(temporary_render, temporary_scene)
    finally:
        if ground_extended:
            set_ground_extension(evo, False)
            evo.LoopFrames(1)
        if solar_frame:
            evo.SetSunDirection(_vec3(evo, list(REFERENCE_SUN_ANGLES_DEGREES)))
            evo.LoopFrames(1)
        temporary_render.unlink(missing_ok=True)
    with Image.open(temporary_scene) as image:
        if image.size != (spec.width, spec.scene_height):
            raise RuntimeError(
                f"scene video capture has the wrong dimensions: {temporary_scene}"
            )
    temporary_scene.replace(scene_path)
    payload = {
        "version": VIDEO_VERSION,
        "date": date,
        "replicate_number": replicate_number,
        "probes_per_panel": probes_per_panel,
        "render_samples": samples,
        "render_bounces": bounces,
        "presentation": DEFAULT_PROFILE.to_dict(),
        "solar_sweep": solar_frame.to_dict() if solar_frame else None,
        "panel_order": [list(key) for key in PANEL_ORDER],
        "illumination_running_means": values,
    }
    temporary_means = means_path.with_suffix(".json.tmp")
    temporary_means.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    temporary_means.replace(means_path)


def validate_staged_prefix(
    root: Path,
    date: str,
    replicates: int,
    probes_per_panel: int,
    solar_sweep: bool = False,
    solar_frame_count: int | None = None,
) -> None:
    for replicate_number in range(1, replicates + 1):
        scene_path = root / date / "scenes" / f"{replicate_number:04d}.png"
        means_path = root / date / "means" / f"{replicate_number:04d}.json"
        if not scene_path.is_file() or not means_path.is_file():
            raise RuntimeError(
                f"video resume is missing {date} realization {replicate_number} artifacts"
            )
        payload = json.loads(means_path.read_text(encoding="utf-8"))
        expected_solar = (
            solar_frame_for_replicate(
                date, replicate_number, solar_frame_count or replicates
            ).to_dict()
            if solar_sweep
            else None
        )
        if (
            payload.get("date") != date
            or payload.get("replicate_number") != replicate_number
            or payload.get("probes_per_panel") != probes_per_panel
            or len(payload.get("illumination_running_means", []))
            != len(PANEL_ORDER) * probes_per_panel
            or payload.get("solar_sweep") != expected_solar
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
    solar_frame: dict[str, object] | None = None,
    dashboard_status: str | None = None,
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
    status = dashboard_status or (
        "waiting for first illumination" if values is None else (
            f"PARBAR mean (fixed reference sun): {replicate_number} fields"
            if solar_frame
            else f"running mean: {replicate_number} fields"
        )
    )
    solar_status = (
        ""
        if not solar_frame
        else (
            f"   |   {solar_frame['local_time'][:5]} {DEFAULT_SOLAR_SITE.timezone_label}"
            f"   sun {float(solar_frame['elevation_degrees']):.1f} deg"
        )
    )
    draw.text(
        (24, dashboard_top + 5),
        f"{date}   |   field {replicate_number:03d}/{replicates:03d}   |   {status}{solar_status}",
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
                (
                    cell_left,
                    round(grid_top),
                    max(cell_left, cell_right),
                    round(grid_bottom),
                ),
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
    solar_sweep: bool = False,
    black_first_panel: bool = True,
) -> tuple[Path, Path]:
    ffmpeg, ffprobe = require_dependencies()
    validate_configuration(dates, replicates, probes_per_panel, spec)
    video_dir = output_dir / "visualizations"
    video_path = video_dir / VIDEO_NAME
    manifest_path = video_dir / MANIFEST_NAME
    expected_frames = len(dates) * spec.frames_per_date
    if video_path.is_file() and manifest_path.is_file():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if bool(existing_manifest.get("solar_sweep", {}).get("enabled")) != solar_sweep:
            raise RuntimeError(f"existing campaign video has the wrong solar mode: {video_path}")
        probe = _probe_video(video_path, ffprobe)
        stream = probe["streams"][0]
        if int(stream["nb_read_frames"]) != expected_frames:
            raise RuntimeError(
                f"existing campaign video has the wrong frame count: {video_path}"
            )
        return video_path, manifest_path

    for date in dates:
        validate_staged_prefix(root, date, replicates, probes_per_panel, solar_sweep)
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
            payload = json.loads(means_path.read_text(encoding="utf-8"))
            values = payload["illumination_running_means"]
            solar_frame = payload.get("solar_sweep")
            dashboard_status = payload.get("dashboard_status")
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
                solar_frame,
                dashboard_status,
            )
            frame_sources = [composite_path] * allocated_frames
            if black_first_panel and replicate_number == 1:
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
                    solar_frame,
                )
                frame_sources[0] = black_path
            for source in frame_sources:
                video_frame += 1
                os.link(source, sequence_dir / f"frame_{video_frame:06d}.png")
    if video_frame != expected_frames:
        raise RuntimeError(
            f"video frame allocation produced {video_frame} of {expected_frames} frames"
        )
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
        raise RuntimeError(
            f"encoded campaign video failed validation: {temporary_video}"
        )
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
        "presentation": DEFAULT_PROFILE.to_dict(),
        "unique_scene_frames_per_date": replicates,
        "encoded_frames_per_date": spec.frames_per_date,
        "scientific_capture_isolation": (
            "each engine batch completes all fixed-reference-sun PARBAR estimates "
            "before any presentation-only geometry or moving-sun capture"
        ),
        "solar_sweep": {
            "enabled": solar_sweep,
            "site": asdict(DEFAULT_SOLAR_SITE) if solar_sweep else None,
            "reference_sun_angles_restored_after_capture": list(
                REFERENCE_SUN_ANGLES_DEGREES
            ) if solar_sweep else None,
            "dates": {
                date: {
                    "sunrise": solar_sweep_for_date(date, replicates)[0].to_dict(),
                    "solar_noon_pair": [
                        frame.to_dict()
                        for frame in solar_sweep_for_date(date, replicates)[
                            replicates // 2 - 1 : replicates // 2 + 1
                        ]
                    ],
                    "sunset": solar_sweep_for_date(date, replicates)[-1].to_dict(),
                }
                for date in dates
            } if solar_sweep else {},
        },
        "frame_count": expected_frames,
        "duration_seconds": len(dates) * spec.seconds_per_date,
        "illumination_units": "relative simulated light; not calibrated physical PAR",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.rmtree(root)
    return video_path, manifest_path
