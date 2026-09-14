"""Capture evaluated SorghumLS snapshots without changing the engine scene.

Call GrowthGeometryExporter.capture(evo, gdd) after each of your own growth steps,
then finish(). Blender consumes the returned manifest path in a separate process.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

PARTS = ("culm", "leaves", "panicle")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_mesh(mesh):
    count = len(mesh["positions"])
    for key, width in (("positions", 3), ("normals", 3), ("uv", 2), ("colors", 4)):
        value = mesh[key]
        if value.shape != (count, width) or not np.isfinite(value).all():
            raise ValueError(f"Invalid mesh {key}: {value.shape}")
    triangles = mesh["triangles"]
    if (
        triangles.ndim != 2
        or triangles.shape[1] != 3
        or triangles.dtype.kind not in "iu"
    ):
        raise ValueError("Invalid triangle array")
    if triangles.size and (triangles.min() < 0 or triangles.max() >= count):
        raise ValueError("Triangle index outside vertex array")


def aligned_triangles(positions, normals, triangles):
    """Match EvoEngine's model exporter: orient each face toward its vertex normals.

    No positions or triangle membership change. The source arrays are untouched.
    """
    result = triangles.copy()
    points = positions[result]
    face_normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    flip = np.sum(face_normals * normals[result].sum(axis=1), axis=1) < 0
    result[flip] = result[flip][:, [0, 2, 1]]
    return result


def validate_manifest(manifest):
    if (
        manifest.get("schema") != "evoengine_sorghum_growth_v1"
        or manifest.get("up_axis") != "Y"
        or manifest.get("units") != "meters"
    ):
        raise ValueError("Unsupported geometry manifest")
    if not isinstance(manifest.get("fps"), int) or manifest["fps"] < 1:
        raise ValueError("FPS must be a positive integer")
    frames = manifest["frames"]
    if not frames or [s["frame"] for s in frames] != list(range(1, len(frames) + 1)):
        raise ValueError("Need a nonempty contiguous frame schedule")
    gdds = [s["gdd"] for s in frames]
    if any(not math.isfinite(g) or g < 0 for g in gdds) or gdds != sorted(gdds):
        raise ValueError("Need finite nondecreasing nonnegative GDD")
    ids = [p["id"] for p in manifest["plants"]]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Need unique plant IDs")


class GrowthGeometryExporter:
    """Write one fixed roster of plants at one or more ordered growth samples.

    The output must be a new/empty directory. Only finish() publishes a manifest.
    Plant organs may appear/disappear or change topology; adding/removing entire
    plants during a recording requires a separate recording.
    """

    def __init__(self, output, fps=24, metadata=None):
        if not isinstance(fps, int) or fps < 1:
            raise ValueError("FPS must be a positive integer")
        self.output = Path(output).resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise FileExistsError("Choose a new/empty export directory")
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "frames").mkdir()
        self.manifest = {
            "schema": "evoengine_sorghum_growth_v1",
            "fps": fps,
            "units": "meters",
            "up_axis": "Y",
            "plants": [],
            "frames": [],
            "metadata": metadata or {},
        }
        self.low, self.high = np.full(3, np.inf), np.full(3, -np.inf)
        self._retained = None
        self._retained_hash = None
        self._ownership_checked = False
        self._finished = False

    def capture(self, engine, gdd):
        """Copy the current evaluated CPU meshes; never advances or rebuilds growth."""
        if self._finished:
            raise RuntimeError("This export is already finished")
        return self.write_frame(engine.GetSorghumLsGeometrySnapshots(), gdd)

    def write_frame(self, snapshots, gdd):
        """Write dictionaries returned by GetSorghumLsGeometrySnapshots()."""
        if self._finished:
            raise RuntimeError("This export is already finished")
        if not math.isfinite(gdd) or gdd < 0:
            raise ValueError("GDD must be finite and nonnegative")
        frames = self.manifest["frames"]
        if frames and gdd < frames[-1]["gdd"]:
            raise ValueError("Capture samples in nondecreasing GDD order")
        snapshots = sorted(snapshots, key=lambda p: (p["name"], p["entity_handle"]))
        if not snapshots or len({p["entity_handle"] for p in snapshots}) != len(
            snapshots
        ):
            raise ValueError("Need a nonempty set of unique plant entities")
        if frames and len(snapshots) != len(self.manifest["plants"]):
            raise ValueError("Plant roster changed during capture")
        if (
            self._retained is not None
            and hashlib.sha256(self._retained.tobytes()).hexdigest()
            != self._retained_hash
        ):
            raise RuntimeError("Snapshot buffer changed after growth")
        ownership_checked = self._ownership_checked or self._retained is not None
        retained, retained_hash = self._retained, self._retained_hash
        arrays, records, plants = {}, [], []
        low, high = self.low.copy(), self.high.copy()
        for i, snapshot in enumerate(snapshots):
            key = f"plant_{i:03d}"
            identity = {
                "id": key,
                **{
                    k: snapshot[k]
                    for k in ("name", "entity_handle", "genotype", "seed")
                },
                "descriptor_path": snapshot.get("descriptor_path", ""),
            }
            if frames and identity != self.manifest["plants"][i]:
                raise ValueError("Plant identity or descriptor changed during capture")
            plants.append(identity)
            world = snapshot["world_transform"]
            if world.shape != (4, 4) or not np.isfinite(world).all():
                raise ValueError("Invalid plant transform")
            arrays[f"{key}/world_transform"] = world
            record = {
                k: snapshot[k]
                for k in (
                    "requested_gdd",
                    "evaluated_gdd",
                    "geometry_version",
                    "organ_ranges",
                )
            }
            record["id"], record["meshes"] = key, {}
            for part in PARTS:
                mesh = snapshot[part]
                validate_mesh(mesh)
                for attribute, value in mesh.items():
                    arrays[f"{key}/{part}/{attribute}"] = value
                record["meshes"][part] = {
                    "vertices": len(mesh["positions"]),
                    "triangles": len(mesh["triangles"]),
                }
                if len(mesh["positions"]):
                    points = mesh["positions"] @ world[:3, :3].T + world[:3, 3]
                    low, high = (
                        np.minimum(low, points.min(axis=0)),
                        np.maximum(high, points.max(axis=0)),
                    )
                    if retained is None:
                        retained = mesh["positions"]
                        retained_hash = hashlib.sha256(retained.tobytes()).hexdigest()
            records.append(record)
        index = len(frames) + 1
        path = self.output / f"frames/frame_{index:04d}.npz"
        np.savez(path, **arrays)
        path.with_suffix(".json").write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )
        frames.append(
            {
                "frame": index,
                "gdd": float(gdd),
                "file": f"frames/{path.name}",
                "sha256": sha256(path),
                "metadata": f"frames/{path.stem}.json",
            }
        )
        self.manifest["plants"] = plants
        self.low, self.high = low, high
        self._retained, self._retained_hash = retained, retained_hash
        self._ownership_checked = ownership_checked
        return index

    def finish(self, camera=None, lighting=None):
        """Publish manifest.json, with an optional Y-up camera/daylight presentation."""
        if self._finished:
            raise RuntimeError("This export is already finished")
        if not self.manifest["frames"] or not np.isfinite(self.low).all():
            raise RuntimeError("Capture at least one sample containing geometry")
        center = (self.low + self.high) / 2
        scale = max(
            float(self.high[1] - self.low[1]) * 1.5,
            float(self.high[2] - self.low[2]) / (16 / 9) * 1.2,
            0.1,
        )
        self.manifest["camera"] = camera or {
            "projection": "orthographic",
            "position": (center + [-12, 3, 0]).tolist(),
            "target": center.tolist(),
            "up": [0, 1, 0],
            "ortho_scale": scale,
            "aspect": 16 / 9,
        }
        self.manifest["lighting"] = lighting or {
            "sun_elevation_degrees": 45,
            "sun_azimuth_degrees": 135,
            "sun_energy": 3.0,
            "world_strength": 0.4,
        }
        self.manifest["bounds"] = {"min": self.low.tolist(), "max": self.high.tolist()}
        self.manifest["validation"] = {
            "owned_arrays_survive_growth": self._ownership_checked,
            "frame_count": len(self.manifest["frames"]),
            "plant_count": len(self.manifest["plants"]),
            "finite_geometry_and_indices": True,
        }
        path = self.output / "manifest.json"
        path.write_text(
            json.dumps(self.manifest, indent=2, allow_nan=False), encoding="utf-8"
        )
        self._finished = True
        return path
