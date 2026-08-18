#!/usr/bin/env python3
"""Bake a continuous, presentation-only 3x3 sorghum leaf PBR atlas."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


OWNERSHIP = "blender_presentation_only"
PREFIX = "sorghum_lsystem_leaf_variants_v2"
VARIANTS = (
    ("healthy_medium", 1.00, (1.00, 1.00, 1.00), 1.00, 0.00),
    ("healthy_dark", 0.91, (0.94, 1.00, 0.91), 1.03, -0.02),
    ("healthy_waxy", 1.02, (0.96, 1.03, 0.96), 1.08, -0.06),
    ("juvenile_light", 1.08, (1.03, 1.04, 0.91), 0.94, 0.03),
    ("broad_midrib", 1.00, (1.01, 1.00, 0.94), 1.22, 0.00),
    ("narrow_midrib", 0.98, (0.96, 1.01, 0.98), 0.82, 0.02),
    ("subtle_fleck", 0.97, (1.03, 0.99, 0.91), 1.00, 0.04),
    ("dry_margin_hint", 0.94, (1.05, 0.98, 0.86), 0.95, 0.07),
    ("deep_green", 0.88, (0.91, 1.00, 0.88), 1.05, -0.01),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_collar(image: np.ndarray) -> int:
    luminance = 0.2126 * image[:, :, 0] + 0.7152 * image[:, :, 1] + 0.0722 * image[:, :, 2]
    row_signal = luminance.mean(axis=1)
    first = round(image.shape[0] * 0.45)
    last = round(image.shape[0] * 0.80)
    return first + int(np.argmax(row_signal[first:last]))


def resample_rows(image: np.ndarray, source_rows: np.ndarray) -> np.ndarray:
    lower = np.floor(source_rows).astype(np.int32)
    upper = np.minimum(lower + 1, image.shape[0] - 1)
    weight = (source_rows - lower)[:, None, None]
    return image[lower] * (1.0 - weight) + image[upper] * weight


def smooth_junction(array: np.ndarray, half: int, band: int) -> np.ndarray:
    result = np.array(array, dtype=np.float32, copy=True)
    start = max(0, half - band)
    end = min(result.shape[0] - 1, half + band)
    first = result[start].copy()
    last = result[end].copy()
    for row in range(start, end + 1):
        value = (row - start) / max(1, end - start)
        value = value * value * (3.0 - 2.0 * value)
        result[row] = first * (1.0 - value) + last * value
    return result


def anatomical_master(master: Image.Image, tile_size: int) -> np.ndarray:
    source = np.asarray(master.convert("RGB"), dtype=np.float32) / 255.0
    collar = locate_collar(source)
    half = tile_size // 2
    output_rows = np.arange(tile_size, dtype=np.float32)
    source_rows = np.empty(tile_size, dtype=np.float32)
    proximal = output_rows < half
    source_rows[proximal] = output_rows[proximal] / max(1, half - 1) * collar
    source_rows[~proximal] = collar + (output_rows[~proximal] - half) / max(1, tile_size - half - 1) * (
        source.shape[0] - 1 - collar
    )
    warped = resample_rows(source, source_rows)
    resized = Image.fromarray(np.uint8(np.clip(warped * 255.0, 0.0, 255.0))).resize(
        (tile_size, tile_size), Image.Resampling.LANCZOS
    )
    return smooth_junction(np.asarray(resized, dtype=np.float32) / 255.0, half, max(8, tile_size // 24))


def grayscale_blur(values: np.ndarray, radius: float) -> np.ndarray:
    image = Image.fromarray(np.uint8(np.clip(values * 255.0, 0.0, 255.0)), "L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius=radius)), dtype=np.float32) / 255.0


def make_variant(base: np.ndarray, index: int, tile_size: int) -> dict[str, np.ndarray]:
    _, brightness, channel_scale, midrib_scale, roughness_offset = VARIANTS[index]
    y, x = np.mgrid[0:tile_size, 0:tile_size]
    u = x / max(1, tile_size - 1)
    v = y / max(1, tile_size - 1)
    midrib_width = 0.027 * midrib_scale
    midrib = np.exp(-((u - 0.5) / midrib_width) ** 2)
    collar = np.exp(-((v - 0.5) / 0.045) ** 2)
    edge = np.clip(np.abs(u - 0.5) * 2.0, 0.0, 1.0)

    albedo = np.clip(base * brightness * np.asarray(channel_scale, dtype=np.float32), 0.0, 1.0)
    albedo += midrib[:, :, None] * np.asarray((0.040, 0.052, 0.012), dtype=np.float32)
    if index in (6, 7):
        damage = (
            np.sin((x * 0.173 + y * 0.071 + index * 1.7))
            * np.sin((x * 0.041 - y * 0.113 + index * 0.9))
        )
        damage = np.clip((damage - 0.78) * 3.5, 0.0, 1.0) * np.clip((v - 0.10) / 0.35, 0.0, 1.0)
        if index == 7:
            damage = np.maximum(damage * 0.45, np.clip((edge - 0.91) * 8.0, 0.0, 1.0) * 0.22)
        albedo = albedo * (1.0 - damage[:, :, None] * 0.22) + damage[:, :, None] * np.asarray(
            (0.54, 0.39, 0.13), dtype=np.float32
        )
    else:
        damage = np.zeros((tile_size, tile_size), dtype=np.float32)
    albedo = smooth_junction(albedo, tile_size // 2, max(8, tile_size // 24))

    gray = 0.2126 * albedo[:, :, 0] + 0.7152 * albedo[:, :, 1] + 0.0722 * albedo[:, :, 2]
    detail = np.clip(gray - grayscale_blur(gray, max(1.0, tile_size / 350.0)), -0.12, 0.12)
    height = np.clip(0.43 + 0.17 * midrib + 0.035 * collar + 0.18 * detail, 0.20, 0.78)
    height = smooth_junction(height, tile_size // 2, max(8, tile_size // 24))

    dy, dx = np.gradient(height)
    normal_strength = 16.0
    nx = -dx * normal_strength
    ny = dy * normal_strength
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx / length, ny / length, nz / length), axis=2) * 0.5 + 0.5
    normal = smooth_junction(normal, tile_size // 2, max(8, tile_size // 24))

    sheath = np.clip((v - 0.50) / 0.30, 0.0, 1.0)
    roughness = np.clip(0.54 + 0.045 * sheath - 0.065 * midrib + roughness_offset + 0.08 * damage, 0.38, 0.72)
    roughness = smooth_junction(roughness, tile_size // 2, max(8, tile_size // 24))
    ao = smooth_junction(np.clip(0.985 - 0.012 * midrib - 0.008 * collar, 0.94, 1.0), tile_size // 2, max(8, tile_size // 24))
    thickness = smooth_junction(np.clip(0.40 + 0.30 * midrib + 0.18 * sheath - 0.10 * edge, 0.24, 0.88), tile_size // 2, max(8, tile_size // 24))
    return {
        "albedo": albedo,
        "normal": normal,
        "roughness": roughness,
        "height": height,
        "ao": ao,
        "metallic": np.zeros((tile_size, tile_size), dtype=np.float32),
        "thickness": thickness,
    }


def seam_metric(tiles: list[dict[str, np.ndarray]], key: str) -> float:
    values = []
    for tile in tiles:
        array = tile[key]
        difference = np.abs(array[array.shape[0] // 2 - 1] - array[array.shape[0] // 2]) * 255.0
        values.append(float(difference.mean()))
    return float(np.mean(values))


def assemble(tiles: list[dict[str, np.ndarray]], key: str, tile_size: int) -> np.ndarray:
    sample = tiles[0][key]
    shape = (3 * tile_size, 3 * tile_size) + (() if sample.ndim == 2 else (sample.shape[2],))
    atlas = np.zeros(shape, dtype=np.float32)
    for index, tile in enumerate(tiles):
        row, column = divmod(index, 3)
        atlas[row * tile_size : (row + 1) * tile_size, column * tile_size : (column + 1) * tile_size] = tile[key]
    return atlas


def save_rgb(path: Path, values: np.ndarray) -> None:
    if values.ndim == 2:
        values = np.repeat(values[:, :, None], 3, axis=2)
    Image.fromarray(np.uint8(np.clip(values * 255.0, 0.0, 255.0)), "RGB").save(path, optimize=True)


def bake_continuous_atlas(master_path: Path, output_dir: Path, tile_size: int = 1536) -> dict[str, Path]:
    if tile_size < 256 or tile_size % 2:
        raise ValueError("tile_size must be an even integer >= 256")
    master_path = Path(master_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base = anatomical_master(Image.open(master_path), tile_size)
    tiles = [make_variant(base, index, tile_size) for index in range(len(VARIANTS))]

    outputs = {key: output_dir / f"{PREFIX}_{key}.png" for key in tiles[0]}
    albedo = assemble(tiles, "albedo", tile_size)
    alpha = np.full(albedo.shape[:2] + (1,), 255, dtype=np.uint8)
    Image.fromarray(np.concatenate((np.uint8(np.clip(albedo * 255.0, 0.0, 255.0)), alpha), axis=2), "RGBA").save(
        outputs["albedo"], optimize=True
    )
    for key in ("normal", "roughness", "ao", "metallic", "thickness"):
        save_rgb(outputs[key], assemble(tiles, key, tile_size))
    height = assemble(tiles, "height", tile_size)
    Image.fromarray(np.uint16(np.clip(height * 65535.0, 0.0, 65535.0))).save(outputs["height"])
    preview = output_dir / f"{PREFIX}_preview.png"
    save_rgb(preview, albedo)
    outputs["preview"] = preview

    metrics = {
        "albedo_mean_rgb_255": seam_metric(tiles, "albedo"),
        "normal_mean_rgb_255": seam_metric(tiles, "normal"),
        "roughness_mean_255": seam_metric(tiles, "roughness"),
        "height_mean_255": seam_metric(tiles, "height"),
        "ao_mean_255": seam_metric(tiles, "ao"),
    }
    report = {
        "schema_version": 1,
        "ownership": OWNERSHIP,
        "scientific_geometry_modified": False,
        "master": str(master_path),
        "master_sha256": sha256(master_path),
        "variant_count": len(VARIANTS),
        "variants": [variant[0] for variant in VARIANTS],
        "tile_size": tile_size,
        "atlas_size": [tile_size * 3, tile_size * 3],
        "uv_contract": "existing 3x3 atlas; sheath V 0.02..0.48; distal V 0.50..0.99",
        "junction_guard_pixels": max(8, tile_size // 24),
        "seam_metrics": metrics,
        "maps": {key: str(path) for key, path in outputs.items()},
    }
    report_path = output_dir / f"{PREFIX}_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    outputs["report"] = report_path
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--tile-size", type=int, default=1536)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = bake_continuous_atlas(args.master, args.output_dir, args.tile_size)
    print(outputs["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
