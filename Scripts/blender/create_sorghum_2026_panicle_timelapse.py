"""Build a 1,000-state midday 2026 sorghum GDD time-lapse.

The 6x10 row ownership and Stage-2 genotype measurements are read from the
project data. Reproductive height and panicle parameters are illustrative
extrapolations, explicitly separated from the measured scenes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    ROOT
    / "Resources/DigitalAgricultureProject/Data/Experiments/Sorghum2026_6x10/descriptor_targets.csv"
)
DESCRIPTOR_ROOT = (
    ROOT
    / "Resources/DigitalAgricultureProject/Assets/GeneratedAssets/Experiments/Sorghum2026_6x10/Descriptors/MeasurementStage02"
)
DEFAULT_OUTPUT = ROOT / "out/panicle_timelapse/sorghum_2026_6x10_1000_gdd_midday"
ROW_GENOTYPES = (
    "GenotypeA",
    "GenotypeA",
    "GenotypeB",
    "GenotypeB",
    "GenotypeC",
    "GenotypeC",
)
MIDDAY_SUN_ANGLES_DEGREES = (90.0, 0.0, 0.0)
PANICLE_SOURCE = "research/panicle source/research_synthesis.md"
FIELD_STATE_COUNT = 1000
DEFAULT_PANICLE_MATURITY_GDD = 260.0


@dataclass(frozen=True)
class Stage:
    name: str
    frame: int
    gdd_fraction: float
    plant_scale: float


STAGE_SPECS = (
    ("Seed", 0.001, 0.001),
    ("Emergence", 0.025, 0.08),
    ("Seedling", 0.09, 0.24),
    ("Leaf expansion", 0.22, 0.48),
    ("Vegetative", 0.45, 0.70),
    ("Culm elongation", 0.60, 0.88),
    ("Boot", 0.68, 0.96),
    ("Heading", 0.76, 1.0),
    ("Anthesis", 0.84, 1.0),
    ("Reproductive maturity", 1.0, 1.0),
)

PANICLE_STYLES = {
    "GenotypeA": {
        "height_multiplier": 2.10,
        "length": 0.34,
        "radius": 0.29,
        "branches": 16,
        "rise": 0.090,
    },
    "GenotypeB": {
        "height_multiplier": 1.94,
        "length": 0.36,
        "radius": 0.23,
        "branches": 18,
        "rise": 0.075,
    },
    "GenotypeC": {
        "height_multiplier": 1.90,
        "length": 0.38,
        "radius": 0.19,
        "branches": 20,
        "rise": 0.060,
    },
}


def frame_for_fraction(
    fraction: float, field_state_count: int = FIELD_STATE_COUNT
) -> int:
    return max(1, min(field_state_count, round(fraction * field_state_count)))


def stage_plan(field_state_count: int = FIELD_STATE_COUNT) -> tuple[Stage, ...]:
    return tuple(
        Stage(
            name,
            frame_for_fraction(gdd_fraction, field_state_count),
            gdd_fraction,
            plant_scale,
        )
        for name, gdd_fraction, plant_scale in STAGE_SPECS
    )


def gdd_at_field(
    field_index: int, target_gdd: float, field_state_count: int = FIELD_STATE_COUNT
) -> float:
    return max(0.0, min(target_gdd, target_gdd * field_index / field_state_count))


def panicle_timeline(
    target_gdd: float,
    panicle_maturity_gdd: float,
    field_state_count: int = FIELD_STATE_COUNT,
) -> dict[str, int]:
    development_start = max(
        0.30, min(0.78, 1.0 - panicle_maturity_gdd / max(1.0, target_gdd))
    )
    reproductive_window = 1.0 - development_start
    return {
        "boot": frame_for_fraction(
            max(0.05, development_start - 0.10), field_state_count
        ),
        "emergence": frame_for_fraction(
            development_start + reproductive_window * 0.17, field_state_count
        ),
        "full_exsertion": frame_for_fraction(
            development_start + reproductive_window * 0.38, field_state_count
        ),
        "anthesis_start": frame_for_fraction(
            development_start + reproductive_window * 0.54, field_state_count
        ),
        "anthesis_end": frame_for_fraction(
            development_start + reproductive_window * 0.68, field_state_count
        ),
        "maturity": field_state_count,
    }


def field_layout() -> tuple[tuple[str, int, int, float, float], ...]:
    y_values = (-3.25, -2.15, 0.05, 1.15, 3.35, 4.45)
    return tuple(
        (genotype, row, column, (column - 4.5) * 0.76, y_values[row])
        for row, genotype in enumerate(ROW_GENOTYPES)
        for column in range(10)
    )


def panicle_style(
    genotype: str, stage2_height_m: float, leaf_count: float
) -> dict[str, float | int]:
    style = PANICLE_STYLES[genotype]
    return {
        "height_m": max(1.35, stage2_height_m * float(style["height_multiplier"])),
        "leaf_count": max(9, int(round(leaf_count))),
        "length_m": float(style["length"]),
        "radius_m": float(style["radius"]),
        "branch_count": int(style["branches"]),
        "branch_rise_m": float(style["rise"]),
    }


def validate_spec(field_state_count: int = FIELD_STATE_COUNT) -> None:
    stages = stage_plan(field_state_count)
    if field_state_count != FIELD_STATE_COUNT:
        raise ValueError(
            "the GDD time-lapse must contain exactly 1,000 sequential field states"
        )
    if stages[0].name != "Seed" or stages[-1].name != "Reproductive maturity":
        raise ValueError(
            "time-lapse must begin at seed and end at reproductive maturity"
        )
    if stages[-1].frame != field_state_count or [
        stage.frame for stage in stages
    ] != sorted(stage.frame for stage in stages):
        raise ValueError("stage frames must increase")
    if (
        len(field_layout()) != 60
        or sum(item[0] == "GenotypeA" for item in field_layout()) != 20
    ):
        raise ValueError(
            "field layout must retain the 6x10, 20-plants-per-genotype design"
        )
    if MIDDAY_SUN_ANGLES_DEGREES != (90.0, 0.0, 0.0):
        raise ValueError("time-lapse must retain the fixed midday reference sun")


def _descriptor_scalar(path: Path, key: str, fallback: float) -> float:
    match = re.search(
        rf"(?m)^{re.escape(key)}:\s*\n\s+mean:\s*([-+0-9.eE]+)",
        path.read_text(encoding="utf-8"),
    )
    return float(match.group(1)) if match else fallback


def read_stage2_targets(path: Path) -> dict[str, dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    result = {
        row["genotype_id"]: {
            "height_m_mean": float(row["height_m_mean"]),
            "leaf_count_mean": float(row["leaf_count_mean"]),
        }
        for row in rows
        if row["session_id"] == "MeasurementStage02"
    }
    if set(result) != set(PANICLE_STYLES):
        raise ValueError(
            f"missing Stage-2 targets: {sorted(set(PANICLE_STYLES) - set(result))}"
        )
    for genotype, target in result.items():
        descriptor = DESCRIPTOR_ROOT / f"{genotype}.sorghumls"
        if not descriptor.is_file():
            raise FileNotFoundError(f"missing Stage-2 descriptor: {descriptor}")
        target["target_gdd"] = _descriptor_scalar(descriptor, "target_gdd", 660.0)
        target["panicle_maturity_gdd"] = _descriptor_scalar(
            descriptor, "panicle_maturity_gdd", DEFAULT_PANICLE_MATURITY_GDD
        )
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution-x", type=int, default=640)
    parser.add_argument("--resolution-y", type=int, default=360)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--field-state-count", type=int, default=FIELD_STATE_COUNT)
    parser.add_argument("--skip-render", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def _material(
    bpy, name: str, color: tuple[float, float, float, float], roughness: float
):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = next(
        node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"
    )
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    material.diffuse_color = color
    return material


def _key_color(
    material,
    frames_and_colors: tuple[tuple[int, tuple[float, float, float, float]], ...],
) -> None:
    bsdf = next(
        node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"
    )
    for frame, color in frames_and_colors:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Base Color"].keyframe_insert("default_value", frame=frame)


def _mesh(
    bpy,
    collection,
    name: str,
    vertices,
    faces,
    material,
    parent=None,
    smooth: bool = False,
):
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    if smooth:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


def _cylinder(
    Vector, vertices, faces, start, end, radius0: float, radius1: float, sides: int = 7
) -> None:
    axis = end - start
    if axis.length < 1.0e-5:
        return
    axis.normalize()
    reference = (
        Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.92 else Vector((1.0, 0.0, 0.0))
    )
    right = axis.cross(reference).normalized()
    up = right.cross(axis).normalized()
    base = len(vertices)
    for point, radius in ((start, radius0), (end, radius1)):
        for side in range(sides):
            angle = math.tau * side / sides
            vertices.append(
                point + radius * (right * math.cos(angle) + up * math.sin(angle))
            )
    for side in range(sides):
        next_side = (side + 1) % sides
        faces.append(
            (
                base + side,
                base + next_side,
                base + sides + next_side,
                base + sides + side,
            )
        )
    faces.extend(
        (
            tuple(base + side for side in range(sides)),
            tuple(base + sides + side for side in reversed(range(sides))),
        )
    )


def _spikelet(Vector, vertices, faces, center, radius: float, length: float) -> None:
    base = len(vertices)
    top = center + Vector((0.0, 0.0, length * 0.5))
    bottom = center - Vector((0.0, 0.0, length * 0.5))
    vertices.extend((top, bottom))
    for side in range(6):
        angle = math.tau * side / 6.0
        vertices.append(
            center + Vector((radius * math.cos(angle), radius * math.sin(angle), 0.0))
        )
    for side in range(6):
        next_side = (side + 1) % 6
        faces.append((base, base + 2 + side, base + 2 + next_side))
        faces.append((base + 1, base + 2 + next_side, base + 2 + side))


def _leaf(
    Vector, vertices, faces, base, direction, length: float, width: float, height: float
) -> None:
    start = len(vertices)
    lateral = Vector((-direction.y, direction.x, 0.0)).normalized()
    points = []
    for segment in range(7):
        u = segment / 6.0
        center = (
            base
            + direction * (length * u)
            + Vector((0.0, 0.0, height * (0.035 * u - 0.18 * u * u)))
        )
        half_width = width * math.sin(math.pi * u) * (0.84 + 0.16 * (1.0 - u))
        points.append((center - lateral * half_width, center + lateral * half_width))
    vertices.extend(point for pair in points for point in pair)
    for segment in range(6):
        left0, right0 = start + segment * 2, start + segment * 2 + 1
        left1, right1 = start + (segment + 1) * 2, start + (segment + 1) * 2 + 1
        faces.append((left0, left1, right1, right0))


def _leaf_cohorts(
    bpy,
    Vector,
    collection,
    parent,
    genotype: str,
    height: float,
    leaf_count: int,
    plant_index: int,
    material,
    field_state_count: int,
):
    objects = []
    for cohort_start in range(0, leaf_count, 3):
        vertices, faces = [], []
        for rank in range(cohort_start, min(leaf_count, cohort_start + 3)):
            ratio = rank / max(1, leaf_count - 1)
            base = Vector((0.0, 0.0, height * (0.10 + ratio * 0.72)))
            azimuth = math.radians(
                rank * 180.0
                + plant_index * 17.0
                + (12.0 if genotype == "GenotypeC" else 0.0)
            )
            direction = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
            length = height * (0.29 + 0.13 * math.sin(math.pi * ratio))
            width = 0.040 + 0.030 * math.sin(math.pi * ratio)
            _leaf(Vector, vertices, faces, base, direction, length, width, height)
        obj = _mesh(
            bpy,
            collection,
            f"{genotype}_LeafCohort_{plant_index:02d}_{cohort_start:02d}",
            vertices,
            faces,
            material,
            parent,
        )
        start_fraction = 0.06 + 0.035 * cohort_start
        for frame, value in (
            (1, 0.001),
            (frame_for_fraction(start_fraction, field_state_count), 0.001),
            (
                frame_for_fraction(min(0.62, start_fraction + 0.18), field_state_count),
                1.0,
            ),
            (field_state_count, 1.0),
        ):
            obj.scale = (value, value, value)
            obj.keyframe_insert("scale", frame=frame)
        objects.append(obj)
    return objects


def _panicle_meshes(
    bpy,
    Vector,
    collection,
    parent,
    genotype: str,
    plant_index: int,
    style,
    timeline,
    branch_material,
    spikelet_material,
    anther_material,
):
    rng = random.Random(91_007 + plant_index * 43)
    branches, branch_faces = [], []
    spikelets, spikelet_faces = [], []
    anthers, anther_faces = [], []
    length, radius = float(style["length_m"]), float(style["radius_m"])
    branch_count, rise = int(style["branch_count"]), float(style["branch_rise_m"])
    _cylinder(
        Vector,
        branches,
        branch_faces,
        Vector((0.0, 0.0, 0.0)),
        Vector((0.0, 0.0, length)),
        0.006,
        0.003,
        7,
    )

    def triad(position, radial) -> None:
        tangent = Vector((-radial.y, radial.x, 0.0))
        _spikelet(
            Vector,
            spikelets,
            spikelet_faces,
            position + Vector((0.0, 0.0, 0.014)),
            0.0105,
            0.030,
        )
        _spikelet(
            Vector, spikelets, spikelet_faces, position + tangent * 0.014, 0.0072, 0.022
        )
        _spikelet(
            Vector, spikelets, spikelet_faces, position - tangent * 0.014, 0.0072, 0.022
        )
        _cylinder(
            Vector,
            anthers,
            anther_faces,
            position + Vector((0.0, 0.0, 0.024)),
            position + Vector((0.0, 0.0, 0.046)),
            0.0020,
            0.0013,
            5,
        )

    for branch_index in range(branch_count):
        t = (branch_index + 0.55) / branch_count
        angle = branch_index * 2.399963 + rng.uniform(-0.22, 0.22)
        radial = Vector((math.cos(angle), math.sin(angle), 0.0))
        span = radius * math.sin(math.pi * t) ** 0.72 * rng.uniform(0.80, 1.08)
        start = Vector((0.0, 0.0, t * length))
        end = (
            start + radial * span + Vector((0.0, 0.0, rise * (0.35 + 0.65 * (1.0 - t))))
        )
        _cylinder(Vector, branches, branch_faces, start, end, 0.0023, 0.0009, 5)
        triad(end, radial)
        if branch_index % 2 == 0:
            secondary_start = start.lerp(end, 0.54)
            secondary_radial = Vector(
                (math.cos(angle + 0.54), math.sin(angle + 0.54), 0.0)
            )
            secondary_end = (
                secondary_start
                + secondary_radial * span * 0.42
                + Vector((0.0, 0.0, rise * 0.34))
            )
            _cylinder(
                Vector,
                branches,
                branch_faces,
                secondary_start,
                secondary_end,
                0.00155,
                0.00065,
                5,
            )
            triad(secondary_end, secondary_radial)

    branch = _mesh(
        bpy,
        collection,
        f"{genotype}_PanicleRachisBranches_{plant_index:02d}",
        branches,
        branch_faces,
        branch_material,
        parent,
        True,
    )
    grains = _mesh(
        bpy,
        collection,
        f"{genotype}_PanicleSpikeletTriads_{plant_index:02d}",
        spikelets,
        spikelet_faces,
        spikelet_material,
        parent,
        True,
    )
    flower = _mesh(
        bpy,
        collection,
        f"{genotype}_PanicleAnthesis_{plant_index:02d}",
        anthers,
        anther_faces,
        anther_material,
        parent,
        True,
    )
    for obj in (branch, grains):
        for frame, value in (
            (1, 0.001),
            (timeline["boot"], 0.001),
            (timeline["emergence"], 0.35),
            (timeline["full_exsertion"], 1.0),
            (timeline["maturity"], 1.0),
        ):
            obj.scale = (value, value, value)
            obj.keyframe_insert("scale", frame=frame)
    for frame, value in (
        (1, 0.001),
        (timeline["full_exsertion"], 0.001),
        (timeline["anthesis_start"], 1.0),
        (timeline["anthesis_end"], 1.0),
        (min(timeline["maturity"], timeline["anthesis_end"] + 45), 0.001),
        (timeline["maturity"], 0.001),
    ):
        flower.scale = (value, value, value)
        flower.keyframe_insert("scale", frame=frame)
    return branch, grains, flower


def _seed_mesh(bpy, Vector):
    vertices, faces = [], []
    _spikelet(Vector, vertices, faces, Vector((0.0, 0.0, 0.012)), 0.016, 0.028)
    mesh = bpy.data.meshes.new("Sorghum Seed Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def _point_camera(camera, target):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def build_scene(args: argparse.Namespace):
    import bpy
    from mathutils import Vector

    validate_spec(args.field_state_count)
    stages = stage_plan(args.field_state_count)
    targets = read_stage2_targets(TARGETS)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.frame_start, scene.frame_end = stages[0].frame, stages[-1].frame
    scene.render.image_settings.file_format = "PNG"
    scene.world.use_nodes = True
    world_background = scene.world.node_tree.nodes.get("Background")
    world_background.inputs["Color"].default_value = (0.055, 0.145, 0.30, 1.0)
    world_background.inputs["Strength"].default_value = 0.32

    field = bpy.data.collections.new("Sorghum 2026 Panicle Time-lapse")
    scene.collection.children.link(field)
    soil = _material(bpy, "Time-lapse dry field soil", (0.095, 0.034, 0.010, 1.0), 0.93)
    seed_material = _material(bpy, "Sorghum seed", (0.48, 0.075, 0.008, 1.0), 0.62)
    leaf_materials = {
        "GenotypeA": _material(bpy, "Genotype A leaf", (0.072, 0.30, 0.025, 1.0), 0.58),
        "GenotypeB": _material(bpy, "Genotype B leaf", (0.035, 0.35, 0.020, 1.0), 0.56),
        "GenotypeC": _material(
            bpy, "Genotype C leaf", (0.100, 0.275, 0.020, 1.0), 0.60
        ),
    }
    stem_materials = {
        genotype: _material(bpy, f"{genotype} culm", (0.20, 0.43, 0.065, 1.0), 0.70)
        for genotype in PANICLE_STYLES
    }
    branch_materials = {
        genotype: _material(
            bpy, f"{genotype} panicle rachis", (0.18, 0.36, 0.055, 1.0), 0.73
        )
        for genotype in PANICLE_STYLES
    }
    spikelet_materials = {
        genotype: _material(
            bpy, f"{genotype} spikelets", (0.22, 0.44, 0.055, 1.0), 0.64
        )
        for genotype in PANICLE_STYLES
    }
    anther_material = _material(bpy, "Panicle anthers", (0.95, 0.63, 0.055, 1.0), 0.42)
    for genotype in PANICLE_STYLES:
        timeline = panicle_timeline(
            targets[genotype]["target_gdd"],
            targets[genotype]["panicle_maturity_gdd"],
            args.field_state_count,
        )
        _key_color(
            branch_materials[genotype],
            (
                (1, (0.18, 0.36, 0.055, 1.0)),
                (timeline["full_exsertion"], (0.18, 0.36, 0.055, 1.0)),
                (timeline["maturity"], (0.38, 0.26, 0.055, 1.0)),
            ),
        )
        _key_color(
            spikelet_materials[genotype],
            (
                (1, (0.22, 0.44, 0.055, 1.0)),
                (timeline["full_exsertion"], (0.35, 0.56, 0.06, 1.0)),
                (timeline["anthesis_start"], (0.95, 0.64, 0.10, 1.0)),
                (timeline["maturity"], (0.42, 0.06, 0.025, 1.0)),
            ),
        )

    soil_vertices = [
        (-5.5, -5.5, 0.0),
        (5.5, -5.5, 0.0),
        (5.5, 6.5, 0.0),
        (-5.5, 6.5, 0.0),
    ]
    _mesh(
        bpy, field, "Measured-layout field ground", soil_vertices, [(0, 1, 2, 3)], soil
    )
    seed_mesh = _seed_mesh(bpy, Vector)
    plant_records = []
    for plant_index, (genotype, row, column, x, y) in enumerate(field_layout()):
        target = targets[genotype]
        style = panicle_style(
            genotype, target["height_m_mean"], target["leaf_count_mean"]
        )
        timeline = panicle_timeline(
            target["target_gdd"], target["panicle_maturity_gdd"], args.field_state_count
        )
        plant = bpy.data.objects.new(f"{genotype}_Plant_R{row}_C{column}", None)
        field.objects.link(plant)
        plant.location = (x, y, 0.0)
        plant["genotype_id"] = genotype
        plant["row"] = row
        plant["column"] = column
        plant["stage2_height_m"] = target["height_m_mean"]
        plant["reproductive_height_m"] = style["height_m"]
        plant["target_gdd"] = target["target_gdd"]
        plant["panicle_source"] = PANICLE_SOURCE
        for stage in stages:
            plant.scale = (stage.plant_scale, stage.plant_scale, stage.plant_scale)
            plant.keyframe_insert("scale", frame=stage.frame)

        height = float(style["height_m"])
        lean = Vector(
            (
                0.055 * math.sin(plant_index * 1.37),
                0.055 * math.cos(plant_index * 1.13),
                0.0,
            )
        )
        stem_vertices, stem_faces = [], []
        _cylinder(
            Vector,
            stem_vertices,
            stem_faces,
            Vector((0.0, 0.0, 0.0)),
            lean + Vector((0.0, 0.0, height)),
            0.017,
            0.010,
            9,
        )
        _mesh(
            bpy,
            field,
            f"{genotype}_Culm_{plant_index:02d}",
            stem_vertices,
            stem_faces,
            stem_materials[genotype],
            plant,
            True,
        )
        _leaf_cohorts(
            bpy,
            Vector,
            field,
            plant,
            genotype,
            height,
            int(style["leaf_count"]),
            plant_index,
            leaf_materials[genotype],
            args.field_state_count,
        )

        panicle_parent = bpy.data.objects.new(
            f"{genotype}_PanicleAnchor_{plant_index:02d}", None
        )
        field.objects.link(panicle_parent)
        panicle_parent.parent = plant
        panicle_parent.location = lean + Vector((0.0, 0.0, height))
        _panicle_meshes(
            bpy,
            Vector,
            field,
            panicle_parent,
            genotype,
            plant_index,
            style,
            timeline,
            branch_materials[genotype],
            spikelet_materials[genotype],
            anther_material,
        )

        boot_vertices, boot_faces = [], []
        _cylinder(
            Vector,
            boot_vertices,
            boot_faces,
            Vector((0.0, 0.0, -0.05)),
            Vector((0.0, 0.0, 0.20)),
            0.038,
            0.055,
            8,
        )
        boot = _mesh(
            bpy,
            field,
            f"{genotype}_Boot_{plant_index:02d}",
            boot_vertices,
            boot_faces,
            leaf_materials[genotype],
            panicle_parent,
            True,
        )
        for frame, value in (
            (1, 0.001),
            (timeline["boot"], 0.001),
            (timeline["emergence"], 1.0),
            (timeline["full_exsertion"], 0.001),
            (args.field_state_count, 0.001),
        ):
            boot.scale = (value, value, value)
            boot.keyframe_insert("scale", frame=frame)

        seed = bpy.data.objects.new(f"{genotype}_Seed_R{row}_C{column}", seed_mesh)
        field.objects.link(seed)
        seed.location = (x, y, 0.0)
        seed.data.materials.clear()
        seed.data.materials.append(seed_material)
        for frame, value in (
            (1, 1.8),
            (frame_for_fraction(0.025, args.field_state_count), 1.45),
            (frame_for_fraction(0.09, args.field_state_count), 0.001),
            (args.field_state_count, 0.001),
        ):
            seed.scale = (value, value, value)
            seed.keyframe_insert("scale", frame=frame)
        plant_records.append(
            {
                "genotype": genotype,
                "row": row,
                "column": column,
                "x_m": x,
                "y_m": y,
                **style,
                "target_gdd": target["target_gdd"],
                "panicle_timeline": timeline,
            }
        )

    sun_data = bpy.data.lights.new("Fixed Midday Sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("Fixed Midday Sun", sun_data)
    field.objects.link(sun)
    sun.rotation_euler = (0.0, 0.0, 0.0)
    sun["sun_angles_degrees"] = MIDDAY_SUN_ANGLES_DEGREES
    fill_data = bpy.data.lights.new("Open Sky Fill", "AREA")
    fill_data.energy, fill_data.shape, fill_data.size = 450.0, "DISK", 10.0
    fill = bpy.data.objects.new("Open Sky Fill", fill_data)
    field.objects.link(fill)
    fill.location = (-2.0, -3.0, 8.0)

    camera_data = bpy.data.cameras.new("Midday Time-lapse Camera")
    camera = bpy.data.objects.new("Midday Time-lapse Camera", camera_data)
    field.objects.link(camera)
    camera_data.lens = 45.0
    for frame, location, target in (
        (1, (8.0, -10.0, 5.0), (0.0, 0.65, 1.15)),
        (args.field_state_count, (5.8, -7.2, 3.3), (0.0, 0.65, 1.25)),
    ):
        camera.location = location
        _point_camera(camera, Vector(target))
        camera.keyframe_insert("location", frame=frame)
        camera.keyframe_insert("rotation_euler", frame=frame)
    scene.camera = camera

    return {"plant_records": plant_records, "scene": scene, "targets": targets}


def main() -> None:
    args = parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    built = build_scene(args)
    import bpy

    blend_path = (
        args.output_dir / "sorghum_2026_6x10_1000_gdd_panicle_midday_timelapse.blend"
    )
    video_path = (
        args.output_dir / "sorghum_2026_6x10_1000_gdd_panicle_midday_timelapse.mp4"
    )
    frames_path = args.output_dir / "frames"
    bpy.context.scene.render.filepath = str(frames_path / "frame_")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    if not args.skip_render:
        frames_path.mkdir(parents=True, exist_ok=True)
        bpy.ops.render.render(animation=True)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg is required to assemble the PNG time-lapse frames"
            )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                str(args.fps),
                "-start_number",
                str(stage_plan(args.field_state_count)[0].frame),
                "-i",
                str(frames_path / "frame_%04d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(video_path),
            ],
            check=True,
        )
    report = {
        "schema_version": 2,
        "ownership": "blender_presentation_only",
        "scientific_scene_modified": False,
        "input": {"descriptor_targets": str(TARGETS), "sha256": sha256(TARGETS)},
        "field": {"rows": list(ROW_GENOTYPES), "plants": 60, "plants_per_genotype": 20},
        "field_states": args.field_state_count,
        "gdd_mapping": {
            "field_index": "1..1000",
            "per_genotype": {
                genotype: {
                    "target_gdd": target["target_gdd"],
                    "field_0001_gdd": gdd_at_field(
                        1, target["target_gdd"], args.field_state_count
                    ),
                    "field_1000_gdd": gdd_at_field(
                        args.field_state_count,
                        target["target_gdd"],
                        args.field_state_count,
                    ),
                    "panicle_maturity_gdd": target["panicle_maturity_gdd"],
                }
                for genotype, target in built["targets"].items()
            },
        },
        "reproductive_policy": "illustrative extrapolation from Stage-2 measured height and leaf count; no reproductive measurements are claimed",
        "panicle_architecture": "rachis, primary and secondary branches, terminal sessile-plus-pedicellate spikelet triads; anthers animate only through anthesis",
        "panicle_source": PANICLE_SOURCE,
        "midday_sun": {
            "fixed": True,
            "angles_degrees": list(MIDDAY_SUN_ANGLES_DEGREES),
        },
        "timeline": [asdict(stage) for stage in stage_plan(args.field_state_count)],
        "plants": built["plant_records"],
        "blend": str(blend_path),
        "frames": str(frames_path),
        "video": str(video_path),
        "video_rendered": not args.skip_render,
    }
    (
        args.output_dir / "sorghum_2026_6x10_1000_gdd_panicle_midday_timelapse.json"
    ).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "blend": str(blend_path),
                "video": str(video_path),
                "rendered": not args.skip_render,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
