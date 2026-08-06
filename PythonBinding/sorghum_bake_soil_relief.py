#!/usr/bin/env python3
"""Bake physically scaled PBR height and UV detail into the canonical EvoEngine ground mesh."""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image


VERTEX_FLOAT_COUNT = 20


def repo_root_from_script() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CMakeLists.txt").exists() and (parent / "Resources" / "DigitalAgricultureProject").exists():
            return parent
    raise RuntimeError("could not locate repository root")


def parser() -> argparse.ArgumentParser:
    root = repo_root_from_script()
    assets = root / "Resources" / "DigitalAgricultureProject" / "Assets"
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--mesh",
        type=Path,
        default=assets / "ManualAssets" / "Context" / "Mesh_7895692069869720144.evemesh",
    )
    result.add_argument(
        "--height-map", type=Path, default=assets / "ManualAssets" / "Soil" / "PBR" / "height.png"
    )
    result.add_argument("--scan-footprint-m", type=float, default=2.0)
    result.add_argument("--height-scale-m", type=float, default=0.04)
    result.add_argument("--row-relief-amplitude-m", type=float, default=0.0)
    result.add_argument("--row-spacing-m", type=float, default=0.76)
    result.add_argument("--report", type=Path, default=root / "out" / "realism_review" / "v5" / "soil_relief.json")
    return result


def warped_uv(x: np.ndarray, z: np.ndarray, footprint: float) -> tuple[np.ndarray, np.ndarray]:
    u = x / footprint + 0.16 * np.sin(2.0 * np.pi * z / 7.3) + 0.07 * np.sin(2.0 * np.pi * (x + z) / 3.9)
    v = z / footprint + 0.14 * np.sin(2.0 * np.pi * x / 8.1) - 0.06 * np.sin(2.0 * np.pi * (x - z) / 4.7)
    return u, v


def sample_periodic(image: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    height, width = image.shape
    x = np.mod(u, 1.0) * width
    y = np.mod(1.0 - v, 1.0) * height
    x0 = np.floor(x).astype(np.int32) % width
    y0 = np.floor(y).astype(np.int32) % height
    x1 = (x0 + 1) % width
    y1 = (y0 + 1) % height
    tx = x - np.floor(x)
    ty = y - np.floor(y)
    return (
        image[y0, x0] * (1.0 - tx) * (1.0 - ty)
        + image[y0, x1] * tx * (1.0 - ty)
        + image[y1, x0] * (1.0 - tx) * ty
        + image[y1, x1] * tx * ty
    )


def bake(args: argparse.Namespace) -> dict[str, object]:
    text = args.mesh.read_text(encoding="utf-8")
    match = re.search(r'(?m)^vertices_: !!binary "([A-Za-z0-9+/=]+)"$', text)
    if not match:
        raise RuntimeError(f"could not find embedded vertex buffer in {args.mesh}")
    raw = base64.b64decode(match.group(1))
    vertices = np.frombuffer(raw, dtype="<f4").copy().reshape(-1, VERTEX_FLOAT_COUNT)
    resolution = math.isqrt(len(vertices))
    if resolution * resolution != len(vertices):
        raise RuntimeError(f"ground mesh is not a square regular grid: {len(vertices)} vertices")

    grid = vertices.reshape(resolution, resolution, VERTEX_FLOAT_COUNT)
    x = vertices[:, 0]
    z = vertices[:, 2]
    u, v = warped_uv(x, z, args.scan_footprint_m)
    source = np.asarray(Image.open(args.height_map).convert("L"), dtype=np.float32) / 255.0
    sampled = sample_periodic(source, u, v)
    center = float(np.median(source))
    relief = (sampled - center) * args.height_scale_m
    if args.row_relief_amplitude_m:
        relief += args.row_relief_amplitude_m * np.cos(2.0 * np.pi * x / args.row_spacing_m)
    vertices[:, 1] = relief
    vertices[:, 16] = u
    vertices[:, 17] = v

    row_delta = grid[1, 0, [0, 2]] - grid[0, 0, [0, 2]]
    column_delta = grid[0, 1, [0, 2]] - grid[0, 0, [0, 2]]
    row_spacing = float(np.linalg.norm(row_delta))
    column_spacing = float(np.linalg.norm(column_delta))
    derivative_row, derivative_column = np.gradient(grid[:, :, 1], row_spacing, column_spacing)
    if abs(row_delta[0]) > abs(row_delta[1]):
        dydx, dydz = derivative_row, derivative_column
    else:
        dydz, dydx = derivative_row, derivative_column
    normals = np.stack((-dydx, np.ones_like(dydx), -dydz), axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    tangents = np.stack((np.ones_like(dydx), dydx, np.zeros_like(dydx)), axis=-1)
    tangents /= np.linalg.norm(tangents, axis=-1, keepdims=True)
    grid[:, :, 4:7] = normals
    grid[:, :, 8:11] = tangents

    encoded = base64.b64encode(vertices.astype("<f4", copy=False).tobytes()).decode("ascii")
    text = text[: match.start(1)] + encoded + text[match.end(1) :]
    args.mesh.write_text(text, encoding="utf-8", newline="\n")

    percentiles = np.percentile(relief, [1, 5, 50, 95, 99])
    report = {
        "mesh": str(args.mesh.resolve()),
        "height_map": str(args.height_map.resolve()),
        "vertex_count": len(vertices),
        "grid_resolution": resolution,
        "grid_spacing_m": [row_spacing, column_spacing],
        "scan_footprint_m": args.scan_footprint_m,
        "height_scale_m": args.height_scale_m,
        "row_relief_amplitude_m": args.row_relief_amplitude_m,
        "relief_percentiles_m": {key: float(value) for key, value in zip(("p01", "p05", "p50", "p95", "p99"), percentiles)},
        "robust_peak_to_peak_m": float(percentiles[-1] - percentiles[0]),
        "uv_repeats_across_x": float(np.ptp(u)),
        "uv_repeats_across_z": float(np.ptp(v)),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parser().parse_args()
    report = bake(args)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
