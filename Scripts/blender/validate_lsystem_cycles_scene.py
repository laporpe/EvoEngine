"""Validate authored rendering parameters in a saved sorghum Cycles scene."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy


LEAF_MATERIAL = "SWEEP_LSystem_Leaf_Cycles"
GROUND_MATERIAL = "SWEEP_Ground_Soil_Displaced_Cycles"
PARBAR_MATERIALS = {
    "SWEEP_PARBAR_Brushed_White_Metal_Cycles": {
        "Base Color": (0.82, 0.82, 0.78, 1.0),
        "Metallic": 1.0,
        "Roughness": 0.38,
        "Specular IOR Level": 1.0,
        "Diffuse Roughness": 0.55,
    },
    "SWEEP_PARBAR_Long_Bar_Plastic_Cycles": {
        "Base Color": (0.74, 0.75, 0.70, 1.0),
        "Metallic": 0.0,
        "Roughness": 0.48,
        "Specular IOR Level": 0.46,
        "Diffuse Roughness": 0.6,
    },
    "SWEEP_PARBAR_Solar_Panel_Plastic_Cycles": {
        "Base Color": (0.05, 0.075, 0.105, 1.0),
        "Metallic": 0.0,
        "Roughness": 0.36,
        "Specular IOR Level": 0.58,
        "Diffuse Roughness": 0.5,
    },
}
LEAF_PRINCIPLED_DEFAULTS = {
    "Metallic": 0.0,
    "Roughness": 0.55,
    "Subsurface Weight": 0.06,
    "Subsurface Scale": 0.009,
    "Subsurface Radius": (0.55, 0.78, 0.36),
    "Specular IOR Level": 0.35,
    "Sheen Weight": 0.07,
    "Sheen Roughness": 0.5,
}
NISHITA_SKY_DEFAULTS = {
    "sky_type": "MULTIPLE_SCATTERING",
    "sun_disc": True,
    "sun_elevation": math.radians(55.0),
    "sun_rotation": math.radians(135.0),
    "sun_intensity": 0.35,
    "sun_size": math.radians(0.53),
    "altitude": 100.0,
    "air_density": 1.0,
    "aerosol_density": 0.05,
    "ozone_density": 1.0,
}
CAMERA_MATRIX_WORLD = (
    (0.5074188113212585, 0.05051324889063835, -0.8602177500724792, -4.723331451416016),
    (-0.8616995811462402, 0.02965959720313549, -0.506551206111908, 4.0044684410095215),
    (-0.00007383651973214, 0.9982829093933105, 0.05857708305120468, 1.859767198562622),
    (0.0, 0.0, 0.0, 1.0),
)
CAMERA_DATA_DEFAULTS = {
    "type": "PERSP",
    "lens": 32.0,
    "sensor_fit": "AUTO",
    "sensor_width": 36.0,
    "sensor_height": 24.0,
    "shift_x": 0.0,
    "shift_y": 0.0,
    "clip_start": 0.1,
    "clip_end": 96.27936553955078,
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evoengine-manifest", type=Path)
    parser.add_argument("--expected-source-scene")
    parser.add_argument("--expected-samples", type=int, required=True)
    parser.add_argument("--expected-resolution-x", type=int, required=True)
    parser.add_argument("--expected-resolution-y", type=int, required=True)
    parser.add_argument("--expect-ground", action="store_true")
    parser.add_argument("--expected-ground-strength", type=float, default=0.5)
    parser.add_argument("--expected-ground-midpoint", type=float, default=0.5)
    parser.add_argument("--expected-material-displacement", type=float, default=0.08)
    return parser.parse_args(argv)


def plain(value):
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        return value
    try:
        return [plain(item) for item in value]
    except TypeError:
        return str(value)


class Audit:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def equal(self, label: str, actual, expected, tolerance: float = 1.0e-5) -> None:
        actual = plain(actual)
        expected = plain(expected)
        if isinstance(expected, list):
            if not isinstance(actual, list) or len(actual) != len(expected):
                self.failures.append(f"{label}: expected {expected!r}, got {actual!r}")
                return
            for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
                self.equal(f"{label}[{index}]", actual_item, expected_item, tolerance)
            return
        if isinstance(expected, float):
            if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, abs_tol=tolerance, rel_tol=tolerance):
                self.failures.append(f"{label}: expected {expected!r}, got {actual!r}")
            return
        if actual != expected:
            self.failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def input_value(node: bpy.types.Node, name: str, audit: Audit):
    if name not in node.inputs:
        audit.failures.append(f"{node.name}: missing input {name!r}")
        return None
    return node.inputs[name].default_value


def check_inputs(node: bpy.types.Node, expected: dict[str, object], audit: Audit, prefix: str) -> None:
    for name, value in expected.items():
        audit.equal(f"{prefix}.{name}", input_value(node, name, audit), value)


def node_by_type(nodes, node_type: str, audit: Audit, label: str) -> bpy.types.Node | None:
    matches = [node for node in nodes if node.type == node_type]
    audit.require(len(matches) == 1, f"{label}: expected one {node_type} node, found {len(matches)}")
    return matches[0] if len(matches) == 1 else None


def node_by_label(nodes, label: str, audit: Audit) -> bpy.types.Node | None:
    matches = [node for node in nodes if node.label == label]
    audit.require(len(matches) == 1, f"expected one node labeled {label!r}, found {len(matches)}")
    return matches[0] if len(matches) == 1 else None


def resolved_image_path(image: bpy.types.Image) -> Path | None:
    if not image or image.source != "FILE" or not image.filepath:
        return None
    return Path(bpy.path.abspath(image.filepath)).resolve()


def node_snapshot(node: bpy.types.Node) -> dict[str, object]:
    result: dict[str, object] = {
        "name": node.name,
        "label": node.label,
        "type": node.type,
        "bl_idname": node.bl_idname,
        "inputs": {
            socket.name: {"value": plain(getattr(socket, "default_value", None)), "linked": socket.is_linked}
            for socket in node.inputs
        },
    }
    image = getattr(node, "image", None)
    if image:
        path = resolved_image_path(image)
        result["image"] = {
            "name": image.name,
            "filepath": str(path) if path else image.filepath,
            "exists": bool(path and path.exists()),
            "colorspace": image.colorspace_settings.name,
        }
    for name in ("blend_type", "data_type", "factor_mode", "operation", "interpolation", "extension", "sky_type"):
        if hasattr(node, name):
            result[name] = plain(getattr(node, name))
    if node.type == "VALTORGB":
        result["color_ramp"] = [
            {"position": element.position, "color": plain(element.color)} for element in node.color_ramp.elements
        ]
    return result


def material_snapshot(material: bpy.types.Material) -> dict[str, object]:
    tree = material.node_tree
    result = {
        "name": material.name,
        "use_nodes": material.use_nodes,
        "use_backface_culling": material.use_backface_culling,
        "nodes": [node_snapshot(node) for node in tree.nodes] if tree else [],
        "links": [
            f"{link.from_node.name}.{link.from_socket.name} -> {link.to_node.name}.{link.to_socket.name}"
            for link in tree.links
        ] if tree else [],
    }
    for name in (
        "blend_method",
        "surface_render_method",
        "show_transparent_back",
        "displacement_method",
        "max_vertex_displacement",
    ):
        if hasattr(material, name):
            result[name] = plain(getattr(material, name))
    return result


def validate_images(material: bpy.types.Material, labels: dict[str, str], audit: Audit) -> None:
    nodes = material.node_tree.nodes
    for label, expected_colorspace in labels.items():
        node = node_by_label(nodes, label, audit)
        if not node:
            continue
        audit.require(node.type == "TEX_IMAGE", f"{material.name}.{label}: node is not an image texture")
        image = getattr(node, "image", None)
        audit.require(image is not None, f"{material.name}.{label}: no image is assigned")
        if not image:
            continue
        path = resolved_image_path(image)
        audit.require(bool(path and path.exists()), f"{material.name}.{label}: image file is missing ({path})")
        audit.equal(f"{material.name}.{label}.colorspace", image.colorspace_settings.name, expected_colorspace)


def validate_leaf(audit: Audit) -> tuple[dict[str, object] | None, int]:
    material = bpy.data.materials.get(LEAF_MATERIAL)
    audit.require(material is not None, f"missing material {LEAF_MATERIAL}")
    if not material or not material.node_tree:
        return None, 0
    if hasattr(material, "blend_method"):
        audit.equal("leaf.blend_method", material.blend_method, "HASHED")
    audit.equal("leaf.use_backface_culling", material.use_backface_culling, False)
    if hasattr(material, "show_transparent_back"):
        audit.equal("leaf.show_transparent_back", material.show_transparent_back, True)
    if hasattr(material, "max_vertex_displacement"):
        audit.equal("leaf.max_vertex_displacement", material.max_vertex_displacement, 0.003)

    nodes = material.node_tree.nodes
    bsdf = node_by_type(nodes, "BSDF_PRINCIPLED", audit, "leaf")
    output = node_by_type(nodes, "OUTPUT_MATERIAL", audit, "leaf")
    if bsdf:
        check_inputs(bsdf, LEAF_PRINCIPLED_DEFAULTS, audit, "leaf.principled")
        for socket_name in ("Base Color", "Alpha", "Roughness", "Metallic", "Normal"):
            if socket_name in bsdf.inputs:
                audit.require(bsdf.inputs[socket_name].is_linked, f"leaf.principled.{socket_name} is not linked")
    if output:
        audit.require(output.inputs["Displacement"].is_linked, "leaf material displacement output is not linked")
    color_calibration = node_by_label(nodes, "SWEEP reference-photo color calibration", audit)
    if color_calibration:
        audit.require(color_calibration.type == "HUE_SAT", "leaf color calibration is not a Hue/Saturation node")
        check_inputs(color_calibration, {"Saturation": 1.05, "Value": 0.88}, audit, "leaf.color")

    validate_images(
        material,
        {
            "albedo": "sRGB",
            "ao": "Non-Color",
            "roughness": "Non-Color",
            "metallic": "Non-Color",
            "normal": "Non-Color",
            "height": "Non-Color",
        },
        audit,
    )
    authored_nodes = {
        "authored leaf normal": {"Strength": 0.6},
        "authored leaf height micro-bump": {"Strength": 0.012, "Distance": 0.004},
        "authored elongated leaf grain mapping": {"Scale": (0.22, 9.0, 1.0)},
        "elongated grain displacement": {"Scale": 34.0, "Detail": 14.0, "Roughness": 0.62},
        "authored elongated leaf grain bump": {"Strength": 0.008, "Distance": 0.003},
        "authored leaf micro-displacement": {"Scale": 0.001, "Midlevel": 0.5},
    }
    for label, expected in authored_nodes.items():
        node = node_by_label(nodes, label, audit)
        if node:
            check_inputs(node, expected, audit, f"leaf.{label}")
    ramp = node_by_label(nodes, "authored elongated leaf grain ramp", audit)
    if ramp and ramp.type == "VALTORGB":
        audit.equal("leaf.grain_ramp.low", ramp.color_ramp.elements[0].position, 0.32)
        audit.equal("leaf.grain_ramp.high", ramp.color_ramp.elements[1].position, 0.86)
    mixes = [node for node in nodes if node.type == "MIX" and getattr(node, "blend_type", "") == "MULTIPLY"]
    audit.require(len(mixes) == 1, f"leaf AO multiply: expected one node, found {len(mixes)}")
    if len(mixes) == 1:
        audit.equal("leaf.ao_multiply.factor", input_value(mixes[0], "Factor", audit), 0.35)

    assigned = sum(
        1
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(slot.material == material for slot in obj.material_slots)
    )
    audit.require(assigned > 0, "leaf material is not assigned to any mesh object")
    return material_snapshot(material), assigned


def validate_principled_material(name: str, expected: dict[str, object], audit: Audit) -> dict[str, object] | None:
    material = bpy.data.materials.get(name)
    audit.require(material is not None, f"missing material {name}")
    if not material or not material.node_tree:
        return None
    bsdf = node_by_type(material.node_tree.nodes, "BSDF_PRINCIPLED", audit, name)
    if bsdf:
        check_inputs(bsdf, expected, audit, name)
    assigned = sum(
        1
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(slot.material == material for slot in obj.material_slots)
    )
    audit.require(assigned > 0, f"{name} is not assigned to any mesh object")
    snapshot = material_snapshot(material)
    snapshot["assigned_mesh_objects"] = assigned
    return snapshot


def validate_ground(args: argparse.Namespace, audit: Audit) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not args.expect_ground:
        return None, None
    material = bpy.data.materials.get(GROUND_MATERIAL)
    audit.require(material is not None, f"missing material {GROUND_MATERIAL}")
    if not material or not material.node_tree:
        return None, None
    nodes = material.node_tree.nodes
    bsdf = node_by_type(nodes, "BSDF_PRINCIPLED", audit, "ground")
    output = node_by_type(nodes, "OUTPUT_MATERIAL", audit, "ground")
    if bsdf:
        check_inputs(bsdf, {"Metallic": 0.0, "Roughness": 0.72}, audit, "ground.principled")
        for socket_name in ("Base Color", "Roughness", "Normal"):
            audit.require(bsdf.inputs[socket_name].is_linked, f"ground.principled.{socket_name} is not linked")
    if output:
        audit.require(output.inputs["Displacement"].is_linked, "ground material displacement output is not linked")
    validate_images(
        material,
        {
            "soil albedo": "sRGB",
            "soil ao": "Non-Color",
            "soil roughness": "Non-Color",
            "soil normal": "Non-Color",
            "soil height micro-bump": "Non-Color",
        },
        audit,
    )
    normal = next((node for node in nodes if node.type == "NORMAL_MAP"), None)
    bump = next((node for node in nodes if node.type == "BUMP"), None)
    displacement = next((node for node in nodes if node.type == "DISPLACEMENT"), None)
    audit.require(normal is not None, "ground normal-map node is missing")
    audit.require(bump is not None, "ground bump node is missing")
    audit.require(displacement is not None, "ground displacement node is missing")
    if normal:
        check_inputs(normal, {"Strength": 0.42}, audit, "ground.normal")
    if bump:
        check_inputs(bump, {"Strength": 0.08, "Distance": 0.018}, audit, "ground.bump")
    if displacement:
        check_inputs(
            displacement,
            {"Scale": args.expected_material_displacement, "Midlevel": 0.5},
            audit,
            "ground.displacement",
        )
    color_calibration = node_by_label(nodes, "SWEEP reference-photo color calibration", audit)
    if color_calibration:
        audit.require(color_calibration.type == "HUE_SAT", "ground color calibration is not a Hue/Saturation node")
        check_inputs(color_calibration, {"Saturation": 1.75, "Value": 0.15}, audit, "ground.color")

    ground_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and any(slot.material == material for slot in obj.material_slots)
    ]
    audit.require(len(ground_objects) == 1, f"expected one ground object using {GROUND_MATERIAL}, found {len(ground_objects)}")
    if len(ground_objects) != 1:
        return material_snapshot(material), None
    ground = ground_objects[0]
    modifiers = [modifier for modifier in ground.modifiers if modifier.name == "SWEEP Ground Height Displacement"]
    audit.require(len(modifiers) == 1, f"expected one ground Geometry Nodes modifier, found {len(modifiers)}")
    group = modifiers[0].node_group if len(modifiers) == 1 else None
    audit.require(group is not None, "ground Geometry Nodes modifier has no node group")
    group_snapshot = None
    if group:
        subtract = next((node for node in group.nodes if node.type == "MATH" and node.operation == "SUBTRACT"), None)
        multiply = next((node for node in group.nodes if node.type == "MATH" and node.operation == "MULTIPLY"), None)
        audit.require(subtract is not None, "ground Geometry Nodes midpoint node is missing")
        audit.require(multiply is not None, "ground Geometry Nodes strength node is missing")
        if subtract:
            audit.equal("ground.geometry_nodes.midpoint", subtract.inputs[1].default_value, args.expected_ground_midpoint)
        if multiply:
            audit.equal("ground.geometry_nodes.strength", multiply.inputs[1].default_value, args.expected_ground_strength)
        group_snapshot = {
            "name": group.name,
            "nodes": [node_snapshot(node) for node in group.nodes],
            "links": [
                f"{link.from_node.name}.{link.from_socket.name} -> {link.to_node.name}.{link.to_socket.name}"
                for link in group.links
            ],
        }
    return material_snapshot(material), {
        "name": ground.name,
        "vertices": len(ground.data.vertices),
        "polygons": len(ground.data.polygons),
        "modifiers": [modifier.name for modifier in ground.modifiers],
        "geometry_nodes": group_snapshot,
    }


def validate_world(audit: Audit) -> dict[str, object] | None:
    world = bpy.context.scene.world
    audit.require(world is not None, "scene has no world")
    audit.require(bool(world and world.use_nodes and world.node_tree), "scene world has no node tree")
    if not world or not world.node_tree:
        return None
    nodes = world.node_tree.nodes
    sky = node_by_type(nodes, "TEX_SKY", audit, "world")
    background = node_by_label(nodes, "SWEEP environment lighting", audit)
    camera_background = node_by_label(nodes, "SWEEP camera-visible sky", audit)
    light_path = node_by_label(nodes, "SWEEP camera-ray sky selector", audit)
    mix = node_by_label(nodes, "SWEEP camera/environment world mix", audit)
    output = node_by_type(nodes, "OUTPUT_WORLD", audit, "world")
    if sky:
        for name, expected in NISHITA_SKY_DEFAULTS.items():
            audit.require(hasattr(sky, name), f"Sky Texture is missing Nishita property {name}")
            if hasattr(sky, name):
                audit.equal(f"world.nishita.{name}", getattr(sky, name), expected)
    if background:
        audit.require(background.type == "BACKGROUND", "environment-lighting node is not a Background shader")
        audit.equal("world.background.strength", background.inputs["Strength"].default_value, 0.65)
        audit.require(background.inputs["Color"].is_linked, "Nishita sky is not linked to the world background")
    if camera_background:
        audit.require(camera_background.type == "BACKGROUND", "camera-visible sky is not a Background shader")
        audit.equal("world.camera_background.strength", camera_background.inputs["Strength"].default_value, 1.40)
        audit.require(camera_background.inputs["Color"].is_linked, "Nishita sky is not linked to the camera background")
    if light_path:
        audit.require(light_path.type == "LIGHT_PATH", "camera-ray selector is not a Light Path node")
    if mix:
        audit.require(mix.type == "MIX_SHADER", "camera/environment world mix is not a Mix Shader")
        for index in range(3):
            audit.require(mix.inputs[index].is_linked, f"world mix input {index} is not linked")
    if output:
        audit.require(output.inputs["Surface"].is_linked, "world mix is not linked to world output")
    sun_objects = [obj.name for obj in bpy.context.scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN"]
    audit.require(not sun_objects, f"authored Nishita world should have no separate Sun objects: {sun_objects}")
    return {
        "name": world.name,
        "model": "Nishita",
        "sky": node_snapshot(sky) if sky else None,
        "sky_parameters": {name: plain(getattr(sky, name, None)) for name in NISHITA_SKY_DEFAULTS} if sky else None,
        "background": node_snapshot(background) if background else None,
        "camera_background": node_snapshot(camera_background) if camera_background else None,
        "light_path": node_snapshot(light_path) if light_path else None,
        "mix": node_snapshot(mix) if mix else None,
        "links": [
            f"{link.from_node.name}.{link.from_socket.name} -> {link.to_node.name}.{link.to_socket.name}"
            for link in world.node_tree.links
        ],
        "sun_objects": sun_objects,
    }


def validate_scene_settings(args: argparse.Namespace, audit: Audit) -> dict[str, object]:
    scene = bpy.context.scene
    audit.equal("render.engine", scene.render.engine, "CYCLES")
    audit.equal("cycles.samples", scene.cycles.samples, args.expected_samples)
    audit.equal("render.resolution_x", scene.render.resolution_x, args.expected_resolution_x)
    audit.equal("render.resolution_y", scene.render.resolution_y, args.expected_resolution_y)
    audit.equal("cycles.use_denoising", scene.cycles.use_denoising, True)
    audit.equal("view.exposure", scene.view_settings.exposure, -0.9)
    audit.equal("view.gamma", scene.view_settings.gamma, 1.0)
    audit.equal("view.view_transform", scene.view_settings.view_transform, "AgX")
    audit.require(
        scene.view_settings.look in {"AgX - Medium High Contrast", "Medium High Contrast"},
        f"view.look: expected the authored AgX Medium High Contrast look, got {scene.view_settings.look!r}",
    )
    camera = scene.camera
    audit.require(camera is not None, "scene has no active camera")
    if camera:
        audit.equal("camera.name", camera.name, "Cycles Paper Camera")
        audit.equal("camera.matrix_world", camera.matrix_world, CAMERA_MATRIX_WORLD)
        for property_name, expected in CAMERA_DATA_DEFAULTS.items():
            audit.equal(f"camera.{property_name}", getattr(camera.data, property_name), expected)
        audit.equal("camera.dof.use_dof", camera.data.dof.use_dof, False)
    return {
        "engine": scene.render.engine,
        "cycles": {
            "samples": scene.cycles.samples,
            "use_denoising": scene.cycles.use_denoising,
            "device": scene.cycles.device,
            "max_bounces": scene.cycles.max_bounces,
            "diffuse_bounces": scene.cycles.diffuse_bounces,
            "glossy_bounces": scene.cycles.glossy_bounces,
            "transparent_max_bounces": scene.cycles.transparent_max_bounces,
        },
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "view": {
            "view_transform": scene.view_settings.view_transform,
            "look": scene.view_settings.look,
            "exposure": scene.view_settings.exposure,
            "gamma": scene.view_settings.gamma,
        },
        "camera": {
            "name": camera.name,
            "matrix_world": plain(camera.matrix_world),
            "location": plain(camera.location),
            "rotation_euler": plain(camera.rotation_euler),
            "data": {name: plain(getattr(camera.data, name)) for name in CAMERA_DATA_DEFAULTS},
            "dof_use": camera.data.dof.use_dof,
        } if camera else None,
    }


def validate_manifest(args: argparse.Namespace, audit: Audit) -> dict[str, object] | None:
    if not args.evoengine_manifest:
        return None
    path = args.evoengine_manifest.resolve()
    audit.require(path.exists(), f"EvoEngine export manifest is missing: {path}")
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    audit.equal("manifest.schema", manifest.get("schema"), "evoengine_lsystem_blender_export_manifest_v1")
    audit.equal("manifest.growth_mode", manifest.get("growth_mode"), "preserve_scene_lsystems")
    audit.equal("manifest.sorghum_ls", manifest.get("sorghum_ls"), 40)
    audit.require((manifest.get("mesh_renderers") or 0) > 0, "manifest reports no exported mesh renderers")
    if args.expected_source_scene:
        actual_scene = manifest.get("source_scene", "").replace("\\", "/")
        expected_scene = args.expected_source_scene.replace("\\", "/")
        audit.equal("manifest.source_scene", actual_scene, expected_scene)
    return manifest


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.report = args.report.resolve()
    if args.evoengine_manifest:
        args.evoengine_manifest = args.evoengine_manifest.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))

    audit = Audit()
    manifest = validate_manifest(args, audit)
    world = validate_world(audit)
    leaf, leaf_assignments = validate_leaf(audit)
    parbar = {
        name: validate_principled_material(name, expected, audit)
        for name, expected in PARBAR_MATERIALS.items()
    }
    stem_materials = [material for material in bpy.data.materials if material.name.startswith("SWEEP_Stem_VertexColor_")]
    audit.require(bool(stem_materials), "no authored stem materials were found")
    for material in stem_materials:
        bsdf = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        audit.require(bsdf is not None, f"{material.name}: Principled BSDF is missing")
        if bsdf:
            check_inputs(bsdf, {"Metallic": 0.0, "Roughness": 0.72}, audit, material.name)
    ground_material, ground = validate_ground(args, audit)
    settings = validate_scene_settings(args, audit)

    report = {
        "schema": "sweep_blender_scene_validation_v1",
        "passed": not audit.failures,
        "failures": audit.failures,
        "blend": str(args.blend),
        "blender_version": bpy.app.version_string,
        "evoengine_manifest": manifest,
        "scene": {
            "objects": len(bpy.context.scene.objects),
            "mesh_objects": sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH"),
            "materials": len(bpy.data.materials),
            "leaf_material_assignments": leaf_assignments,
            "stem_materials": len(stem_materials),
        },
        "settings": settings,
        "world": world,
        "materials": {
            "leaf": leaf,
            "stems": [material_snapshot(material) for material in stem_materials],
            "parbar": parbar,
            "ground": ground_material,
        },
        "ground": ground,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"SWEEP_BLENDER_SCENE_VALIDATION {'passed' if report['passed'] else 'failed'} report={args.report}")
    if audit.failures:
        raise RuntimeError("Blender scene validation failed:\n" + "\n".join(audit.failures))


if __name__ == "__main__":
    main()
