#!/usr/bin/env python3
"""Shared, render-only presentation settings for the calibrated 4x10 field."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path


Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Bounds:
    minimum: Vec3
    maximum: Vec3

    @property
    def center(self) -> Vec3:
        return tuple((low + high) * 0.5 for low, high in zip(self.minimum, self.maximum))

    def corners(self) -> tuple[Vec3, ...]:
        return tuple(
            (x, y, z)
            for x in (self.minimum[0], self.maximum[0])
            for y in (self.minimum[1], self.maximum[1])
            for z in (self.minimum[2], self.maximum[2])
        )


# Union of calibrated plant geometry measured from the five generated 2021 scenes
# at seed 2,000,000. A fixed bound prevents the camera from zooming with growth.
FIVE_DATE_REFERENCE_BOUNDS = Bounds(
    minimum=(-2.6107702255, -0.4312002063, -11.4184722900),
    maximum=(7.7527875900, 3.0855040550, -3.9594635963),
)


@dataclass(frozen=True)
class PresentationProfile:
    name: str = "field_photographic_v1"
    camera_style: str = "field_perspective"
    sun_angles_degrees: Vec3 = (55.0, 30.0, 0.0)
    sun_angular_diameter_radians: float = 0.012
    sun_intensity: float = 0.92
    sun_color: Vec3 = (1.0, 0.975, 0.94)
    skylight_intensity: float = 0.92
    ambient_light_intensity: float = 0.14
    gamma: float = 2.2
    ground_extension_size_m: float = 160.0
    ground_texture_repeat_m: float = 4.0
    brightness: float = 0.94
    contrast: float = 0.95
    saturation: float = 0.90
    red_gain: float = 1.015
    green_gain: float = 1.0
    blue_gain: float = 0.965

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PROFILE = PresentationProfile()


def _add(a: Vec3, b: Vec3) -> Vec3:
    return tuple(x + y for x, y in zip(a, b))


def _subtract(a: Vec3, b: Vec3) -> Vec3:
    return tuple(x - y for x, y in zip(a, b))


def _scale(value: Vec3, scale: float) -> Vec3:
    return tuple(component * scale for component in value)


def _dot(a: Vec3, b: Vec3) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-9:
        raise ValueError("cannot normalize a zero-length vector")
    return _scale(value, 1.0 / length)


def _fit_camera(
    bounds: Bounds,
    offset_direction: Vec3,
    requested_up: Vec3,
    fov_degrees: float,
    aspect_ratio: float,
    crop: float,
    target_y: float | None = None,
) -> dict[str, object]:
    if aspect_ratio <= 0.0 or not 0.5 <= crop <= 1.5:
        raise ValueError("camera aspect and crop are invalid")
    center = bounds.center
    target = center if target_y is None else (center[0], target_y, center[2])
    front = _scale(_normalize(offset_direction), -1.0)
    right = _normalize(_cross(front, _normalize(requested_up)))
    up = _normalize(_cross(right, front))
    tan_vertical = math.tan(math.radians(fov_degrees) * 0.5)
    tan_horizontal = tan_vertical * aspect_ratio
    distance = 0.1
    for corner in bounds.corners():
        relative = _subtract(corner, target)
        along_front = _dot(relative, front)
        distance = max(
            distance,
            abs(_dot(relative, right)) / tan_horizontal - along_front,
            abs(_dot(relative, up)) / tan_vertical - along_front,
        )
    position = _subtract(target, _scale(front, distance * crop))
    return {
        "position": list(position),
        "target": list(target),
        "up": list(up),
        "fov_degrees": fov_degrees,
        "style": "custom",
        "crop": crop,
    }


def camera_for_style(
    style: str,
    width: int,
    height: int,
    bounds: Bounds = FIVE_DATE_REFERENCE_BOUNDS,
) -> dict[str, object]:
    """Return a fixed five-date camera; styles never modify scene geometry."""
    if width <= 0 or height <= 0:
        raise ValueError("camera dimensions must be positive")
    aspect = width / height
    if style == "field_perspective":
        camera = _fit_camera(
            bounds,
            (1.0, 0.34, 1.0),
            (0.0, 1.0, 0.0),
            42.0,
            aspect,
            0.82,
            target_y=0.92,
        )
    elif style == "near_top_down":
        camera = _fit_camera(
            bounds,
            (0.20, 1.0, 0.16),
            (0.0, 0.0, -1.0),
            44.0,
            aspect,
            0.98,
        )
    elif style == "row_side":
        camera = _fit_camera(
            bounds,
            (0.12, 0.18, 1.0),
            (0.0, 1.0, 0.0),
            46.0,
            aspect,
            0.88,
            target_y=0.90,
        )
    elif style == "legacy_oblique":
        camera = _fit_camera(
            bounds,
            (1.0, 0.65, 1.0),
            (0.0, 1.0, 0.0),
            50.0,
            aspect,
            1.10,
        )
    else:
        raise ValueError(f"unknown presentation camera style: {style}")
    camera["style"] = style
    return camera


def apply_photo_grade(
    source: Path,
    destination: Path,
    profile: PresentationProfile = DEFAULT_PROFILE,
) -> None:
    """Apply a restrained display-referred grade without touching scene assets."""
    from PIL import Image, ImageEnhance

    with Image.open(source).convert("RGB") as image:
        image = ImageEnhance.Brightness(image).enhance(profile.brightness)
        image = ImageEnhance.Contrast(image).enhance(profile.contrast)
        image = ImageEnhance.Color(image).enhance(profile.saturation)
        red, green, blue = image.split()
        red = red.point(lambda value: min(255, round(value * profile.red_gain)))
        green = green.point(lambda value: min(255, round(value * profile.green_gain)))
        blue = blue.point(lambda value: min(255, round(value * profile.blue_gain)))
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.merge("RGB", (red, green, blue)).save(destination, "PNG")


def configure_lighting(evo: object, profile: PresentationProfile = DEFAULT_PROFILE) -> None:
    def vec3(values: Vec3) -> object:
        result = evo.Vec3()
        result.x, result.y, result.z = values
        return result

    if not evo.ConfigureRayTracerSkydome(
        vec3(profile.sun_angles_degrees),
        profile.sun_angular_diameter_radians,
        profile.sun_intensity,
        vec3(profile.sun_color),
        profile.skylight_intensity,
        profile.ambient_light_intensity,
        profile.gamma,
    ):
        raise RuntimeError("failed to configure the presentation skydome")


def set_ground_extension(
    evo: object,
    enabled: bool,
    profile: PresentationProfile = DEFAULT_PROFILE,
) -> int:
    """Create or remove the non-serializable presentation-only ground skirt."""
    if not hasattr(evo, "ConfigurePresentationGroundExtension"):
        return 0
    return int(
        evo.ConfigurePresentationGroundExtension(
            enabled,
            profile.ground_extension_size_m,
            profile.ground_texture_repeat_m,
        )
    )
