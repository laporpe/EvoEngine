"""Render a fixed-camera, plant-free soil and PARBAR material study in Cycles.

This operates only on a copied Blender presentation scene.  It never changes the
EvoEngine scene, descriptor data, measured plant geometry, or illumination data.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SOIL_MATERIAL = "SWEEP_Ground_Soil_Displaced_Cycles"
METAL_MATERIAL = "SWEEP_PARBAR_Brushed_White_Metal_Cycles"
SENSOR_MATERIAL = "SWEEP_PARBAR_Long_Bar_Plastic_Cycles"
LEAF_MATERIAL = "SWEEP_LSystem_Leaf_Cycles"
STEM_MATERIAL = "SWEEP_LSystem_Stem_Cycles"
GROUND_OBJECT = "Ground Mesh"
PLANT_ROOT = re.compile(r"^Genotype[ABC]_LSystem_R\d+_C\d+$")


VARIANTS = (
    {
        "id": "01_current_dark_control",
        "description": "Saved-scene control: current dark clay-like soil and bright metal.",
        "soil": {
            "saturation": 1.75, "value": 0.15, "roughness": (0.88, 0.98),
            "macro_low": 0.72, "macro_factor": 0.32, "specular": 0.18,
            "normal": 0.85, "height_bump": (0.38, 0.010),
            "material_displacement": 0.012, "gn_relief": (0.035, 0.030),
            "crack_bump": (0.42, 0.0030), "crack_color": 0.74,
            "crack_region": (0.52, 0.66), "crack_profile": (0.008, 0.028),
            "micro": (150.0, 0.18, 0.0015),
        },
        "metal": {
            "label": "current bright metal", "low": (0.82, 0.82, 0.78, 1.0),
            "high": (0.82, 0.82, 0.78, 1.0), "roughness": (0.38, 0.38),
            "anisotropy": 0.0, "grain_scale": 35.0, "grain_strength": 0.0,
            "grain_distance": 0.0,
        },
    },
    {
        "id": "02_dry_tan_matte_aluminum",
        "description": "Brighter dry tan, restrained relief, matte aluminum hardware.",
        "soil": {
            "saturation": 0.95, "value": 0.24, "roughness": (0.93, 0.99),
            "macro_low": 0.80, "macro_factor": 0.28, "specular": 0.14,
            "normal": 1.00, "height_bump": (0.46, 0.012),
            "material_displacement": 0.015, "gn_relief": (0.042, 0.030),
            "crack_bump": (0.48, 0.0035), "crack_color": 0.66,
            "crack_region": (0.52, 0.66), "crack_profile": (0.008, 0.030),
            "micro": (175.0, 0.23, 0.0018),
        },
        "metal": {
            "label": "matte bead-blasted aluminum", "low": (0.38, 0.40, 0.41, 1.0),
            "high": (0.66, 0.68, 0.69, 1.0), "roughness": (0.30, 0.42),
            "anisotropy": 0.35, "grain_scale": 55.0, "grain_strength": 0.060,
            "grain_distance": 0.00055,
        },
    },
    {
        "id": "03_pale_dust_soft_relief",
        "description": "Pale dusty soil with gentle relief and broad satin aluminum highlights.",
        "soil": {
            "saturation": 0.65, "value": 0.33, "roughness": (0.95, 0.995),
            "macro_low": 0.86, "macro_factor": 0.25, "specular": 0.12,
            "normal": 0.72, "height_bump": (0.28, 0.007),
            "material_displacement": 0.008, "gn_relief": (0.026, 0.018),
            "crack_bump": (0.32, 0.0025), "crack_color": 0.50,
            "crack_region": (0.56, 0.70), "crack_profile": (0.008, 0.026),
            "micro": (125.0, 0.16, 0.0012),
        },
        "metal": {
            "label": "satin aluminum", "low": (0.46, 0.48, 0.50, 1.0),
            "high": (0.76, 0.78, 0.80, 1.0), "roughness": (0.28, 0.39),
            "anisotropy": 0.42, "grain_scale": 48.0, "grain_strength": 0.045,
            "grain_distance": 0.00045,
        },
    },
    {
        "id": "04_high_relief_brushed_aluminum",
        "description": "Pronounced clods and height relief with lower-roughness brushed aluminum.",
        "soil": {
            "saturation": 0.90, "value": 0.28, "roughness": (0.92, 0.99),
            "macro_low": 0.78, "macro_factor": 0.38, "specular": 0.13,
            "normal": 1.18, "height_bump": (0.64, 0.018),
            "material_displacement": 0.026, "gn_relief": (0.066, 0.050),
            "crack_bump": (0.56, 0.0045), "crack_color": 0.72,
            "crack_region": (0.50, 0.64), "crack_profile": (0.007, 0.032),
            "micro": (145.0, 0.30, 0.0022),
        },
        "metal": {
            "label": "strong brushed aluminum", "low": (0.32, 0.34, 0.36, 1.0),
            "high": (0.68, 0.70, 0.72, 1.0), "roughness": (0.19, 0.30),
            "anisotropy": 0.72, "grain_scale": 95.0, "grain_strength": 0.120,
            "grain_distance": 0.00075,
        },
    },
    {
        "id": "05_cracked_arid_galvanized",
        "description": "Most legible dry cracks, warm arid soil, galvanized zinc hardware.",
        "soil": {
            "saturation": 1.15, "value": 0.30, "roughness": (0.94, 0.995),
            "macro_low": 0.80, "macro_factor": 0.34, "specular": 0.11,
            "normal": 1.08, "height_bump": (0.54, 0.014),
            "material_displacement": 0.020, "gn_relief": (0.050, 0.038),
            "crack_bump": (0.82, 0.0070), "crack_color": 1.12,
            "crack_region": (0.42, 0.58), "crack_profile": (0.006, 0.040),
            "micro": (165.0, 0.28, 0.0020),
        },
        "metal": {
            "label": "mottled galvanized zinc", "low": (0.28, 0.30, 0.31, 1.0),
            "high": (0.73, 0.75, 0.74, 1.0), "roughness": (0.30, 0.49),
            "anisotropy": 0.18, "grain_scale": 24.0, "grain_strength": 0.105,
            "grain_distance": 0.00095,
        },
    },
    {
        "id": "06_granular_aggregate_weathered",
        "description": "Micro-granular aggregate and weathered, low-glare field hardware.",
        "soil": {
            "saturation": 0.75, "value": 0.29, "roughness": (0.95, 0.998),
            "macro_low": 0.75, "macro_factor": 0.42, "specular": 0.10,
            "normal": 1.24, "height_bump": (0.58, 0.016),
            "material_displacement": 0.018, "gn_relief": (0.045, 0.042),
            "crack_bump": (0.50, 0.0040), "crack_color": 0.64,
            "crack_region": (0.52, 0.67), "crack_profile": (0.008, 0.030),
            "micro": (235.0, 0.43, 0.0030),
        },
        "metal": {
            "label": "weathered aluminum", "low": (0.24, 0.26, 0.27, 1.0),
            "high": (0.58, 0.60, 0.60, 1.0), "roughness": (0.43, 0.60),
            "anisotropy": 0.16, "grain_scale": 12.0, "grain_strength": 0.145,
            "grain_distance": 0.00110,
        },
    },
    {
        "id": "07_warm_field_dust_satin",
        "description": "Warm photo-oriented field dust with clean satin aluminum hardware.",
        "soil": {
            "saturation": 1.15, "value": 0.33, "roughness": (0.93, 0.99),
            "macro_low": 0.88, "macro_factor": 0.28, "specular": 0.13,
            "normal": 0.96, "height_bump": (0.46, 0.012),
            "material_displacement": 0.016, "gn_relief": (0.042, 0.033),
            "crack_bump": (0.52, 0.0040), "crack_color": 0.70,
            "crack_region": (0.50, 0.64), "crack_profile": (0.008, 0.032),
            "micro": (170.0, 0.25, 0.0019),
        },
        "metal": {
            "label": "slightly warm satin aluminum", "low": (0.38, 0.37, 0.33, 1.0),
            "high": (0.70, 0.69, 0.64, 1.0), "roughness": (0.25, 0.38),
            "anisotropy": 0.48, "grain_scale": 58.0, "grain_strength": 0.065,
            "grain_distance": 0.00055,
        },
    },
    {
        "id": "08_balanced_candidate",
        "description": "Balanced proposal: dry tan, readable relief/cracks, brushed galvanized aluminum.",
        "soil": {
            "saturation": 0.88, "value": 0.30, "roughness": (0.94, 0.995),
            "macro_low": 0.82, "macro_factor": 0.34, "specular": 0.12,
            "normal": 1.05, "height_bump": (0.52, 0.014),
            "material_displacement": 0.019, "gn_relief": (0.052, 0.039),
            "crack_bump": (0.62, 0.0048), "crack_color": 0.82,
            "crack_region": (0.48, 0.63), "crack_profile": (0.007, 0.034),
            "micro": (185.0, 0.29, 0.0022),
        },
        "metal": {
            "label": "balanced brushed galvanized aluminum", "low": (0.32, 0.35, 0.37, 1.0),
            "high": (0.68, 0.71, 0.72, 1.0), "roughness": (0.27, 0.42),
            "anisotropy": 0.42, "grain_scale": 42.0, "grain_strength": 0.085,
            "grain_distance": 0.00070,
        },
    },
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    return parser.parse_args(argv)


def material_has(obj: bpy.types.Object, material_name: str) -> bool:
    return obj.type == "MESH" and any(
        material and material.name == material_name for material in obj.data.materials
    )


def hide_plants_and_extra_parbars() -> dict[str, object]:
    plant_meshes: set[bpy.types.Object] = set()
    for obj in bpy.context.scene.objects:
        if material_has(obj, LEAF_MATERIAL) or material_has(obj, STEM_MATERIAL):
            plant_meshes.add(obj)
        if PLANT_ROOT.fullmatch(obj.name):
            plant_meshes.update(child for child in obj.children_recursive if child.type == "MESH")
    for obj in plant_meshes:
        obj.hide_render = True
        obj.hide_viewport = True

    hidden_parbars = []
    for root_name in ("PARBAR_GenotypeA", "PARBAR_GenotypeC"):
        root = bpy.data.objects.get(root_name)
        if not root:
            continue
        for child in root.children_recursive:
            if child.type == "MESH":
                child.hide_render = True
                child.hide_viewport = True
                hidden_parbars.append(child.name)
    visible_root = bpy.data.objects.get("PARBAR_GenotypeB")
    visible = [
        child.name for child in visible_root.children_recursive
        if child.type == "MESH" and not child.hide_render
    ] if visible_root else []
    if len(visible) < 9:
        raise RuntimeError(f"expected a complete Genotype B PARBAR, found {len(visible)} visible meshes")
    return {
        "plant_mesh_count_hidden": len(plant_meshes),
        "extra_parbar_mesh_count_hidden": len(hidden_parbars),
        "visible_parbar_root": "PARBAR_GenotypeB",
        "visible_parbar_mesh_count": len(visible),
    }


def node(material: bpy.types.Material, name: str) -> bpy.types.Node:
    result = material.node_tree.nodes.get(name)
    if result is None:
        raise RuntimeError(f"material {material.name} has no node {name}")
    return result


def set_principled(principled: bpy.types.Node, name: str, value) -> None:
    if name in principled.inputs:
        principled.inputs[name].default_value = value


def set_gray_ramp(ramp: bpy.types.Node, low: float, high: float) -> None:
    ramp.color_ramp.elements[0].color = (low, low, low, 1.0)
    ramp.color_ramp.elements[-1].color = (high, high, high, 1.0)


def configure_soil(settings: dict[str, object]) -> dict[str, object]:
    material = bpy.data.materials.get(SOIL_MATERIAL)
    ground = bpy.data.objects.get(GROUND_OBJECT)
    if not material or not material.use_nodes or not ground:
        raise RuntimeError("expected displaced soil material and Ground Mesh")
    calibration = node(material, "SWEEP Soil Reference Color Calibration")
    calibration.inputs["Saturation"].default_value = settings["saturation"]
    calibration.inputs["Value"].default_value = settings["value"]
    set_gray_ramp(node(material, "SWEEP Soil Dry Roughness"), *settings["roughness"])
    macro = node(material, "SWEEP Soil Macro Color Range")
    macro.color_ramp.elements[0].color = (*([settings["macro_low"]] * 3), 1.0)
    macro.color_ramp.elements[-1].color = (1.0, 1.0, 1.0, 1.0)
    node(material, "SWEEP Soil Macro Color Variation").inputs["Factor"].default_value = settings["macro_factor"]

    principled = node(material, "SWEEP Soil Principled BSDF")
    set_principled(principled, "Specular IOR Level", settings["specular"])
    node(material, "SWEEP Soil PBR Normal").inputs["Strength"].default_value = settings["normal"]
    height_bump = node(material, "SWEEP Soil PBR Height Bump")
    height_bump.inputs["Strength"].default_value = settings["height_bump"][0]
    height_bump.inputs["Distance"].default_value = settings["height_bump"][1]
    displacement = node(material, "SWEEP Soil Material Displacement")
    displacement.inputs["Scale"].default_value = settings["material_displacement"]
    crack_bump = node(material, "SWEEP Soil Crack Bump")
    crack_bump.inputs["Strength"].default_value = settings["crack_bump"][0]
    crack_bump.inputs["Distance"].default_value = settings["crack_bump"][1]
    node(material, "SWEEP Soil Crack Color Strength").inputs[1].default_value = settings["crack_color"]
    crack_region = node(material, "SWEEP Soil Sparse Crack Regions").color_ramp.elements
    crack_region[0].position, crack_region[-1].position = settings["crack_region"]
    crack_profile = node(material, "SWEEP Soil Crack Profile").color_ramp.elements
    crack_profile[0].position, crack_profile[-1].position = settings["crack_profile"]
    micro = node(material, "SWEEP Soil Micro Grain")
    micro.inputs["Scale"].default_value = settings["micro"][0]
    micro_bump = node(material, "SWEEP Soil Micro Grain Bump")
    micro_bump.inputs["Strength"].default_value = settings["micro"][1]
    micro_bump.inputs["Distance"].default_value = settings["micro"][2]

    modifier = next(
        (mod for mod in ground.modifiers if mod.type == "NODES" and mod.node_group), None
    )
    if modifier is None:
        raise RuntimeError("Ground Mesh has no geometry-node displacement modifier")
    pbr_relief = modifier.node_group.nodes.get("SWEEP Soil PBR Relief Strength")
    macro_relief = modifier.node_group.nodes.get("SWEEP Soil Macro Relief Strength")
    if not pbr_relief or not macro_relief:
        raise RuntimeError("ground displacement group is missing named relief controls")
    pbr_relief.inputs[1].default_value = settings["gn_relief"][0]
    macro_relief.inputs[1].default_value = settings["gn_relief"][1]
    modifier.show_render = True
    if hasattr(material, "displacement_method"):
        material.displacement_method = "DISPLACEMENT"
    if hasattr(material, "max_vertex_displacement"):
        material.max_vertex_displacement = 0.08
    material.node_tree.update_tag()
    modifier.node_group.update_tag()
    ground.data.update()
    bpy.context.view_layer.update()
    return {
        "material": material.name,
        "displacement_method": getattr(material, "displacement_method", None),
        "max_vertex_displacement_m": getattr(material, "max_vertex_displacement", None),
        "shader_displacement_m": displacement.inputs["Scale"].default_value,
        "geometry_node_relief_m": [pbr_relief.inputs[1].default_value, macro_relief.inputs[1].default_value],
        "geometry_node_modifier_render_enabled": modifier.show_render,
    }


def rebuild_metal_material(settings: dict[str, object]) -> dict[str, object]:
    material = bpy.data.materials.get(METAL_MATERIAL)
    if not material:
        raise RuntimeError(f"missing {METAL_MATERIAL}")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (540, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.name = "SWEEP PARBAR Metal Principled"
    principled.location = (280, 0)
    set_principled(principled, "Metallic", 1.0)
    set_principled(principled, "Roughness", sum(settings["roughness"]) * 0.5)
    set_principled(principled, "Coat Weight", 0.0)
    set_principled(principled, "Anisotropic IOR Level", settings["anisotropy"])

    coordinates = nodes.new("ShaderNodeTexCoord")
    coordinates.location = (-760, 0)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.name = "SWEEP PARBAR Metal Grain"
    noise.location = (-520, 0)
    noise.inputs["Scale"].default_value = settings["grain_scale"]
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.62
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])

    color = nodes.new("ShaderNodeValToRGB")
    color.name = "SWEEP PARBAR Metal Color Variation"
    color.location = (-260, 100)
    color.color_ramp.elements[0].color = settings["low"]
    color.color_ramp.elements[-1].color = settings["high"]
    links.new(noise.outputs["Fac"], color.inputs["Factor"])
    links.new(color.outputs["Color"], principled.inputs["Base Color"])

    roughness = nodes.new("ShaderNodeValToRGB")
    roughness.name = "SWEEP PARBAR Metal Roughness Variation"
    roughness.location = (-250, -100)
    set_gray_ramp(roughness, *settings["roughness"])
    links.new(noise.outputs["Fac"], roughness.inputs["Factor"])
    links.new(roughness.outputs["Color"], principled.inputs["Roughness"])

    bump = nodes.new("ShaderNodeBump")
    bump.name = "SWEEP PARBAR Metal Grain Bump"
    bump.location = (20, -170)
    bump.inputs["Strength"].default_value = settings["grain_strength"]
    bump.inputs["Distance"].default_value = settings["grain_distance"]
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    material.node_tree.update_tag()
    return {
        "material": material.name,
        "finish": settings["label"],
        "metallic": 1.0,
        "roughness_range": list(settings["roughness"]),
        "anisotropy": settings["anisotropy"],
        "procedural_grain": True,
    }


def configure_sensor_polymer() -> dict[str, object]:
    material = bpy.data.materials.get(SENSOR_MATERIAL)
    if not material or not material.use_nodes:
        raise RuntimeError(f"missing {SENSOR_MATERIAL}")
    principled = next((candidate for candidate in material.node_tree.nodes if candidate.type == "BSDF_PRINCIPLED"), None)
    if not principled:
        raise RuntimeError("sensor-bar polymer material has no Principled BSDF")
    set_principled(principled, "Base Color", (0.37, 0.39, 0.37, 1.0))
    set_principled(principled, "Metallic", 0.0)
    set_principled(principled, "Roughness", 0.52)
    set_principled(principled, "Specular IOR Level", 0.32)
    material.node_tree.update_tag()
    return {
        "material": material.name,
        "classification": "matte polymer sensor housing (preserved; not falsely metallized)",
        "metallic": 0.0,
        "roughness": 0.52,
    }


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def make_camera() -> bpy.types.Object:
    name = "SWEEP Plant-Free Soil PARBAR Study Camera"
    camera = bpy.data.objects.get(name)
    if camera is None:
        camera_data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, camera_data)
        bpy.context.scene.collection.objects.link(camera)
    camera.data.sensor_fit = "VERTICAL"
    camera.data.sensor_height = 32.0
    camera.data.lens = 55.0
    camera.data.clip_start = 0.02
    camera.data.clip_end = 1000.0
    camera.data.dof.use_dof = False
    camera.location = (8.34, 4.47, 2.07)
    look_at(camera, Vector((2.57, 9.06, 1.50)))
    return camera


def configure_render(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.018
    scene.cycles.seed = 20260728
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


def displacement_audit() -> dict[str, object]:
    material = bpy.data.materials.get(SOIL_MATERIAL)
    ground = bpy.data.objects.get(GROUND_OBJECT)
    output = next(
        (candidate for candidate in material.node_tree.nodes if candidate.type == "OUTPUT_MATERIAL"), None
    )
    socket = output.inputs.get("Displacement") if output else None
    modifier = next(
        (mod for mod in ground.modifiers if mod.type == "NODES" and mod.node_group), None
    )
    return {
        "material_displacement_method": getattr(material, "displacement_method", None),
        "material_max_vertex_displacement_m": getattr(material, "max_vertex_displacement", None),
        "material_output_displacement_linked": bool(socket and socket.is_linked),
        "material_output_displacement_source": (
            socket.links[0].from_node.name if socket and socket.is_linked else None
        ),
        "ground_geometry_node_modifier": modifier.name if modifier else None,
        "ground_geometry_node_modifier_render_enabled": modifier.show_render if modifier else False,
        "ground_vertices": len(ground.data.vertices),
        "ground_polygons": len(ground.data.polygons),
        "true_displacement_has_dense_mesh_support": len(ground.data.vertices) > 1_000_000,
    }


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.output_blend = args.output_blend.resolve()
    args.output_dir = args.output_dir.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    visibility = hide_plants_and_extra_parbars()
    configure_render(args)
    sensor = configure_sensor_polymer()
    camera = make_camera()
    bpy.context.scene.camera = camera
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_blend.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for variant in VARIANTS:
        soil = configure_soil(variant["soil"])
        metal = rebuild_metal_material(variant["metal"])
        bpy.context.scene["SWEEP_active_soil_parbar_variant"] = variant["id"]
        output = args.output_dir / f"{variant['id']}.png"
        bpy.context.scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        records.append({
            "id": variant["id"],
            "description": variant["description"],
            "output": str(output),
            "soil_settings": variant["soil"],
            "soil_runtime": soil,
            "parbar_metal_settings": variant["metal"],
            "parbar_metal_runtime": metal,
        })

    bpy.context.scene["SWEEP_soil_parbar_variant_study"] = json.dumps(
        {"variant_count": len(VARIANTS), "presentation_only": True}
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    report = {
        "schema_version": 1,
        "renderer": "Blender Cycles",
        "source_blend": str(args.blend),
        "output_blend": str(args.output_blend),
        "output_directory": str(args.output_dir),
        "samples": args.samples,
        "resolution": [args.resolution_x, args.resolution_y],
        "device": bpy.context.scene.cycles.device,
        "fixed_camera": {
            "name": camera.name,
            "location": list(camera.location),
            "rotation_euler": list(camera.rotation_euler),
            "lens_mm": camera.data.lens,
            "depth_of_field": camera.data.dof.use_dof,
        },
        "visibility": visibility,
        "sensor_bar_material": sensor,
        "displacement_audit": displacement_audit(),
        "variant_count": len(records),
        "variants": records,
        "ownership": {
            "scope": "Blender presentation-only material study",
            "plants_hidden_not_deleted": True,
            "evoengine_scene_modified": False,
            "scientific_geometry_modified": False,
            "parbar_geometry_modified": False,
        },
    }
    report_path = args.output_dir / "soil_parbar_variant_study_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"SWEEP_VARIANT_STUDY_REPORT={report_path}")


if __name__ == "__main__":
    main()
