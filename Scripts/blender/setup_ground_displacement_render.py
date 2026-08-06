"""Add Cycles ground displacement to an authored LSystem sorghum Blender scene."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLEND = ROOT / "out" / "exports" / "lsystem_sorghum_paper_smoke" / "lsystem_sorghum_adult_cycles.blend"
DEFAULT_OUTPUT_BLEND = (
    ROOT
    / "out"
    / "exports"
    / "lsystem_sorghum_paper_smoke"
    / "lsystem_sorghum_adult_cycles_ground_displacement.blend"
)
DEFAULT_RENDER = (
    ROOT
    / "out"
    / "exports"
    / "lsystem_sorghum_paper_smoke"
    / "lsystem_sorghum_adult_cycles_ground_displacement.png"
)
SOIL_SCAN_ROOT = (
    ROOT
    / "Resources"
    / "DigitalAgricultureProject"
    / "Assets"
    / "ManualAssets"
    / "Soil"
    / "ScannedPBR"
    / "PolyHaven"
)
DEFAULT_SOIL_HEIGHT = SOIL_SCAN_ROOT / "brown_mud_dry" / "brown_mud_dry_displacement.exr"
SOIL_MATERIAL_NAME = "SWEEP_Ground_Soil_Displaced_Cycles"
SOIL_CONTEXT_COLLECTION = "SWEEP_RenderOnly_SoilContext"
STEM_MATERIAL_NAME = "SWEEP_LSystem_Stem_Cycles"
SOIL_BROWN_MUD_PHYSICAL_WIDTH_M = 1.3
SOIL_DIRT_PHYSICAL_WIDTH_M = 2.0
SOIL_SPECULAR_IOR_LEVEL = 0.5
SOIL_NORMAL_STRENGTH = 1.0
SOIL_HEIGHT_BUMP_STRENGTH = 0.30
SOIL_HEIGHT_BUMP_DISTANCE_M = 0.003
SOIL_CRACK_CELL_SCALE_PER_M = 5.5
SOIL_CRACK_BUMP_STRENGTH = 0.12
SOIL_CRACK_BUMP_DISTANCE_M = 0.0012
SOIL_LARGE_CLOD_DENSITY_PER_M2 = 5.0
SOIL_SMALL_AGGREGATE_DENSITY_PER_M2 = 80.0
SOIL_PEBBLE_DENSITY_PER_M2 = 10.0
SOIL_RESIDUE_DENSITY_PER_M2 = 0.5
SOIL_CONTACT_CLODS_PER_PLANT = 6
SOIL_CONTEXT_SEED = 20260709


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", type=Path, default=DEFAULT_BLEND)
    parser.add_argument("--output-blend", type=Path, default=DEFAULT_OUTPUT_BLEND)
    parser.add_argument("--render-output", type=Path, default=DEFAULT_RENDER)
    parser.add_argument("--height-texture", type=Path, default=DEFAULT_SOIL_HEIGHT)
    parser.add_argument("--samples", type=int, default=512)
    parser.add_argument("--resolution-x", type=int, default=3000)
    parser.add_argument("--resolution-y", type=int, default=2000)
    parser.add_argument("--displacement-strength", type=float, default=0.0)
    parser.add_argument("--macro-displacement-strength", type=float, default=0.0)
    parser.add_argument("--material-displacement-strength", type=float, default=0.042)
    parser.add_argument("--height-midpoint", type=float, default=0.58)
    parser.add_argument("--label", default="")
    parser.add_argument("--skip-render", action="store_true")
    return parser.parse_args(argv)


def load_image(path: Path, colorspace: str) -> bpy.types.Image:
    image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass
    return image


def texture_dir_for_blend(path: Path) -> Path:
    return path.resolve().parent / "textures"


def ensure_soil_height_texture(output_blend: Path, source: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Soil height texture not found: {source}")
    texture_dir = texture_dir_for_blend(output_blend)
    texture_dir.mkdir(parents=True, exist_ok=True)
    target = texture_dir / f"soil_height{source.suffix.lower()}"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def find_ground_object() -> bpy.types.Object:
    candidates = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.name.startswith("Ground Mesh")]
    if not candidates:
        candidates = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and "ground" in obj.name.lower()]
    if not candidates:
        raise RuntimeError("Could not find a ground mesh object")
    return max(candidates, key=lambda obj: len(obj.data.polygons))


def new_principled_material(name: str) -> tuple[bpy.types.Material, bpy.types.Node]:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (260, 0)
    material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material, bsdf


def set_input_default(node: bpy.types.Node, name: str, value) -> None:
    if name in node.inputs:
        node.inputs[name].default_value = value


def add_image_node(
    material: bpy.types.Material,
    image: bpy.types.Image,
    label: str,
    location: tuple[int, int],
    vector: bpy.types.NodeSocket | None = None,
) -> bpy.types.Node:
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.name = label
    node.label = label
    node.image = image
    node.extension = "REPEAT"
    node.interpolation = "Cubic"
    node.location = location
    if vector:
        material.node_tree.links.new(vector, node.inputs["Vector"])
    return node


def soil_object_coordinates(
    material: bpy.types.Material,
    ground: bpy.types.Object,
    scale_per_m: float,
    name: str,
) -> bpy.types.NodeSocket:
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    coordinates = nodes.new("ShaderNodeTexCoord")
    coordinates.name = f"SWEEP Soil World Coordinates {name}"
    coordinates.object = ground
    coordinates.location = (-1500, -260)

    tile_scale = nodes.new("ShaderNodeVectorMath")
    tile_scale.name = f"SWEEP Soil Physical Tile Scale {name}"
    tile_scale.operation = "SCALE"
    tile_scale.inputs["Scale"].default_value = scale_per_m
    tile_scale.location = (-1280, -260)

    warp = nodes.new("ShaderNodeTexNoise")
    warp.name = f"SWEEP Soil Anti-Tiling Warp {name}"
    warp.noise_dimensions = "3D"
    warp.inputs["Scale"].default_value = 0.22
    warp.inputs["Detail"].default_value = 3.0
    warp.inputs["Roughness"].default_value = 0.62
    warp.location = (-1280, -470)

    center_warp = nodes.new("ShaderNodeVectorMath")
    center_warp.operation = "SUBTRACT"
    center_warp.inputs[1].default_value = (0.5, 0.5, 0.5)
    center_warp.location = (-1050, -470)
    warp_scale = nodes.new("ShaderNodeVectorMath")
    warp_scale.operation = "SCALE"
    warp_scale.inputs["Scale"].default_value = 0.12
    warp_scale.location = (-830, -470)
    add_warp = nodes.new("ShaderNodeVectorMath")
    add_warp.name = f"SWEEP Soil Warped PBR Coordinates {name}"
    add_warp.operation = "ADD"
    add_warp.location = (-610, -260)

    links.new(coordinates.outputs["Object"], tile_scale.inputs[0])
    links.new(coordinates.outputs["Object"], warp.inputs["Vector"])
    links.new(warp.outputs["Color"], center_warp.inputs[0])
    links.new(center_warp.outputs["Vector"], warp_scale.inputs[0])
    links.new(tile_scale.outputs["Vector"], add_warp.inputs[0])
    links.new(warp_scale.outputs["Vector"], add_warp.inputs[1])
    return add_warp.outputs["Vector"]


def first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def rebuild_ground_material(
    ground: bpy.types.Object,
    texture_dir: Path,
    height_path: Path,
    material_displacement_strength: float,
) -> dict[str, str | None]:
    material, bsdf = new_principled_material(SOIL_MATERIAL_NAME)
    bsdf.name = "SWEEP Soil Principled BSDF"
    bsdf.label = "CC0 scanned dry sandy-loam field soil"
    if hasattr(material, "displacement_method"):
        material.displacement_method = "DISPLACEMENT"
    if hasattr(material, "max_vertex_displacement"):
        material.max_vertex_displacement = max(0.08, material_displacement_strength)
    set_input_default(bsdf, "Metallic", 0.0)
    set_input_default(bsdf, "Roughness", 0.82)
    set_input_default(bsdf, "Specular IOR Level", SOIL_SPECULAR_IOR_LEVEL)
    set_input_default(bsdf, "Coat Weight", 0.0)

    brown_dir = SOIL_SCAN_ROOT / "brown_mud_dry"
    dirt_dir = SOIL_SCAN_ROOT / "dirt"
    paths: dict[str, Path | None] = {
        "brown_diffuse": brown_dir / "brown_mud_dry_diffuse.jpg",
        "brown_normal": brown_dir / "brown_mud_dry_nor_gl.png",
        "brown_roughness": brown_dir / "brown_mud_dry_rough.exr",
        "brown_displacement": height_path,
        "brown_bump": brown_dir / "brown_mud_dry_bump.exr",
        "dirt_diffuse": dirt_dir / "dirt_diffuse.jpg",
        "dirt_normal": dirt_dir / "dirt_nor_gl.png",
        "dirt_roughness": dirt_dir / "dirt_rough.exr",
        "dirt_displacement": dirt_dir / "dirt_displacement.exr",
    }
    missing = [str(path) for path in paths.values() if path is not None and not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing scanned soil maps: {missing}")
    images: dict[str, bpy.types.Image] = {
        key: load_image(path, "sRGB" if key.endswith("diffuse") else "Non-Color")
        for key, path in paths.items()
        if path is not None
    }
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    brown_coordinates = soil_object_coordinates(
        material, ground, 1.0 / SOIL_BROWN_MUD_PHYSICAL_WIDTH_M, "BrownMud"
    )
    dirt_coordinates = soil_object_coordinates(material, ground, 1.0 / SOIL_DIRT_PHYSICAL_WIDTH_M, "Dirt")
    object_coordinates = nodes["SWEEP Soil World Coordinates BrownMud"].outputs["Object"]

    channel_nodes: dict[str, tuple[bpy.types.Node, bpy.types.Node]] = {}
    y_positions = {"diffuse": 500, "roughness": 220, "normal": -60, "displacement": -340}
    for channel, y in y_positions.items():
        brown = add_image_node(
            material, images[f"brown_{channel}"], f"SWEEP Brown Mud {channel}", (-1120, y), brown_coordinates
        )
        dirt = add_image_node(
            material, images[f"dirt_{channel}"], f"SWEEP Dirt {channel}", (-1120, y - 130), dirt_coordinates
        )
        channel_nodes[channel] = (brown, dirt)
    brown_bump = add_image_node(
        material, images["brown_bump"], "SWEEP Brown Mud bump", (-1120, -620), brown_coordinates
    )

    compact_noise = nodes.new("ShaderNodeTexNoise")
    compact_noise.name = "SWEEP Compacted Furrow Patch Noise"
    compact_noise.inputs["Scale"].default_value = 0.33
    compact_noise.inputs["Detail"].default_value = 3.0
    compact_noise.inputs["Roughness"].default_value = 0.62
    compact_noise.location = (-1080, 760)
    links.new(object_coordinates, compact_noise.inputs["Vector"])
    compact_range = nodes.new("ShaderNodeMapRange")
    compact_range.name = "SWEEP Dirt Mix Fraction"
    compact_range.inputs["From Min"].default_value = 0.0
    compact_range.inputs["From Max"].default_value = 1.0
    compact_range.inputs["To Min"].default_value = 0.08
    compact_range.inputs["To Max"].default_value = 0.28
    compact_range.clamp = True
    compact_range.location = (-820, 760)
    links.new(compact_noise.outputs["Factor"], compact_range.inputs["Value"])

    mixed_outputs: dict[str, bpy.types.NodeSocket] = {}
    for index, channel in enumerate(y_positions):
        mix = nodes.new("ShaderNodeMixRGB")
        mix.name = f"SWEEP Hybrid {channel.title()}"
        mix.location = (-570, 520 - index * 240)
        links.new(compact_range.outputs["Result"], mix.inputs["Factor"])
        links.new(channel_nodes[channel][0].outputs["Color"], mix.inputs["Color1"])
        links.new(channel_nodes[channel][1].outputs["Color"], mix.inputs["Color2"])
        mixed_outputs[channel] = mix.outputs["Color"]
    # The compacted Dirt scan contributes albedo and roughness only.  Mixing its
    # unrelated height/normal field would soften the Brown Mud scan's correlated
    # aggregate relief and create a non-physical hybrid micro-surface.
    mixed_outputs["normal"] = channel_nodes["normal"][0].outputs["Color"]
    mixed_outputs["displacement"] = channel_nodes["displacement"][0].outputs["Color"]

    color_calibration = nodes.new("ShaderNodeHueSaturation")
    color_calibration.name = "SWEEP Soil Reference Color Calibration"
    color_calibration.label = "preserve scan contrast; reduce brightness before warm tint"
    color_calibration.inputs["Saturation"].default_value = 1.05
    color_calibration.inputs["Value"].default_value = 0.64
    color_calibration.location = (-280, 520)
    links.new(mixed_outputs["diffuse"], color_calibration.inputs["Color"])
    warm_tint = nodes.new("ShaderNodeMixRGB")
    warm_tint.name = "SWEEP Arizona Sandy-Loam Warm Tint"
    warm_tint.blend_type = "MULTIPLY"
    warm_tint.inputs["Factor"].default_value = 0.60
    warm_tint.inputs["Color2"].default_value = (0.55, 0.23, 0.06, 1.0)
    warm_tint.location = (-40, 520)
    links.new(color_calibration.outputs["Color"], warm_tint.inputs["Color1"])

    cracks = nodes.new("ShaderNodeTexVoronoi")
    cracks.name = "SWEEP Soil Sparse Fine Crack Cells"
    cracks.voronoi_dimensions = "2D"
    cracks.feature = "DISTANCE_TO_EDGE"
    cracks.inputs["Scale"].default_value = SOIL_CRACK_CELL_SCALE_PER_M
    cracks.inputs["Randomness"].default_value = 0.88
    cracks.location = (-570, 800)
    links.new(object_coordinates, cracks.inputs["Vector"])
    crack_profile = nodes.new("ShaderNodeValToRGB")
    crack_profile.name = "SWEEP Soil Fine Crack Profile"
    crack_profile.color_ramp.elements[0].position = 0.007
    crack_profile.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    crack_profile.color_ramp.elements[1].position = 0.020
    crack_profile.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    crack_profile.location = (-330, 800)
    links.new(cracks.outputs["Distance"], crack_profile.inputs["Factor"])
    crack_regions = nodes.new("ShaderNodeTexNoise")
    crack_regions.name = "SWEEP Soil Sparse Crack Regions"
    crack_regions.inputs["Scale"].default_value = 0.22
    crack_regions.inputs["Detail"].default_value = 2.0
    crack_regions.location = (-570, 980)
    links.new(object_coordinates, crack_regions.inputs["Vector"])
    crack_region_ramp = nodes.new("ShaderNodeValToRGB")
    crack_region_ramp.color_ramp.elements[0].position = 0.63
    crack_region_ramp.color_ramp.elements[1].position = 0.76
    crack_region_ramp.location = (-330, 980)
    links.new(crack_regions.outputs["Factor"], crack_region_ramp.inputs["Factor"])
    crack_mask = nodes.new("ShaderNodeMath")
    crack_mask.name = "SWEEP Soil Sparse Crack Mask"
    crack_mask.operation = "MULTIPLY"
    crack_mask.location = (-80, 850)
    links.new(crack_profile.outputs["Color"], crack_mask.inputs[0])
    links.new(crack_region_ramp.outputs["Color"], crack_mask.inputs[1])
    crack_strength = nodes.new("ShaderNodeMath")
    crack_strength.name = "SWEEP Soil Crack Color Strength"
    crack_strength.operation = "MULTIPLY"
    crack_strength.inputs[1].default_value = 0.24
    crack_strength.location = (140, 820)
    links.new(crack_mask.outputs["Value"], crack_strength.inputs[0])
    crack_color = nodes.new("ShaderNodeMixRGB")
    crack_color.name = "SWEEP Soil Sparse Crack Color"
    crack_color.inputs["Color2"].default_value = (0.025, 0.011, 0.004, 1.0)
    crack_color.location = (190, 520)
    links.new(crack_strength.outputs["Value"], crack_color.inputs["Factor"])
    links.new(warm_tint.outputs["Color"], crack_color.inputs["Color1"])
    links.new(crack_color.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(mixed_outputs["roughness"], bsdf.inputs["Roughness"])

    normal = nodes.new("ShaderNodeNormalMap")
    normal.name = "SWEEP Soil Scan Normal"
    normal.inputs["Strength"].default_value = SOIL_NORMAL_STRENGTH
    normal.location = (-260, -20)
    links.new(mixed_outputs["normal"], normal.inputs["Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.name = "SWEEP Soil Fine Aggregate Bump"
    bump.inputs["Strength"].default_value = SOIL_HEIGHT_BUMP_STRENGTH
    bump.inputs["Distance"].default_value = SOIL_HEIGHT_BUMP_DISTANCE_M
    bump.location = (-30, -100)
    links.new(brown_bump.outputs["Color"], bump.inputs["Height"])
    links.new(normal.outputs["Normal"], bump.inputs["Normal"])
    crack_bump = nodes.new("ShaderNodeBump")
    crack_bump.name = "SWEEP Soil Crack Bump"
    crack_bump.invert = True
    crack_bump.inputs["Strength"].default_value = SOIL_CRACK_BUMP_STRENGTH
    crack_bump.inputs["Distance"].default_value = SOIL_CRACK_BUMP_DISTANCE_M
    crack_bump.location = (200, -80)
    links.new(crack_mask.outputs["Value"], crack_bump.inputs["Height"])
    links.new(bump.outputs["Normal"], crack_bump.inputs["Normal"])
    links.new(crack_bump.outputs["Normal"], bsdf.inputs["Normal"])

    displacement = nodes.new("ShaderNodeDisplacement")
    displacement.name = "SWEEP Soil Material Displacement"
    displacement.inputs["Scale"].default_value = material_displacement_strength
    displacement.inputs["Midlevel"].default_value = 0.58
    displacement.location = (450, -380)
    links.new(mixed_outputs["displacement"], displacement.inputs["Height"])
    output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
    links.new(displacement.outputs["Displacement"], output.inputs["Displacement"])

    ground.data.materials.clear()
    ground.data.materials.append(material)
    return {key: str(value.resolve()) if value else None for key, value in paths.items()}


def add_socket(group: bpy.types.NodeTree, name: str, in_out: str, socket_type: str) -> None:
    group.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)


def build_ground_displacement_group(
    height_image: bpy.types.Image,
    strength: float,
    macro_strength: float,
    midpoint: float,
    row_centers_y: list[float],
) -> bpy.types.NodeTree:
    name = "SWEEP_Ground_Height_Displacement_GN"
    old = bpy.data.node_groups.get(name)
    if old:
        bpy.data.node_groups.remove(old)
    group = bpy.data.node_groups.new(name, "GeometryNodeTree")
    add_socket(group, "Geometry", "INPUT", "NodeSocketGeometry")
    add_socket(group, "Geometry", "OUTPUT", "NodeSocketGeometry")

    nodes = group.nodes
    links = group.links
    group_input = nodes.new("NodeGroupInput")
    group_input.location = (-920, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.location = (680, 0)

    position = nodes.new("GeometryNodeInputPosition")
    position.location = (-1180, -230)
    tile_scale = nodes.new("ShaderNodeVectorMath")
    tile_scale.name = "SWEEP Soil PBR Tile Scale"
    tile_scale.operation = "SCALE"
    tile_scale.inputs["Scale"].default_value = 1.0 / SOIL_BROWN_MUD_PHYSICAL_WIDTH_M
    tile_scale.location = (-980, -230)

    warp = nodes.new("ShaderNodeTexNoise")
    warp.name = "SWEEP Soil Anti-Tiling Warp"
    warp.inputs["Scale"].default_value = 0.22
    warp.inputs["Detail"].default_value = 3.0
    warp.inputs["Roughness"].default_value = 0.62
    warp.location = (-980, -450)
    center_warp = nodes.new("ShaderNodeVectorMath")
    center_warp.operation = "SUBTRACT"
    center_warp.inputs[1].default_value = (0.5, 0.5, 0.5)
    center_warp.location = (-760, -450)
    warp_scale = nodes.new("ShaderNodeVectorMath")
    warp_scale.operation = "SCALE"
    warp_scale.inputs["Scale"].default_value = 0.12
    warp_scale.location = (-550, -450)
    add_warp = nodes.new("ShaderNodeVectorMath")
    add_warp.name = "SWEEP Soil Warped PBR Coordinates"
    add_warp.operation = "ADD"
    add_warp.location = (-340, -250)

    image = nodes.new("GeometryNodeImageTexture")
    image.name = "SWEEP Soil Repeating Height"
    image.inputs["Image"].default_value = height_image
    image.extension = "REPEAT"
    image.interpolation = "Cubic"
    image.location = (-100, -180)

    separate = nodes.new("FunctionNodeSeparateColor")
    separate.mode = "RGB"
    separate.location = (120, -180)

    subtract = nodes.new("ShaderNodeMath")
    subtract.operation = "SUBTRACT"
    subtract.inputs[1].default_value = midpoint
    subtract.location = (330, -170)

    scale = nodes.new("ShaderNodeMath")
    scale.name = "SWEEP Soil PBR Relief Strength"
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = strength
    scale.location = (540, -170)

    macro = nodes.new("ShaderNodeTexNoise")
    macro.name = "SWEEP Soil Macro Undulation"
    macro.inputs["Scale"].default_value = 0.22
    macro.inputs["Detail"].default_value = 3.0
    macro.inputs["Roughness"].default_value = 0.65
    macro.location = (110, -450)
    macro_center = nodes.new("ShaderNodeMath")
    macro_center.operation = "SUBTRACT"
    macro_center.inputs[1].default_value = 0.5
    macro_center.location = (330, -450)
    macro_scale = nodes.new("ShaderNodeMath")
    macro_scale.name = "SWEEP Soil Macro Relief Strength"
    macro_scale.operation = "MULTIPLY"
    macro_scale.inputs[1].default_value = macro_strength
    macro_scale.location = (540, -450)
    add_relief = nodes.new("ShaderNodeMath")
    add_relief.name = "SWEEP Soil Combined Scan And Macro Relief"
    add_relief.operation = "ADD"
    add_relief.location = (750, -260)

    separate_position = nodes.new("ShaderNodeSeparateXYZ")
    separate_position.location = (-80, -700)
    links.new(position.outputs["Position"], separate_position.inputs["Vector"])
    ridge_sum = None
    for index, row_center in enumerate(row_centers_y):
        distance = nodes.new("ShaderNodeMath")
        distance.operation = "SUBTRACT"
        distance.inputs[1].default_value = row_center
        distance.location = (120, -690 - index * 105)
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        absolute.location = (310, -690 - index * 105)
        profile = nodes.new("ShaderNodeMapRange")
        profile.name = f"SWEEP Soil Row {index + 1} Furrow Ridge Profile"
        profile.interpolation_type = "SMOOTHERSTEP"
        profile.clamp = True
        profile.inputs["From Min"].default_value = 0.0
        profile.inputs["From Max"].default_value = 0.55
        profile.inputs["To Min"].default_value = 1.0
        profile.inputs["To Max"].default_value = 0.0
        profile.location = (500, -690 - index * 105)
        links.new(separate_position.outputs["Y"], distance.inputs[0])
        links.new(distance.outputs["Value"], absolute.inputs[0])
        links.new(absolute.outputs["Value"], profile.inputs["Value"])
        if ridge_sum is None:
            ridge_sum = profile.outputs["Result"]
        else:
            add_row = nodes.new("ShaderNodeMath")
            add_row.operation = "ADD"
            add_row.location = (710, -720 - index * 105)
            links.new(ridge_sum, add_row.inputs[0])
            links.new(profile.outputs["Result"], add_row.inputs[1])
            ridge_sum = add_row.outputs["Value"]
    ridge_scale = nodes.new("ShaderNodeMath")
    ridge_scale.name = "SWEEP Soil Furrow Ridge Height"
    ridge_scale.operation = "MULTIPLY"
    ridge_scale.inputs[1].default_value = 0.014
    ridge_scale.location = (920, -720)
    if ridge_sum is not None:
        links.new(ridge_sum, ridge_scale.inputs[0])
    combined_with_ridges = nodes.new("ShaderNodeMath")
    combined_with_ridges.name = "SWEEP Soil Combined Relief"
    combined_with_ridges.operation = "ADD"
    combined_with_ridges.location = (960, -260)

    normal = nodes.new("GeometryNodeInputNormal")
    normal.location = (750, -500)

    vector_scale = nodes.new("ShaderNodeVectorMath")
    vector_scale.operation = "SCALE"
    vector_scale.location = (1160, -300)

    set_position = nodes.new("GeometryNodeSetPosition")
    set_position.location = (1370, 0)
    group_output.location = (1590, 0)

    links.new(group_input.outputs["Geometry"], set_position.inputs["Geometry"])
    links.new(position.outputs["Position"], tile_scale.inputs[0])
    links.new(position.outputs["Position"], warp.inputs["Vector"])
    links.new(warp.outputs["Color"], center_warp.inputs[0])
    links.new(center_warp.outputs["Vector"], warp_scale.inputs[0])
    links.new(tile_scale.outputs["Vector"], add_warp.inputs[0])
    links.new(warp_scale.outputs["Vector"], add_warp.inputs[1])
    links.new(add_warp.outputs["Vector"], image.inputs["Vector"])
    links.new(image.outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Red"], subtract.inputs[0])
    links.new(subtract.outputs["Value"], scale.inputs[0])
    links.new(position.outputs["Position"], macro.inputs["Vector"])
    links.new(macro.outputs["Factor"], macro_center.inputs[0])
    links.new(macro_center.outputs["Value"], macro_scale.inputs[0])
    links.new(scale.outputs["Value"], add_relief.inputs[0])
    links.new(macro_scale.outputs["Value"], add_relief.inputs[1])
    links.new(add_relief.outputs["Value"], combined_with_ridges.inputs[0])
    links.new(ridge_scale.outputs["Value"], combined_with_ridges.inputs[1])
    links.new(normal.outputs["Normal"], vector_scale.inputs["Vector"])
    links.new(combined_with_ridges.outputs["Value"], vector_scale.inputs["Scale"])
    links.new(vector_scale.outputs["Vector"], set_position.inputs["Offset"])
    links.new(set_position.outputs["Geometry"], group_output.inputs["Geometry"])
    return group


def apply_ground_displacement_modifier(
    ground: bpy.types.Object,
    height_path: Path,
    strength: float,
    macro_strength: float,
    midpoint: float,
    row_centers_y: list[float],
) -> None:
    height_image = load_image(height_path, "Non-Color")
    node_group = build_ground_displacement_group(
        height_image, strength, macro_strength, midpoint, row_centers_y
    )
    for modifier in list(ground.modifiers):
        if modifier.name == "SWEEP Ground Height Displacement":
            ground.modifiers.remove(modifier)
    modifier = ground.modifiers.new("SWEEP Ground Height Displacement", "NODES")
    modifier.node_group = node_group
    modifier.show_render = True
    modifier.show_viewport = True


def render_only_collection() -> bpy.types.Collection:
    old = bpy.data.collections.get(SOIL_CONTEXT_COLLECTION)
    if old:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new(SOIL_CONTEXT_COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    return collection


def stem_base_records() -> list[dict[str, object]]:
    stems = sorted(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
            and any(material and material.name == STEM_MATERIAL_NAME for material in obj.data.materials)
        ),
        key=lambda obj: obj.name,
    )
    records = []
    for obj in stems:
        points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        minimum_z = min(point.z for point in points)
        base_points = [point for point in points if point.z <= minimum_z + 0.018]
        center = Vector(
            (
                sum(point.x for point in base_points) / len(base_points),
                sum(point.y for point in base_points) / len(base_points),
                minimum_z,
            )
        )
        spread = max(math.hypot(point.x - center.x, point.y - center.y) for point in base_points)
        records.append({"stem": obj.name, "center": center, "spread": spread})
    return records


def inferred_row_centers_y(bases: list[dict[str, object]]) -> list[float]:
    """Recover the six authored row centerlines without changing plant ownership."""
    ordered = sorted(float(record["center"].y) for record in bases)
    groups: list[list[float]] = []
    for value in ordered:
        if not groups or value - groups[-1][-1] > 0.35:
            groups.append([value])
        else:
            groups[-1].append(value)
    if len(groups) != 6 or any(len(group) != 10 for group in groups):
        raise RuntimeError(f"expected six ten-plant Blender rows, got {[len(group) for group in groups]}")
    return [sum(group) / len(group) for group in groups]


def soil_surface_sampler(ground: bpy.types.Object):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    tree = BVHTree.FromObject(ground, depsgraph)
    inverse = ground.matrix_world.inverted()
    direction = (inverse.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()

    def sample(x: float, y: float) -> tuple[Vector, Vector]:
        origin = inverse @ Vector((x, y, 2.0))
        location, normal, _, _ = tree.ray_cast(origin, direction)
        if location is None or normal is None:
            raise RuntimeError(f"ground ray missed at ({x:.3f}, {y:.3f})")
        world_location = ground.matrix_world @ location
        world_normal = (ground.matrix_world.to_3x3() @ normal).normalized()
        return world_location, world_normal

    return sample


def create_contact_mounds(
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    bases: list[dict[str, object]],
    surface,
) -> tuple[bpy.types.Object, list[float]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    outer_radii = []
    segments = 28
    ring_factors = (0.22, 0.48, 0.75, 1.0)
    ring_lifts = (0.018, 0.014, 0.006, -0.004)
    for record in bases:
        center = record["center"]
        outer_radius = min(0.18, max(0.10, float(record["spread"]) + 0.075))
        outer_radii.append(outer_radius)
        seed = int(hashlib.sha256(str(record["stem"]).encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        center_surface, _ = surface(center.x, center.y)
        center_index = len(vertices)
        vertices.append((center.x, center.y, max(center_surface.z + 0.004, center.z + 0.002)))
        ring_indices = []
        phase = rng.uniform(0.0, math.tau)
        for ring_index, (factor, lift) in enumerate(zip(ring_factors, ring_lifts)):
            indices = []
            for segment in range(segments):
                angle = phase + math.tau * segment / segments
                irregularity = 1.0 + rng.uniform(-0.09, 0.09) + 0.035 * math.sin(3.0 * angle + phase)
                radius = outer_radius * factor * irregularity
                x = center.x + radius * math.cos(angle)
                y = center.y + radius * math.sin(angle)
                ground_point, _ = surface(x, y)
                z = ground_point.z + lift + rng.uniform(-0.0025, 0.0025)
                if ring_index == 0:
                    z = max(z, center.z + 0.004)
                indices.append(len(vertices))
                vertices.append((x, y, z))
            ring_indices.append(indices)
        for segment in range(segments):
            faces.append((center_index, ring_indices[0][segment], ring_indices[0][(segment + 1) % segments]))
        for inner, outer in zip(ring_indices, ring_indices[1:]):
            for segment in range(segments):
                faces.append(
                    (
                        inner[segment],
                        outer[segment],
                        outer[(segment + 1) % segments],
                        inner[(segment + 1) % segments],
                    )
                )

    mesh = bpy.data.meshes.new("SWEEP Soil Contact Mounds Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new("SWEEP Soil Contact Mounds", mesh)
    obj["sweep_ownership"] = "blender_presentation_only"
    obj["scientific_geometry"] = False
    obj["plant_contact_count"] = len(bases)
    collection.objects.link(obj)
    return obj, outer_radii


def soil_context_bounds(bases: list[dict[str, object]]) -> tuple[float, float, float, float]:
    minimum_x = min(record["center"].x for record in bases) - 1.5
    maximum_x = max(record["center"].x for record in bases) + 1.5
    minimum_y = min(record["center"].y for record in bases) - 1.5
    maximum_y = max(record["center"].y for record in bases) + 1.5
    return minimum_x, maximum_x, minimum_y, maximum_y


def soil_prototype_collection() -> bpy.types.Collection:
    name = "SWEEP_RenderOnly_SoilPrototypes"
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    collection.hide_render = True
    return collection


def add_instance_modifier(
    points: bpy.types.Object,
    material: bpy.types.Material,
    name: str,
    radius_range_m: tuple[float, float],
    vertical_scale_range: tuple[float, float],
    seed: int,
) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    for vertex in bm.verts:
        vertex.co *= 1.0 + 0.12 * math.sin(3.7 * vertex.co.x + 5.1 * vertex.co.y + seed)
    mesh = bpy.data.meshes.new(f"{name} Prototype Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    prototype = bpy.data.objects.new(f"{name} Prototype", mesh)
    prototype["sweep_ownership"] = "blender_presentation_only_prototype"
    prototype["scientific_geometry"] = False
    soil_prototype_collection().objects.link(prototype)

    group = bpy.data.node_groups.new(f"{name} Instance Geometry", "GeometryNodeTree")
    add_socket(group, "Geometry", "INPUT", "NodeSocketGeometry")
    add_socket(group, "Geometry", "OUTPUT", "NodeSocketGeometry")
    nodes = group.nodes
    links = group.links
    group_input = nodes.new("NodeGroupInput")
    group_output = nodes.new("NodeGroupOutput")
    object_info = nodes.new("GeometryNodeObjectInfo")
    object_info.transform_space = "ORIGINAL"
    object_info.inputs["Object"].default_value = prototype
    instance = nodes.new("GeometryNodeInstanceOnPoints")
    scale = nodes.new("FunctionNodeRandomValue")
    scale.data_type = "FLOAT_VECTOR"
    minimum_radius, maximum_radius = radius_range_m
    scale.inputs["Min"].default_value = (
        minimum_radius * 0.82,
        minimum_radius * 0.72,
        minimum_radius * vertical_scale_range[0],
    )
    scale.inputs["Max"].default_value = (
        maximum_radius * 1.42,
        maximum_radius * 1.30,
        maximum_radius * vertical_scale_range[1],
    )
    scale.inputs["Seed"].default_value = seed
    rotation = nodes.new("FunctionNodeRandomValue")
    rotation.data_type = "FLOAT_VECTOR"
    rotation.inputs["Min"].default_value = (-0.14, -0.14, 0.0)
    rotation.inputs["Max"].default_value = (0.14, 0.14, math.tau)
    rotation.inputs["Seed"].default_value = seed + 1
    links.new(group_input.outputs["Geometry"], instance.inputs["Points"])
    links.new(object_info.outputs["Geometry"], instance.inputs["Instance"])
    links.new(scale.outputs["Value"], instance.inputs["Scale"])
    links.new(rotation.outputs["Value"], instance.inputs["Rotation"])
    links.new(instance.outputs["Instances"], group_output.inputs["Geometry"])
    modifier = points.modifiers.new(f"{name} Instances", "NODES")
    modifier.node_group = group
    return prototype


def create_aggregate_mesh(
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    bases: list[dict[str, object]],
    surface,
    *,
    name: str,
    density_per_m2: float,
    radius_range_m: tuple[float, float],
    vertical_scale_range: tuple[float, float],
    seed_offset: int,
    contact_radii: list[float] | None = None,
) -> tuple[bpy.types.Object, int, int]:
    rng = random.Random(SOIL_CONTEXT_SEED + seed_offset)
    minimum_x, maximum_x, minimum_y, maximum_y = soil_context_bounds(bases)
    global_count = round((maximum_x - minimum_x) * (maximum_y - minimum_y) * density_per_m2)
    positions = [
        (rng.uniform(minimum_x, maximum_x), rng.uniform(minimum_y, maximum_y))
        for _ in range(global_count)
    ]
    if contact_radii:
        for record, radius in zip(bases, contact_radii):
            center = record["center"]
            for _ in range(SOIL_CONTACT_CLODS_PER_PLANT):
                angle = rng.uniform(0.0, math.tau)
                distance = radius * rng.uniform(0.42, 1.18)
                positions.append((center.x + distance * math.cos(angle), center.y + distance * math.sin(angle)))

    vertices: list[tuple[float, float, float]] = []
    for x, y in positions:
        location, normal = surface(x, y)
        vertices.append(tuple(location + normal * (0.25 * radius_range_m[0])))
    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, [], [])
    obj = bpy.data.objects.new(name, mesh)
    obj["sweep_ownership"] = "blender_presentation_only"
    obj["scientific_geometry"] = False
    obj["element_count"] = len(positions)
    obj["density_per_m2"] = density_per_m2
    obj["diameter_range_m"] = [2.0 * radius_range_m[0], 2.0 * radius_range_m[1]]
    collection.objects.link(obj)
    prototype = add_instance_modifier(
        obj,
        material,
        name,
        radius_range_m,
        vertical_scale_range,
        SOIL_CONTEXT_SEED + seed_offset,
    )
    obj["prototype_object"] = prototype.name
    return obj, global_count, len(positions) - global_count


def create_pebble_material() -> bpy.types.Material:
    material, bsdf = new_principled_material("SWEEP Dry Field Pebbles")
    set_input_default(bsdf, "Roughness", 0.74)
    set_input_default(bsdf, "Specular IOR Level", 0.42)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.07, 0.045, 0.027, 1.0)
    ramp.color_ramp.elements[1].color = (0.34, 0.24, 0.15, 1.0)
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Factor"], ramp.inputs["Factor"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def create_residue_material() -> bpy.types.Material:
    material, bsdf = new_principled_material("SWEEP Dry Crop Residue")
    set_input_default(bsdf, "Base Color", (0.31, 0.16, 0.045, 1.0))
    set_input_default(bsdf, "Roughness", 0.82)
    set_input_default(bsdf, "Specular IOR Level", 0.38)
    return material


def create_crop_residue(
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    bases: list[dict[str, object]],
    surface,
) -> tuple[bpy.types.Object, int]:
    rng = random.Random(SOIL_CONTEXT_SEED + 41)
    minimum_x, maximum_x, minimum_y, maximum_y = soil_context_bounds(bases)
    count = round((maximum_x - minimum_x) * (maximum_y - minimum_y) * SOIL_RESIDUE_DENSITY_PER_M2)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    segments = 4
    for _ in range(count):
        center_x = rng.uniform(minimum_x, maximum_x)
        center_y = rng.uniform(minimum_y, maximum_y)
        length = rng.uniform(0.035, 0.18)
        width = rng.uniform(0.0025, 0.008)
        angle = rng.uniform(0.0, math.tau)
        direction = Vector((math.cos(angle), math.sin(angle)))
        lateral = Vector((-direction.y, direction.x))
        strip: list[tuple[int, int]] = []
        phase = rng.uniform(0.0, math.tau)
        for index in range(segments + 1):
            along = length * (index / segments - 0.5)
            curve = 0.08 * length * math.sin(math.pi * index / segments + phase)
            x = center_x + direction.x * along + lateral.x * curve
            y = center_y + direction.y * along + lateral.y * curve
            point, _ = surface(x, y)
            z = point.z + 0.003 + 0.003 * math.sin(math.pi * index / segments)
            left = (x + lateral.x * width * 0.5, y + lateral.y * width * 0.5, z)
            right = (x - lateral.x * width * 0.5, y - lateral.y * width * 0.5, z)
            strip.append((len(vertices), len(vertices) + 1))
            vertices.extend((left, right))
        for first, second in zip(strip, strip[1:]):
            faces.append((first[0], second[0], second[1], first[1]))
    mesh = bpy.data.meshes.new("SWEEP Dry Crop Residue Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new("SWEEP Dry Crop Residue", mesh)
    obj["sweep_ownership"] = "blender_presentation_only"
    obj["scientific_geometry"] = False
    obj["fragment_count"] = count
    collection.objects.link(obj)
    solidify = obj.modifiers.new("SWEEP Residue Thickness", "SOLIDIFY")
    solidify.thickness = 0.0007
    return obj, count


def create_furrow_ridges(
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    bases: list[dict[str, object]],
    surface,
) -> bpy.types.Object:
    """Add shallow row-aligned bed geometry without deforming scientific ground."""
    minimum_x, maximum_x, _, _ = soil_context_bounds(bases)
    row_centers = inferred_row_centers_y(bases)
    along_segments = 96
    across_segments = 8
    half_width = 0.55
    height = 0.014
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for row_index, row_y in enumerate(row_centers):
        grid: list[list[int]] = []
        for along in range(along_segments + 1):
            fraction = along / along_segments
            x = minimum_x + (maximum_x - minimum_x) * fraction
            longitudinal = 0.82 + 0.18 * math.sin(7.0 * fraction + 1.7 * row_index)
            cross_indices = []
            for across in range(across_segments + 1):
                lateral = half_width * (2.0 * across / across_segments - 1.0)
                profile = math.cos(0.5 * math.pi * lateral / half_width) ** 2
                y = row_y + lateral
                point, _ = surface(x, y)
                z = point.z + 0.001 + height * longitudinal * profile
                cross_indices.append(len(vertices))
                vertices.append((x, y, z))
            grid.append(cross_indices)
        for along in range(along_segments):
            for across in range(across_segments):
                faces.append(
                    (
                        grid[along][across],
                        grid[along + 1][across],
                        grid[along + 1][across + 1],
                        grid[along][across + 1],
                    )
                )
    mesh = bpy.data.meshes.new("SWEEP Shallow Row Furrows Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new("SWEEP Shallow Row Furrows", mesh)
    obj["sweep_ownership"] = "blender_presentation_only"
    obj["scientific_geometry"] = False
    obj["row_count"] = len(row_centers)
    obj["ridge_height_m"] = height
    obj["ridge_half_width_m"] = half_width
    collection.objects.link(obj)
    return obj


def create_soil_context(
    ground: bpy.types.Object,
    material: bpy.types.Material,
    bases: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    bases = bases or stem_base_records()
    if len(bases) != 60:
        raise RuntimeError(f"expected 60 stem bases, got {len(bases)}")
    collection = render_only_collection()
    surface = soil_surface_sampler(ground)
    furrows = create_furrow_ridges(collection, material, bases, surface)
    mounds, outer_radii = create_contact_mounds(collection, material, bases, surface)
    large_clods, large_global_count, contact_count = create_aggregate_mesh(
        collection,
        material,
        bases,
        surface,
        name="SWEEP Soil Large Clods",
        density_per_m2=SOIL_LARGE_CLOD_DENSITY_PER_M2,
        radius_range_m=(0.0075, 0.032),
        vertical_scale_range=(0.30, 0.62),
        seed_offset=11,
        contact_radii=outer_radii,
    )
    small_aggregate, small_count, _ = create_aggregate_mesh(
        collection,
        material,
        bases,
        surface,
        name="SWEEP Soil Small Aggregate",
        density_per_m2=SOIL_SMALL_AGGREGATE_DENSITY_PER_M2,
        radius_range_m=(0.002, 0.009),
        vertical_scale_range=(0.36, 0.78),
        seed_offset=23,
    )
    pebble_material = create_pebble_material()
    pebbles, pebble_count, _ = create_aggregate_mesh(
        collection,
        pebble_material,
        bases,
        surface,
        name="SWEEP Dry Field Pebbles",
        density_per_m2=SOIL_PEBBLE_DENSITY_PER_M2,
        radius_range_m=(0.0025, 0.012),
        vertical_scale_range=(0.24, 0.58),
        seed_offset=37,
    )
    residue, residue_count = create_crop_residue(
        collection, create_residue_material(), bases, surface
    )
    row_centers = inferred_row_centers_y(bases)
    return {
        "ownership": "blender_presentation_only",
        "collection": collection.name,
        "object_count": len(collection.objects),
        "plant_base_count": len(bases),
        "furrow_object": furrows.name,
        "mound_object": mounds.name,
        "mound_vertices": len(mounds.data.vertices),
        "mound_polygons": len(mounds.data.polygons),
        "mound_radius_range_m": [min(outer_radii), max(outer_radii)],
        "minimum_culm_overlap_m": 0.002,
        "clod_object": large_clods.name,
        "clod_count": large_global_count + contact_count,
        "global_clod_count": large_global_count,
        "contact_clod_count": contact_count,
        "clod_diameter_range_m": [0.015, 0.064],
        "small_aggregate_object": small_aggregate.name,
        "small_aggregate_count": small_count,
        "small_aggregate_diameter_range_m": [0.004, 0.018],
        "pebble_object": pebbles.name,
        "pebble_count": pebble_count,
        "pebble_diameter_range_m": [0.005, 0.024],
        "residue_object": residue.name,
        "residue_fragment_count": residue_count,
        "row_centers_y_m": row_centers,
        "furrow_ridge_height_m": 0.014,
        "furrow_ridge_half_width_m": 0.55,
        "scientific_scene_modified": False,
    }


def configure_cycles(samples: int, resolution_x: int, resolution_y: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    scene.cycles.transparent_max_bounces = 12
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.view_settings.exposure = -0.9
    scene.view_settings.gamma = 1.0
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        for device in preferences.devices:
            device.use = True
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"


def add_camera_label(label: str) -> None:
    if not label:
        return
    camera = bpy.context.scene.camera
    if not camera:
        return
    material = bpy.data.materials.new("SWEEP_Render_Label_Black")
    material.diffuse_color = (0.0, 0.0, 0.0, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf and "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bpy.ops.object.text_add()
    text = bpy.context.object
    text.name = "SWEEP Render Date Label"
    text.data.body = label
    text.data.align_x = "LEFT"
    text.data.align_y = "CENTER"
    text.data.materials.append(material)
    frame = camera.data.view_frame(scene=bpy.context.scene)
    distance = 2.0
    scale = distance / max(1.0e-6, abs(frame[0].z))
    min_x = min(point.x for point in frame) * scale
    max_x = max(point.x for point in frame) * scale
    min_y = min(point.y for point in frame) * scale
    max_y = max(point.y for point in frame) * scale
    text.data.size = 0.045 * (max_y - min_y)
    text.parent = camera
    text.location = (
        min_x + 0.04 * (max_x - min_x),
        max_y - 0.06 * (max_y - min_y),
        -distance,
    )
    text.rotation_euler = (0.0, 0.0, 0.0)


def write_report(
    path: Path,
    ground: bpy.types.Object,
    texture_paths: dict[str, str | None],
    soil_context: dict[str, object],
    args: argparse.Namespace,
) -> None:
    camera = bpy.context.scene.camera
    report = {
        "blend": str(args.output_blend.resolve()),
        "render": None if args.skip_render else str(args.render_output.resolve()),
        "ground_object": ground.name,
        "ground_vertices": len(ground.data.vertices),
        "ground_polygons": len(ground.data.polygons),
        "ground_modifiers": [modifier.name for modifier in ground.modifiers],
        "ground_textures": texture_paths,
        "displacement_strength_m": args.displacement_strength,
        "macro_displacement_strength_m": args.macro_displacement_strength,
        "material_displacement_strength_m": args.material_displacement_strength,
        "height_midpoint": args.height_midpoint,
        "height_extension": "REPEAT",
        "pbr_physical_width_m": {
            "brown_mud_dry": SOIL_BROWN_MUD_PHYSICAL_WIDTH_M,
            "dirt": SOIL_DIRT_PHYSICAL_WIDTH_M,
        },
        "soil_shader": {
            "material": SOIL_MATERIAL_NAME,
            "roughness": "direct scan maps; no narrow remap",
            "specular_ior_level": SOIL_SPECULAR_IOR_LEVEL,
            "normal_strength": SOIL_NORMAL_STRENGTH,
            "height_bump_strength": SOIL_HEIGHT_BUMP_STRENGTH,
            "height_bump_distance_m": SOIL_HEIGHT_BUMP_DISTANCE_M,
            "color_saturation": 1.05,
            "color_value": 0.64,
            "warm_tint_factor": 0.60,
            "warm_tint_linear_rgba": [0.55, 0.23, 0.06, 1.0],
            "brown_mud_scan_fraction": [0.72, 0.92],
            "dirt_scan_fraction": [0.08, 0.28],
            "normal_and_displacement_source": "brown_mud_dry_correlated_maps",
            "geometry_nodes_scan_displacement_m": args.displacement_strength,
            "scan_height_applied_more_than_once": False,
            "crack_cell_scale_per_m": SOIL_CRACK_CELL_SCALE_PER_M,
            "crack_bump_strength": SOIL_CRACK_BUMP_STRENGTH,
            "crack_bump_distance_m": SOIL_CRACK_BUMP_DISTANCE_M,
            "material_displacement_method": getattr(
                bpy.data.materials[SOIL_MATERIAL_NAME], "displacement_method", None
            ),
            "material_output_displacement_linked": bool(
                next(
                    node
                    for node in bpy.data.materials[SOIL_MATERIAL_NAME].node_tree.nodes
                    if node.type == "OUTPUT_MATERIAL"
                ).inputs["Displacement"].is_linked
            ),
        },
        "soil_context": soil_context,
        "label": args.label,
        "camera": {
            "name": camera.name if camera else None,
            "location": list(camera.location) if camera else None,
            "rotation_euler": list(camera.rotation_euler) if camera else None,
            "lens": camera.data.lens if camera else None,
        },
        "cycles": {
            "samples": bpy.context.scene.cycles.samples,
            "device": bpy.context.scene.cycles.device,
            "resolution": [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y],
        },
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.output_blend = args.output_blend.resolve()
    args.render_output = args.render_output.resolve()
    args.height_texture = args.height_texture.resolve()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    if not bpy.context.scene.camera:
        raise RuntimeError("The blend file has no active camera; refusing to invent one")

    height_path = ensure_soil_height_texture(args.output_blend, args.height_texture)
    ground = find_ground_object()
    bases = stem_base_records()
    if len(bases) != 60:
        raise RuntimeError(f"expected 60 stem bases, got {len(bases)}")
    row_centers_y = inferred_row_centers_y(bases)
    texture_paths = rebuild_ground_material(
        ground,
        texture_dir_for_blend(args.output_blend),
        height_path,
        args.material_displacement_strength,
    )
    if abs(args.displacement_strength) > 1.0e-9 or abs(args.macro_displacement_strength) > 1.0e-9:
        apply_ground_displacement_modifier(
            ground,
            height_path,
            args.displacement_strength,
            args.macro_displacement_strength,
            args.height_midpoint,
            [],
        )
    else:
        for modifier in list(ground.modifiers):
            if modifier.name == "SWEEP Ground Height Displacement":
                ground.modifiers.remove(modifier)
    soil_context = create_soil_context(ground, bpy.data.materials[SOIL_MATERIAL_NAME], bases)
    configure_cycles(args.samples, args.resolution_x, args.resolution_y)

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    if not args.skip_render:
        add_camera_label(args.label)
        args.render_output.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(args.render_output)
        bpy.ops.render.render(write_still=True)

    write_report(
        args.output_blend.with_name(args.output_blend.stem + "_report.json"),
        ground,
        texture_paths,
        soil_context,
        args,
    )


if __name__ == "__main__":
    main()
