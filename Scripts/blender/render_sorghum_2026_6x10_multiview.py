"""Render the twelve-view 2026 6x10 review from an authored Cycles blend file."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sorghum_2026_background as background  # noqa: E402
import sorghum_leaf_presentation as leaf_presentation  # noqa: E402


PLANT_PATTERN = re.compile(r"^(Genotype[ABC])_LSystem_R(\d+)_C(\d+)$")
OVERVIEW_VIEWS = ("perspective", "near_top_down", "row_side")
GENOTYPE_PREFIXES = {
    "GenotypeA": "genotype_a",
    "GenotypeB": "genotype_b",
    "GenotypeC": "genotype_c",
}
VIEWS = OVERVIEW_VIEWS + tuple(
    f"{prefix}_{detail}"
    for prefix in GENOTYPE_PREFIXES.values()
    for detail in ("plant", "basal", "leaf")
)
LEAF_MATERIAL = "SWEEP_LSystem_Leaf_Cycles"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    parser.add_argument("--views", default=",".join(VIEWS))
    parser.add_argument("--leaf-bend-degrees", type=float, default=42.0)
    parser.add_argument("--leaf-bend-start", type=float, default=0.20)
    parser.add_argument(
        "--leaf-bend-mode",
        choices=("legacy_all_components", "blade_only"),
        default="blade_only",
    )
    parser.add_argument(
        "--leaf-shader-stage",
        choices=("legacy", "continuous_albedo", "continuous_pbr", "final"),
        default="final",
    )
    parser.add_argument("--background-profile", type=Path)
    parser.add_argument("--background-variant", choices=background.BACKGROUND_VARIANTS, default="final")
    parser.add_argument("--background-bakeoff", action="store_true")
    return parser.parse_args(argv)


def leaf_objects() -> list[bpy.types.Object]:
    return [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(material and material.name == LEAF_MATERIAL for material in obj.data.materials)
    ]


def component_records(mesh: bpy.types.Mesh) -> tuple[bmesh.types.BMesh, list[dict[str, object]]]:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        bm.free()
        raise RuntimeError(f"leaf mesh {mesh.name} has no longitudinal UV map")
    remaining = set(bm.verts)
    records = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        vertices = []
        while stack:
            vertex = stack.pop()
            vertices.append(vertex)
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    stack.append(other)
        uv_by_vertex = {
            vertex: sum(loop[uv_layer].uv.y for loop in vertex.link_loops) / len(vertex.link_loops)
            for vertex in vertices
        }
        minimum = min(uv_by_vertex.values())
        maximum = max(uv_by_vertex.values())
        span = maximum - minimum
        if span <= 1.0e-6:
            continue
        edge = 0.04 * span
        base = sum((vertex.co for vertex in vertices if uv_by_vertex[vertex] <= minimum + edge), Vector())
        base /= sum(uv_by_vertex[vertex] <= minimum + edge for vertex in vertices)
        tip = sum((vertex.co for vertex in vertices if uv_by_vertex[vertex] >= maximum - edge), Vector())
        tip /= sum(uv_by_vertex[vertex] >= maximum - edge for vertex in vertices)
        records.append(
            {
                "vertices": vertices,
                "uv": uv_by_vertex,
                "minimum": minimum,
                "maximum": maximum,
                "base": base,
                "tip": tip,
            }
        )
    return bm, records


def paired_components(records: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    remaining = set(range(len(records)))
    groups = []
    while remaining:
        index = remaining.pop()
        record = records[index]
        candidates = [
            other
            for other in remaining
            if len(records[other]["vertices"]) == len(record["vertices"])
            and abs(float(records[other]["minimum"]) - float(record["minimum"])) < 1.0e-4
            and abs(float(records[other]["maximum"]) - float(record["maximum"])) < 1.0e-4
        ]
        if candidates:
            partner = min(
                candidates,
                key=lambda other: (
                    (records[other]["base"] - record["base"]).length
                    + (records[other]["tip"] - record["tip"]).length
                ),
            )
            distance = (
                (records[partner]["base"] - record["base"]).length
                + (records[partner]["tip"] - record["tip"]).length
            )
            if distance < 0.05:
                remaining.remove(partner)
                groups.append([record, records[partner]])
                continue
        groups.append([record])
    return groups


def bend_leaf_group(group: list[dict[str, object]], degrees: float, bend_start: float) -> tuple[int, float]:
    vertices = [vertex for record in group for vertex in record["vertices"]]
    minimum = min(float(record["minimum"]) for record in group)
    maximum = max(float(record["maximum"]) for record in group)
    span = maximum - minimum
    edge = 0.04 * span
    uv = {vertex: value for record in group for vertex, value in record["uv"].items()}
    base_vertices = [vertex for vertex in vertices if uv[vertex] <= minimum + edge]
    tip_vertices = [vertex for vertex in vertices if uv[vertex] >= maximum - edge]
    base = sum((vertex.co for vertex in base_vertices), Vector()) / len(base_vertices)
    tip = sum((vertex.co for vertex in tip_vertices), Vector()) / len(tip_vertices)
    chord = tip - base
    if chord.length <= 1.0e-5:
        return 0, 0.0
    horizontal = Vector((chord.x, chord.y, 0.0))
    if horizontal.length <= 1.0e-5:
        horizontal = Vector((base.x, base.y, 0.0))
    if horizontal.length <= 1.0e-5:
        horizontal = Vector((1.0, 0.0, 0.0))
    target = (horizontal.normalized() + Vector((0.0, 0.0, -1.0))).normalized()
    axis = chord.normalized().cross(target)
    if axis.length <= 1.0e-5:
        axis = Vector((horizontal.y, -horizontal.x, 0.0)).normalized()
    else:
        axis.normalize()
    rotations = {}
    blade_base_max_displacement = 0.0
    for vertex in vertices:
        before = vertex.co.copy()
        strength = leaf_presentation.blade_bend_weight(uv[vertex], minimum, maximum, bend_start)
        key = round(strength, 5)
        rotation = rotations.setdefault(key, Matrix.Rotation(math.radians(degrees) * key, 4, axis))
        vertex.co = base + rotation @ (vertex.co - base)
        if uv[vertex] <= minimum + edge:
            blade_base_max_displacement = max(blade_base_max_displacement, (vertex.co - before).length)
    return len(vertices), blade_base_max_displacement


def bend_all_leaves(degrees: float, bend_start: float, mode: str = "blade_only") -> dict[str, object]:
    if degrees < 0.0 or degrees > 90.0:
        raise ValueError("leaf bend must be between 0 and 90 degrees")
    if bend_start < 0.0 or bend_start >= 1.0:
        raise ValueError("leaf bend start must be in [0, 1)")
    objects = leaf_objects()
    if len(objects) != 60:
        raise RuntimeError(f"expected 60 leaf objects, found {len(objects)}")
    component_count = paired_group_count = solo_group_count = vertex_count = 0
    blade_component_count = bent_blade_group_count = proximal_group_count = junction_weld_count = 0
    blade_base_max_displacement = 0.0
    for obj in objects:
        bm, records = component_records(obj.data)
        groups = paired_components(records)
        for group in groups:
            paired_group_count += len(group) == 2
            solo_group_count += len(group) == 1
            minimum = min(float(record["minimum"]) for record in group)
            maximum = max(float(record["maximum"]) for record in group)
            is_blade = leaf_presentation.global_component_is_blade(minimum, maximum)
            if is_blade:
                blade_component_count += len(group)
            if mode == "legacy_all_components" or is_blade:
                bent_vertices, base_displacement = bend_leaf_group(group, degrees, bend_start)
                vertex_count += bent_vertices
                if is_blade:
                    bent_blade_group_count += 1
                    blade_base_max_displacement = max(blade_base_max_displacement, base_displacement)
            else:
                proximal_group_count += 1
        component_count += len(records)
        if mode == "blade_only":
            before_weld = len(bm.verts)
            bmesh.ops.remove_doubles(
                bm,
                verts=list(bm.verts),
                dist=leaf_presentation.JUNCTION_WELD_DISTANCE_M,
            )
            junction_weld_count += before_weld - len(bm.verts)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
    return {
        "presentation_only": True,
        "method": (
            "legacy_all_surface_components_longitudinal_uv_distal_rotation"
            if mode == "legacy_all_components"
            else "atlas_semantic_blade_only_longitudinal_uv_distal_rotation"
        ),
        "mode": mode,
        "bend_degrees": degrees,
        "bend_start_fraction": bend_start,
        "leaf_object_count": len(objects),
        "surface_component_count": component_count,
        "blade_surface_component_count": blade_component_count,
        "bent_blade_group_count": bent_blade_group_count,
        "unbent_proximal_group_count": proximal_group_count,
        "paired_surface_group_count": paired_group_count,
        "solo_surface_group_count": solo_group_count,
        "deformed_vertex_count": vertex_count,
        "blade_base_max_displacement_m": blade_base_max_displacement,
        "junction_weld_distance_m": leaf_presentation.JUNCTION_WELD_DISTANCE_M,
        "junction_weld_count": junction_weld_count,
        "canonical_descriptors_modified": False,
        "scientific_scenes_modified": False,
    }


def mesh_descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [obj for obj in root.children_recursive if obj.type == "MESH" and not obj.hide_render]


def object_bound_points(objects: list[bpy.types.Object]) -> list[Vector]:
    return [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = object_bound_points(objects)
    if not points:
        raise RuntimeError("cannot frame an empty object set")
    return (
        Vector(tuple(min(point[index] for point in points) for index in range(3))),
        Vector(tuple(max(point[index] for point in points) for index in range(3))),
    )


def center_and_radius(minimum: Vector, maximum: Vector) -> tuple[Vector, float]:
    center = (minimum + maximum) * 0.5
    return center, max((maximum - center).length, 0.1)


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def review_camera(name: str) -> bpy.types.Object:
    camera = bpy.data.objects.get(name)
    if camera is None:
        camera_data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, camera_data)
        bpy.context.scene.collection.objects.link(camera)
    camera.data.sensor_fit = "VERTICAL"
    camera.data.sensor_height = 32.0
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000.0
    return camera


def place_camera(
    name: str,
    target: Vector,
    direction: tuple[float, float, float],
    distance: float,
    fov_degrees: float,
) -> bpy.types.Object:
    camera = review_camera(name)
    camera.data.lens = camera.data.sensor_height / (2.0 * math.tan(math.radians(fov_degrees) * 0.5))
    camera.location = target + Vector(direction).normalized() * distance
    look_at(camera, target)
    return camera


def fit_camera(
    name: str,
    minimum: Vector,
    maximum: Vector,
    direction: tuple[float, float, float],
    fov_degrees: float,
    aspect: float,
    margin: float,
    target_height_fraction: float = 0.5,
) -> bpy.types.Object:
    center, radius = center_and_radius(minimum, maximum)
    target = center.copy()
    target.z = minimum.z + target_height_fraction * (maximum.z - minimum.z)
    vertical = math.radians(fov_degrees)
    horizontal = 2.0 * math.atan(math.tan(vertical * 0.5) * aspect)
    limiting = min(vertical, horizontal)
    distance = margin * radius / max(math.sin(limiting * 0.5), 0.05)
    return place_camera(name, target, direction, distance, fov_degrees)


def plant_roots() -> dict[str, list[bpy.types.Object]]:
    result = {genotype: [] for genotype in GENOTYPE_PREFIXES}
    for obj in bpy.context.scene.objects:
        match = PLANT_PATTERN.fullmatch(obj.name)
        if match:
            result[match.group(1)].append(obj)
    if {key: len(value) for key, value in result.items()} != {
        "GenotypeA": 20,
        "GenotypeB": 20,
        "GenotypeC": 20,
    }:
        raise RuntimeError(f"expected 20 plant roots per genotype, got { {key: len(value) for key, value in result.items()} }")
    return result


def representative(root_group: list[bpy.types.Object]) -> tuple[bpy.types.Object, Vector, Vector]:
    candidates = []
    for root in root_group:
        match = PLANT_PATTERN.fullmatch(root.name)
        if match and int(match.group(3)) in (2, 7):
            minimum, maximum = bounds(mesh_descendants(root))
            candidates.append((root, minimum, maximum, maximum.z - minimum.z))
    heights = sorted(value[3] for value in candidates)
    median = (heights[(len(heights) - 1) // 2] + heights[len(heights) // 2]) * 0.5
    root, minimum, maximum, _height = min(candidates, key=lambda value: (abs(value[3] - median), value[0].name))
    return root, minimum, maximum


def make_cameras(
    aspect: float,
) -> tuple[dict[str, bpy.types.Object], dict[str, str], Vector, Vector]:
    roots = plant_roots()
    plant_meshes = [mesh for group in roots.values() for root in group for mesh in mesh_descendants(root)]
    parbar_meshes = []
    for genotype in GENOTYPE_PREFIXES:
        root = bpy.data.objects.get(f"PARBAR_{genotype}")
        if root:
            parbar_meshes.extend(mesh_descendants(root))
    if len(parbar_meshes) < 9:
        raise RuntimeError(f"expected exported PARBAR geometry, found only {len(parbar_meshes)} meshes")
    field_minimum, field_maximum = bounds(plant_meshes + parbar_meshes)
    authored_perspective = bpy.data.objects.get("Cycles Paper Camera")
    if authored_perspective is None or authored_perspective.type != "CAMERA":
        raise RuntimeError("the author-approved Cycles Paper Camera is missing")
    authored_perspective.name = "SWEEP Review perspective"
    authored_perspective.data.clip_end = 1000.0
    cameras = {
        "perspective": authored_perspective,
        "near_top_down": fit_camera(
            "SWEEP Review near_top_down", field_minimum, field_maximum,
            (0.16, -0.12, 1.0), 44.0, aspect, 0.73, 0.46,
        ),
        "row_side": fit_camera(
            "SWEEP Review row_side", field_minimum, field_maximum,
            (0.08, -1.0, 0.13), 46.0, aspect, 0.68, 0.30,
        ),
    }
    representatives = {}
    for genotype, prefix in GENOTYPE_PREFIXES.items():
        root, minimum, maximum = representative(roots[genotype])
        representatives[genotype] = root.name
        height = max(maximum.z - minimum.z, 0.1)
        center = (minimum + maximum) * 0.5
        cameras[f"{prefix}_plant"] = fit_camera(
            f"SWEEP Review {prefix}_plant", minimum, maximum,
            (-0.24, -1.0, 0.24), 46.0, aspect, 1.08, 0.48,
        )
        root_center = Vector((center.x, center.y, minimum.z))
        cameras[f"{prefix}_basal"] = place_camera(
            f"SWEEP Review {prefix}_basal",
            root_center + Vector((0.0, 0.0, 0.20 * height)),
            (-0.28, -1.0, 0.14), max(0.42, 0.56 * height), 38.0,
        )
        cameras[f"{prefix}_leaf"] = place_camera(
            f"SWEEP Review {prefix}_leaf",
            root_center + Vector((0.0, 0.0, 0.62 * height)),
            (0.30, -1.0, 0.12), max(0.36, 0.46 * height), 34.0,
        )
    return cameras, representatives, field_minimum, field_maximum


def configure_render(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type != "CPU"
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"


def principled_value(material_name: str, socket_name: str):
    material = bpy.data.materials.get(material_name)
    if not material or not material.use_nodes:
        return None
    node = next((candidate for candidate in material.node_tree.nodes if candidate.type == "BSDF_PRINCIPLED"), None)
    if not node or socket_name not in node.inputs:
        return None
    value = node.inputs[socket_name].default_value
    return list(value) if hasattr(value, "__len__") and not isinstance(value, str) else value


def principled_any_value(material_name: str, socket_names: tuple[str, ...]):
    for socket_name in socket_names:
        value = principled_value(material_name, socket_name)
        if value is not None:
            return value
    return None


def input_link_source(material_name: str, node_name: str, socket_name: str) -> str | None:
    material = bpy.data.materials.get(material_name)
    if not material or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get(node_name)
    if not node or socket_name not in node.inputs or not node.inputs[socket_name].is_linked:
        return None
    return node.inputs[socket_name].links[0].from_node.name


def material_image_paths(material_name: str) -> dict[str, str]:
    material = bpy.data.materials.get(material_name)
    if not material or not material.use_nodes:
        return {}
    return {
        node.label: str(Path(bpy.path.abspath(node.image.filepath)).resolve())
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image and node.label
    }


def configure_leaf_shader_stage(stage: str) -> dict[str, object]:
    material = bpy.data.materials.get("SWEEP_LSystem_Leaf_Cycles")
    if not material or not material.use_nodes:
        raise RuntimeError("missing SWEEP leaf material")
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("SWEEP Leaf Principled BSDF") or next(
        (node for node in nodes if node.type == "BSDF_PRINCIPLED"), None
    )
    if bsdf is None:
        raise RuntimeError("missing SWEEP leaf Principled BSDF")

    def unlink_input(socket_name: str) -> None:
        if socket_name in bsdf.inputs:
            for link in list(bsdf.inputs[socket_name].links):
                links.remove(link)

    if stage in ("continuous_albedo", "continuous_pbr"):
        calibration = nodes.get("SWEEP Leaf Reference Color Calibration")
        if calibration and "Base Color" in bsdf.inputs:
            unlink_input("Base Color")
            links.new(calibration.outputs["Color"], bsdf.inputs["Base Color"])
        unlink_input("Subsurface Weight")
        if "Subsurface Weight" in bsdf.inputs:
            bsdf.inputs["Subsurface Weight"].default_value = 0.06
        for anisotropic_name in ("Anisotropic IOR Level", "Anisotropic"):
            if anisotropic_name in bsdf.inputs:
                bsdf.inputs[anisotropic_name].default_value = 0.0
                break

    if stage == "continuous_albedo":
        for socket_name in ("Roughness", "Metallic", "Normal"):
            unlink_input(socket_name)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.55
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output and "Displacement" in output.inputs:
            for link in list(output.inputs["Displacement"].links):
                links.remove(link)

    return {
        "stage": stage,
        "ownership": "blender_presentation_only",
        "scientific_scene_modified": False,
    }


def node_input_value(material_name: str, node_name: str, socket_name: str):
    material = bpy.data.materials.get(material_name)
    if not material or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get(node_name)
    if not node or socket_name not in node.inputs:
        return None
    value = node.inputs[socket_name].default_value
    return list(value) if hasattr(value, "__len__") and not isinstance(value, str) else value


def color_ramp_endpoints(material_name: str, node_name: str) -> list[float] | None:
    material = bpy.data.materials.get(material_name)
    if not material or not material.use_nodes:
        return None
    node = material.node_tree.nodes.get(node_name)
    if not node or not hasattr(node, "color_ramp") or len(node.color_ramp.elements) < 2:
        return None
    return [node.color_ramp.elements[0].color[0], node.color_ramp.elements[-1].color[0]]


def soil_context_report() -> dict[str, object]:
    collection = bpy.data.collections.get("SWEEP_RenderOnly_SoilContext")
    mounds = bpy.data.objects.get("SWEEP Soil Contact Mounds")
    clods = bpy.data.objects.get("SWEEP Soil Large Clods")
    aggregate = bpy.data.objects.get("SWEEP Soil Small Aggregate")
    pebbles = bpy.data.objects.get("SWEEP Dry Field Pebbles")
    residue = bpy.data.objects.get("SWEEP Dry Crop Residue")
    return {
        "ownership": "blender_presentation_only",
        "collection": collection.name if collection else None,
        "object_count": len(collection.objects) if collection else 0,
        "plant_base_count": mounds.get("plant_contact_count") if mounds else None,
        "mound_vertices": len(mounds.data.vertices) if mounds else 0,
        "clod_count": clods.get("element_count") if clods else None,
        "small_aggregate_count": aggregate.get("element_count") if aggregate else None,
        "pebble_count": pebbles.get("element_count") if pebbles else None,
        "residue_fragment_count": residue.get("fragment_count") if residue else None,
        "scientific_scene_modified": False,
    }


def render_background_bakeoff(
    args: argparse.Namespace,
    camera: bpy.types.Object,
) -> None:
    outputs = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, variant in enumerate(background.BACKGROUND_VARIANTS, 1):
        state = background.set_landscape_for_view("perspective", variant)
        bpy.context.scene.camera = camera
        output = args.output_dir / f"{index:02d}_{variant}.png"
        bpy.context.scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs.append({"variant": variant, "output": str(output), **state})
    background.set_landscape_for_view("perspective", "final")
    bpy.context.scene.camera = camera
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    report = {
        "schema_version": 1,
        "session_id": args.session,
        "renderer": "Blender Cycles",
        "fixed_camera": {
            "name": camera.name,
            "location": list(camera.location),
            "rotation_euler": list(camera.rotation_euler),
            "lens_mm": camera.data.lens,
        },
        "samples": args.samples,
        "resolution": [args.resolution_x, args.resolution_y],
        "variants": outputs,
        "landscape": background.landscape_report("final"),
        "scientific_scene_modified": False,
    }
    (args.output_dir.parent / f"{args.session}_background_bakeoff_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.output_blend = args.output_blend.resolve()
    args.output_dir = args.output_dir.resolve()
    selected = [value.strip() for value in args.views.split(",") if value.strip()]
    unknown = set(selected) - set(VIEWS)
    if unknown:
        raise ValueError(f"unknown views: {sorted(unknown)}")
    if not args.background_profile or not args.background_profile.is_file():
        raise FileNotFoundError(args.background_profile or "--background-profile is required")
    args.background_profile = args.background_profile.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    leaf_shader_stage = configure_leaf_shader_stage(args.leaf_shader_stage)
    leaf_bend = bend_all_leaves(args.leaf_bend_degrees, args.leaf_bend_start, args.leaf_bend_mode)
    configure_render(args)
    cameras, representatives, field_minimum, field_maximum = make_cameras(
        args.resolution_x / args.resolution_y
    )
    ground_material = bpy.data.materials.get("SWEEP_Ground_Soil_Displaced_Cycles")
    if ground_material is None:
        raise RuntimeError("the approved displaced soil material is missing")
    background.create_landscape_context(
        field_minimum,
        field_maximum,
        ground_material,
        args.background_profile,
    )
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.camera = cameras["perspective"]
    background.set_landscape_for_view("perspective", args.background_variant)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    if args.background_bakeoff:
        render_background_bakeoff(args, cameras["perspective"])
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    views = []
    for view in selected:
        camera = cameras[view]
        bpy.context.scene.camera = camera
        landscape_state = background.set_landscape_for_view(view, args.background_variant)
        output = args.output_dir / f"{args.session}_{view}.png"
        bpy.context.scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        views.append(
            {
                "view": view,
                "output": str(output),
                "camera": camera.name,
                "location": list(camera.location),
                "rotation_euler": list(camera.rotation_euler),
                "lens_mm": camera.data.lens,
                "landscape": landscape_state,
            }
        )
    bpy.context.scene.camera = cameras["perspective"]
    background.set_landscape_for_view("perspective", args.background_variant)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    sky = None
    if bpy.context.scene.world and bpy.context.scene.world.use_nodes:
        sky = next((node for node in bpy.context.scene.world.node_tree.nodes if node.type == "TEX_SKY"), None)
    report = {
        "schema_version": 1,
        "session_id": args.session,
        "renderer": "Blender Cycles",
        "source_blend": str(args.blend),
        "output_blend": str(args.output_blend),
        "samples": args.samples,
        "resolution": [args.resolution_x, args.resolution_y],
        "device": bpy.context.scene.cycles.device,
        "representative_plants": representatives,
        "leaf_bend": leaf_bend,
        "leaf_shader_stage": leaf_shader_stage,
        "views": views,
        "leaf_shader": {
            "material": "SWEEP_LSystem_Leaf_Cycles",
            "subsurface_weight": principled_value("SWEEP_LSystem_Leaf_Cycles", "Subsurface Weight"),
            "subsurface_scale": principled_value("SWEEP_LSystem_Leaf_Cycles", "Subsurface Scale"),
            "subsurface_radius": principled_value("SWEEP_LSystem_Leaf_Cycles", "Subsurface Radius"),
            "specular_ior_level": principled_value("SWEEP_LSystem_Leaf_Cycles", "Specular IOR Level"),
            "roughness": principled_value("SWEEP_LSystem_Leaf_Cycles", "Roughness"),
            "anisotropic": principled_any_value(
                "SWEEP_LSystem_Leaf_Cycles", ("Anisotropic IOR Level", "Anisotropic")
            ),
            "subsurface_source": input_link_source(
                "SWEEP_LSystem_Leaf_Cycles", "SWEEP Leaf Principled BSDF", "Subsurface Weight"
            ),
            "base_color_source": input_link_source(
                "SWEEP_LSystem_Leaf_Cycles", "SWEEP Leaf Principled BSDF", "Base Color"
            ),
            "texture_paths": material_image_paths("SWEEP_LSystem_Leaf_Cycles"),
            "color_saturation": node_input_value(
                "SWEEP_LSystem_Leaf_Cycles", "SWEEP Leaf Reference Color Calibration", "Saturation"
            ),
            "color_value": node_input_value(
                "SWEEP_LSystem_Leaf_Cycles", "SWEEP Leaf Reference Color Calibration", "Value"
            ),
        },
        "stem_shader": {
            "material": "SWEEP_LSystem_Stem_Cycles",
            "base_color": principled_value("SWEEP_LSystem_Stem_Cycles", "Base Color"),
            "roughness": principled_value("SWEEP_LSystem_Stem_Cycles", "Roughness"),
            "specular_ior_level": principled_value("SWEEP_LSystem_Stem_Cycles", "Specular IOR Level"),
            "emission_color": principled_value("SWEEP_LSystem_Stem_Cycles", "Emission Color"),
            "emission_strength": principled_value("SWEEP_LSystem_Stem_Cycles", "Emission Strength"),
        },
        "soil_shader": {
            "material": "SWEEP_Ground_Soil_Displaced_Cycles",
            "specular_ior_level": principled_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "Specular IOR Level"
            ),
            "normal_strength": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Scan Normal", "Strength"
            ),
            "height_bump_strength": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Fine Aggregate Bump", "Strength"
            ),
            "height_bump_distance_m": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Fine Aggregate Bump", "Distance"
            ),
            "crack_bump_strength": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Crack Bump", "Strength"
            ),
            "crack_bump_distance_m": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Crack Bump", "Distance"
            ),
            "color_saturation": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Reference Color Calibration", "Saturation"
            ),
            "color_value": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Reference Color Calibration", "Value"
            ),
            "warm_tint_factor": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Arizona Sandy-Loam Warm Tint", "Factor"
            ),
            "warm_tint_linear_rgba": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Arizona Sandy-Loam Warm Tint", "Color2"
            ),
            "dirt_mix_minimum": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Dirt Mix Fraction", "To Min"
            ),
            "dirt_mix_maximum": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Dirt Mix Fraction", "To Max"
            ),
            "material_displacement_scale_m": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Material Displacement", "Scale"
            ),
            "material_displacement_midlevel": node_input_value(
                "SWEEP_Ground_Soil_Displaced_Cycles", "SWEEP Soil Material Displacement", "Midlevel"
            ),
        },
        "soil_context": soil_context_report(),
        "landscape": background.landscape_report(args.background_variant),
        "world": {
            "sky_type": sky.sky_type if sky else None,
            "sun_elevation": sky.sun_elevation if sky else None,
            "sun_rotation": sky.sun_rotation if sky else None,
            "sun_intensity": getattr(sky, "sun_intensity", None) if sky else None,
            "sun_size": getattr(sky, "sun_size", None) if sky else None,
            "altitude": getattr(sky, "altitude", None) if sky else None,
            "air_density": getattr(sky, "air_density", None) if sky else None,
            "aerosol_density": getattr(sky, "aerosol_density", None) if sky else None,
            "ozone_density": getattr(sky, "ozone_density", None) if sky else None,
        },
        "color_management": {
            "view_transform": bpy.context.scene.view_settings.view_transform,
            "look": bpy.context.scene.view_settings.look,
            "exposure": bpy.context.scene.view_settings.exposure,
            "gamma": bpy.context.scene.view_settings.gamma,
        },
    }
    (args.output_dir.parent / f"{args.session}_blender_render_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
