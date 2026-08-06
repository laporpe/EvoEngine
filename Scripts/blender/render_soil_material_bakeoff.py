"""Render fixed-scale soil material candidates under the production field lighting.

This is a presentation-only validation scene.  It opens an existing exported field
blend to inherit its Nishita sky, color management, and Cycles configuration, then
hides every scientific object and renders a new 1.2 m comparison patch.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = (
    ROOT
    / "Resources"
    / "DigitalAgricultureProject"
    / "Assets"
    / "ManualAssets"
    / "Soil"
    / "ScannedPBR"
    / "PolyHaven"
)
VARIANTS = (
    "production_control",
    "legacy_corrected",
    "dirt_scan",
    "brown_mud_scan",
    "hybrid_scan",
    "brown_mud_warm",
    "hybrid_warm",
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=820)
    return parser.parse_args(argv)


def set_input(node: bpy.types.Node, name: str, value) -> None:
    if name in node.inputs:
        node.inputs[name].default_value = value


def load_image(path: Path, colorspace: str) -> bpy.types.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass
    return image


def hide_source_scene() -> None:
    for obj in bpy.context.scene.objects:
        obj.hide_render = True


def create_patch() -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=257, y_segments=257, size=0.6)
    mesh = bpy.data.meshes.new("SWEEP Soil Validation 1.2m Patch Mesh")
    bm.to_mesh(mesh)
    bm.free()
    patch = bpy.data.objects.new("SWEEP Soil Validation 1.2m Patch", mesh)
    patch["sweep_ownership"] = "blender_presentation_only_validation"
    patch["scientific_geometry"] = False
    patch["physical_width_m"] = 1.2
    bpy.context.scene.collection.objects.link(patch)
    for polygon in patch.data.polygons:
        polygon.use_smooth = True
    return patch


def new_material(name: str) -> tuple[bpy.types.Material, bpy.types.Node, bpy.types.Node]:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (760, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (500, 100)
    bsdf.name = "SWEEP Soil Principled BSDF"
    material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    set_input(bsdf, "Metallic", 0.0)
    set_input(bsdf, "Specular IOR Level", 0.5)
    set_input(bsdf, "Coat Weight", 0.0)
    if hasattr(material, "displacement_method"):
        material.displacement_method = "DISPLACEMENT"
    if hasattr(material, "max_vertex_displacement"):
        material.max_vertex_displacement = 0.10
    return material, bsdf, output


def object_coordinates(material: bpy.types.Material, patch: bpy.types.Object, scale_per_m: float, name: str):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    coordinates = nodes.new("ShaderNodeTexCoord")
    coordinates.object = patch
    coordinates.location = (-1500, 0)
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.name = name
    scale.inputs["Scale"].default_value = scale_per_m
    scale.location = (-1300, 0)
    links.new(coordinates.outputs["Object"], scale.inputs[0])
    return scale.outputs["Vector"]


def image_node(material: bpy.types.Material, path: Path, colorspace: str, coordinates, name: str, y: int):
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.name = name
    node.label = path.name
    node.image = load_image(path, colorspace)
    node.extension = "REPEAT"
    node.interpolation = "Cubic"
    node.location = (-980, y)
    material.node_tree.links.new(coordinates, node.inputs["Vector"])
    return node


def attach_scan_layer(
    material: bpy.types.Material,
    patch: bpy.types.Object,
    asset: str,
    prefix: str,
    physical_width_m: float,
) -> dict[str, object]:
    directory = SCAN_ROOT / asset
    coordinates = object_coordinates(material, patch, 1.0 / physical_width_m, f"{prefix} Physical Scale")
    files = {
        "diffuse": directory / f"{asset}_diffuse.jpg",
        "roughness": directory / f"{asset}_rough.exr",
        "normal": directory / f"{asset}_nor_gl.png",
        "displacement": directory / f"{asset}_displacement.exr",
        "bump": directory / f"{asset}_bump.exr",
    }
    diffuse = image_node(material, files["diffuse"], "sRGB", coordinates, f"{prefix} Diffuse", 420)
    roughness = image_node(material, files["roughness"], "Non-Color", coordinates, f"{prefix} Roughness", 180)
    normal = image_node(material, files["normal"], "Non-Color", coordinates, f"{prefix} Normal", -60)
    displacement = image_node(
        material, files["displacement"], "Non-Color", coordinates, f"{prefix} Displacement", -300
    )
    bump = None
    if files["bump"].is_file():
        bump = image_node(material, files["bump"], "Non-Color", coordinates, f"{prefix} Bump", -540)
    return {
        "diffuse": diffuse.outputs["Color"],
        "roughness": roughness.outputs["Color"],
        "normal": normal.outputs["Color"],
        "displacement": displacement.outputs["Color"],
        "bump": bump.outputs["Color"] if bump else displacement.outputs["Color"],
        "files": {key: str(value.resolve()) for key, value in files.items() if value.is_file()},
        "physical_width_m": physical_width_m,
    }


def make_scan_material(patch: bpy.types.Object, variant: str) -> tuple[bpy.types.Material, dict[str, object]]:
    material, bsdf, output = new_material(f"SWEEP Soil Bakeoff {variant}")
    links = material.node_tree.links
    nodes = material.node_tree.nodes
    if variant == "dirt_scan":
        layers = [(attach_scan_layer(material, patch, "dirt", "Dirt", 2.0), 1.0)]
        color_value, color_saturation, displacement_scale, displacement_midlevel = 1.28, 0.82, 0.030, 0.5
    elif variant in {"brown_mud_scan", "brown_mud_warm"}:
        layers = [(attach_scan_layer(material, patch, "brown_mud_dry", "Brown Mud Dry", 1.3), 1.0)]
        color_value = 0.64 if variant == "brown_mud_warm" else 1.12
        color_saturation = 1.05 if variant == "brown_mud_warm" else 0.95
        displacement_scale, displacement_midlevel = 0.045, 0.6
    else:
        brown = attach_scan_layer(material, patch, "brown_mud_dry", "Brown Mud Dry", 1.3)
        dirt = attach_scan_layer(material, patch, "dirt", "Dirt", 2.0)
        mask_coordinates = object_coordinates(material, patch, 0.33, "Hybrid Macro Mask Scale")
        mask = nodes.new("ShaderNodeTexNoise")
        mask.name = "SWEEP Compacted Patch Mask"
        mask.inputs["Scale"].default_value = 1.0
        mask.inputs["Detail"].default_value = 3.0
        mask.inputs["Roughness"].default_value = 0.6
        mask.location = (-850, 700)
        links.new(mask_coordinates, mask.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.name = "SWEEP Compacted Patch Coverage"
        ramp.color_ramp.elements[0].position = 0.38
        ramp.color_ramp.elements[1].position = 0.70
        ramp.location = (-620, 700)
        links.new(mask.outputs["Factor"], ramp.inputs["Factor"])
        layers = [(brown, ramp.outputs["Color"]), (dirt, ramp.outputs["Color"])]
        color_value = 0.68 if variant == "hybrid_warm" else 1.16
        color_saturation = 1.02 if variant == "hybrid_warm" else 0.92
        displacement_scale, displacement_midlevel = 0.038, 0.55

    if len(layers) == 1:
        color = layers[0][0]["diffuse"]
        roughness = layers[0][0]["roughness"]
        normal_color = layers[0][0]["normal"]
        displacement_height = layers[0][0]["displacement"]
        bump_height = layers[0][0]["bump"]
    else:
        brown, dirt = layers[0][0], layers[1][0]
        factor = layers[0][1]
        mixed = []
        for index, channel in enumerate(("diffuse", "roughness", "normal", "displacement", "bump")):
            mix = nodes.new("ShaderNodeMixRGB")
            mix.name = f"SWEEP Hybrid {channel.title()}"
            mix.location = (-280, 520 - index * 190)
            links.new(factor, mix.inputs["Factor"])
            links.new(brown[channel], mix.inputs["Color1"])
            links.new(dirt[channel], mix.inputs["Color2"])
            mixed.append(mix.outputs["Color"])
        color, roughness, normal_color, displacement_height, bump_height = mixed

    calibration = nodes.new("ShaderNodeHueSaturation")
    calibration.name = "SWEEP Soil Reference Color Calibration"
    calibration.inputs["Saturation"].default_value = color_saturation
    calibration.inputs["Value"].default_value = color_value
    calibration.location = (130, 430)
    links.new(color, calibration.inputs["Color"])
    calibrated_color = calibration.outputs["Color"]
    warm_tint_factor = 0.0
    if variant in {"brown_mud_warm", "hybrid_warm"}:
        warm_tint_factor = 0.60
        warm_tint = nodes.new("ShaderNodeMixRGB")
        warm_tint.name = "SWEEP Arizona Sandy-Loam Warm Tint"
        warm_tint.blend_type = "MULTIPLY"
        warm_tint.inputs["Factor"].default_value = warm_tint_factor
        warm_tint.inputs["Color2"].default_value = (0.55, 0.23, 0.06, 1.0)
        warm_tint.location = (320, 430)
        links.new(calibrated_color, warm_tint.inputs["Color1"])
        calibrated_color = warm_tint.outputs["Color"]
    links.new(calibrated_color, bsdf.inputs["Base Color"])
    links.new(roughness, bsdf.inputs["Roughness"])

    normal = nodes.new("ShaderNodeNormalMap")
    normal.name = "SWEEP Soil Scan Normal"
    normal.inputs["Strength"].default_value = 1.0
    normal.location = (100, 0)
    links.new(normal_color, normal.inputs["Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.name = "SWEEP Soil Fine Bump"
    bump.inputs["Strength"].default_value = 0.30
    bump.inputs["Distance"].default_value = 0.003
    bump.location = (300, -70)
    links.new(bump_height, bump.inputs["Height"])
    links.new(normal.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    displacement = nodes.new("ShaderNodeDisplacement")
    displacement.name = "SWEEP Soil Scan Displacement"
    displacement.inputs["Scale"].default_value = displacement_scale
    displacement.inputs["Midlevel"].default_value = displacement_midlevel
    displacement.location = (490, -330)
    links.new(displacement_height, displacement.inputs["Height"])
    links.new(displacement.outputs["Displacement"], output.inputs["Displacement"])
    layer_report = [
        {"files": layer[0]["files"], "physical_width_m": layer[0]["physical_width_m"]} for layer in layers
    ]
    return material, {
        "layers": layer_report,
        "specular_ior_level": 0.5,
        "color_value": color_value,
        "color_saturation": color_saturation,
        "warm_tint_factor": warm_tint_factor,
        "warm_tint_linear_rgba": [0.55, 0.23, 0.06, 1.0] if warm_tint_factor else None,
        "displacement_scale_m": displacement_scale,
        "displacement_midlevel": displacement_midlevel,
        "bump_distance_m": 0.003,
    }


def make_legacy_material(patch: bpy.types.Object, corrected: bool) -> tuple[bpy.types.Material, dict[str, object]]:
    source = bpy.data.materials.get("SWEEP_Ground_Soil_Displaced_Cycles")
    if source is None:
        raise RuntimeError("production control material is missing")
    material = source.copy()
    material.name = "SWEEP Soil Bakeoff Legacy Corrected" if corrected else "SWEEP Soil Bakeoff Production Control"
    coordinates = material.node_tree.nodes.get("SWEEP Soil World Coordinates")
    if coordinates:
        coordinates.object = patch
    report = {"source_material": source.name, "corrected": corrected}
    if corrected:
        nodes = material.node_tree.nodes
        calibration = nodes.get("SWEEP Soil Reference Color Calibration")
        if calibration:
            calibration.inputs["Saturation"].default_value = 1.0
            calibration.inputs["Value"].default_value = 1.0
        bsdf = nodes.get("SWEEP Soil Principled BSDF")
        if bsdf:
            set_input(bsdf, "Specular IOR Level", 0.5)
        roughness = nodes.get("SWEEP Soil Dry Roughness")
        if roughness:
            roughness.color_ramp.elements[0].color = (0.48, 0.48, 0.48, 1.0)
            roughness.color_ramp.elements[1].color = (0.98, 0.98, 0.98, 1.0)
        displacement = nodes.get("SWEEP Soil Material Displacement")
        if displacement:
            displacement.inputs["Scale"].default_value = 0.018
        bump = nodes.get("SWEEP Soil PBR Height Bump")
        if bump:
            bump.inputs["Distance"].default_value = 0.004
        crack_color = nodes.get("SWEEP Soil Crack Color Strength")
        if crack_color:
            crack_color.inputs[1].default_value = 0.18
        crack_bump = nodes.get("SWEEP Soil Crack Bump")
        if crack_bump:
            crack_bump.inputs["Strength"].default_value = 0.15
        report.update(
            {
                "specular_ior_level": 0.5,
                "roughness_range": [0.48, 0.98],
                "color_saturation": 1.0,
                "color_value": 1.0,
                "displacement_scale_m": 0.018,
            }
        )
    return material, report


def simple_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material, bsdf, _ = new_material(name)
    set_input(bsdf, "Base Color", color)
    set_input(bsdf, "Roughness", 0.62)
    return material


def add_scale_bar() -> None:
    black = simple_material("SWEEP Scale Black", (0.015, 0.015, 0.015, 1.0))
    white = simple_material("SWEEP Scale White", (0.72, 0.72, 0.72, 1.0))
    for index in range(5):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-0.45 + index * 0.10, -0.51, 0.055))
        obj = bpy.context.object
        obj.name = f"SWEEP 10cm Scale {index + 1}"
        obj.scale = (0.05, 0.012, 0.008)
        obj.data.materials.append(black if index % 2 == 0 else white)
        obj["sweep_ownership"] = "blender_presentation_only_validation"


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def configure_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("SWEEP Soil Validation Camera")
    camera = bpy.data.objects.new(data.name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = (0.0, -1.25, 0.72)
    camera.data.lens = 58.0
    look_at(camera, Vector((0.0, 0.02, 0.0)))
    bpy.context.scene.camera = camera
    return camera


def configure_render(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        for device in preferences.devices:
            device.use = True
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.output = args.output.resolve()
    args.report = args.report.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    hide_source_scene()
    patch = create_patch()
    if args.variant == "production_control":
        material, settings = make_legacy_material(patch, corrected=False)
    elif args.variant == "legacy_corrected":
        material, settings = make_legacy_material(patch, corrected=True)
    else:
        material, settings = make_scan_material(patch, args.variant)
    patch.data.materials.append(material)
    add_scale_bar()
    camera = configure_camera()
    configure_render(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(args.output)
    bpy.ops.render.render(write_still=True)
    report = {
        "variant": args.variant,
        "source_blend": str(args.blend),
        "render": str(args.output),
        "ownership": "blender_presentation_only_validation",
        "scientific_scene_modified": False,
        "patch_width_m": 1.2,
        "patch_vertices": len(patch.data.vertices),
        "scale_bar_segments": 5,
        "scale_bar_segment_m": 0.10,
        "camera": {"location": list(camera.location), "lens_mm": camera.data.lens},
        "lighting_inherited_from_source_blend": True,
        "view_transform": bpy.context.scene.view_settings.look,
        "exposure": bpy.context.scene.view_settings.exposure,
        "samples": args.samples,
        "material": settings,
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
