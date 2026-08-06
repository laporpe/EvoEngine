"""Prepare an EvoEngine LSystem sorghum glTF export for Blender Cycles."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


LEAF_TEXTURES = {
    "albedo": ("sorghum_lsystem_leaf_variants_albedo.png", "sorghum_leaf_stem_atlas_albedo.png"),
    "normal": ("sorghum_lsystem_leaf_variants_normal.png", "sorghum_leaf_stem_atlas_normal.png"),
    "roughness": ("sorghum_lsystem_leaf_variants_roughness.png", "sorghum_leaf_stem_atlas_roughness.png"),
    "ao": ("sorghum_lsystem_leaf_variants_ao.png", "sorghum_leaf_stem_atlas_ao.png"),
    "height": ("sorghum_lsystem_leaf_variants_height.png",),
    "metallic": ("sorghum_lsystem_leaf_variants_metallic.png", "sorghum_leaf_stem_atlas_metallic.png"),
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

LEAF_COLOR_DEFAULTS = {
    "Saturation": 1.05,
    "Value": 0.88,
}

# Blender 5 exposes the Nishita atmosphere as single- or multiple-scattering
# Sky Texture modes. These reference-photo-matched values retain the otherwise
# easy-to-miss altitude default.
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
WORLD_LIGHTING_STRENGTH = 0.65
WORLD_CAMERA_STRENGTH = 1.40

# Author-approved fixed field camera, captured from the manually composed
# 2021-08-18 Blender scene. Keep this absolute across dates so growth-stage
# comparisons do not acquire camera motion from date-dependent canopy bounds.
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--gltf", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--render-output", type=Path)
    parser.add_argument("--resolution-x", type=int, default=3000)
    parser.add_argument("--resolution-y", type=int, default=2000)
    parser.add_argument("--samples", type=int, default=512)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def set_colorspace(image: bpy.types.Image, name: str) -> None:
    try:
        image.colorspace_settings.name = name
    except TypeError:
        pass


def load_image(path: Path, colorspace: str) -> bpy.types.Image | None:
    if not path or not path.exists():
        return None
    image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    set_colorspace(image, colorspace)
    return image


def find_texture(texture_dir: Path, names: tuple[str, ...]) -> Path | None:
    if not texture_dir.exists():
        return None
    lower_names = {name.lower() for name in names}
    for path in texture_dir.iterdir():
        if path.is_file() and path.name.lower() in lower_names:
            return path
    return None


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


def set_input_default(node: bpy.types.Node, names: tuple[str, ...], value) -> None:
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return
    raise RuntimeError(f"{node.bl_idname} is missing required input: {' or '.join(names)}")


def link_image(material: bpy.types.Material, image: bpy.types.Image, label: str) -> bpy.types.Node:
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.label = label
    node.image = image
    return node


def enable_material_displacement(material: bpy.types.Material, max_displacement: float) -> None:
    if hasattr(material, "displacement_method"):
        material.displacement_method = "DISPLACEMENT"
    if hasattr(material, "max_vertex_displacement"):
        material.max_vertex_displacement = max_displacement


def build_leaf_material(texture_dir: Path) -> tuple[bpy.types.Material, dict[str, str | None]]:
    material, bsdf = new_principled_material("SWEEP_LSystem_Leaf_Cycles")
    bsdf.name = "SWEEP Leaf Principled BSDF"
    bsdf.label = "authored leaf SSS and surface response"
    material.blend_method = "HASHED"
    material.use_screen_refraction = False
    material.use_backface_culling = False
    enable_material_displacement(material, 0.003)
    if hasattr(material, "show_transparent_back"):
        material.show_transparent_back = True
    for socket_name, value in LEAF_PRINCIPLED_DEFAULTS.items():
        set_input_default(bsdf, (socket_name,), value)

    paths = {key: find_texture(texture_dir, names) for key, names in LEAF_TEXTURES.items()}
    images = {
        "albedo": load_image(paths["albedo"], "sRGB") if paths["albedo"] else None,
        "normal": load_image(paths["normal"], "Non-Color") if paths["normal"] else None,
        "roughness": load_image(paths["roughness"], "Non-Color") if paths["roughness"] else None,
        "ao": load_image(paths["ao"], "Non-Color") if paths["ao"] else None,
        "height": load_image(paths["height"], "Non-Color") if paths["height"] else None,
        "metallic": load_image(paths["metallic"], "Non-Color") if paths["metallic"] else None,
    }

    links = material.node_tree.links
    if images["albedo"]:
        albedo = link_image(material, images["albedo"], "albedo")
        albedo.location = (-760, 160)
        color_output = albedo.outputs["Color"]
        if images["ao"]:
            ao = link_image(material, images["ao"], "ao")
            ao.location = (-760, -60)
            multiply = material.node_tree.nodes.new("ShaderNodeMix")
            multiply.data_type = "RGBA"
            multiply.factor_mode = "UNIFORM"
            multiply.blend_type = "MULTIPLY"
            multiply.inputs["Factor"].default_value = 0.35
            multiply.location = (-420, 110)
            links.new(albedo.outputs["Color"], multiply.inputs["A"])
            links.new(ao.outputs["Color"], multiply.inputs["B"])
            color_output = multiply.outputs["Result"]
        color_calibration = material.node_tree.nodes.new("ShaderNodeHueSaturation")
        color_calibration.name = "SWEEP Leaf Reference Color Calibration"
        color_calibration.label = "SWEEP reference-photo color calibration"
        color_calibration.location = (-100, 130)
        for socket_name, value in LEAF_COLOR_DEFAULTS.items():
            color_calibration.inputs[socket_name].default_value = value
        links.new(color_output, color_calibration.inputs["Color"])
        color_output = color_calibration.outputs["Color"]
        links.new(color_output, bsdf.inputs["Base Color"])
        if "Alpha" in bsdf.inputs:
            links.new(albedo.outputs["Alpha"], bsdf.inputs["Alpha"])
    else:
        set_input_default(bsdf, ("Base Color",), (0.28, 0.47, 0.17, 1.0))

    if images["roughness"] and "Roughness" in bsdf.inputs:
        roughness = link_image(material, images["roughness"], "roughness")
        roughness.location = (-420, -210)
        links.new(roughness.outputs["Color"], bsdf.inputs["Roughness"])
    if images["metallic"] and "Metallic" in bsdf.inputs:
        metallic = link_image(material, images["metallic"], "metallic")
        metallic.location = (-420, -390)
        links.new(metallic.outputs["Color"], bsdf.inputs["Metallic"])

    normal_output = None
    if images["normal"]:
        normal_tex = link_image(material, images["normal"], "normal")
        normal_tex.location = (-760, -580)
        normal = material.node_tree.nodes.new("ShaderNodeNormalMap")
        normal.label = "authored leaf normal"
        normal.location = (-420, -560)
        normal.inputs["Strength"].default_value = 0.6
        links.new(normal_tex.outputs["Color"], normal.inputs["Color"])
        normal_output = normal.outputs["Normal"]
    if images["height"]:
        height_tex = link_image(material, images["height"], "height")
        height_tex.location = (-760, -790)
        bump = material.node_tree.nodes.new("ShaderNodeBump")
        bump.label = "authored leaf height micro-bump"
        bump.location = (-140, -620)
        bump.inputs["Strength"].default_value = 0.012
        bump.inputs["Distance"].default_value = 0.004
        links.new(height_tex.outputs["Color"], bump.inputs["Height"])
        if normal_output:
            links.new(normal_output, bump.inputs["Normal"])
        normal_output = bump.outputs["Normal"]
    texcoord = material.node_tree.nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-1180, -1010)
    mapping = material.node_tree.nodes.new("ShaderNodeMapping")
    mapping.label = "authored elongated leaf grain mapping"
    mapping.location = (-980, -1010)
    if "Scale" in mapping.inputs:
        mapping.inputs["Scale"].default_value = (0.22, 9.0, 1.0)
    grain = material.node_tree.nodes.new("ShaderNodeTexNoise")
    grain.label = "elongated grain displacement"
    grain.location = (-760, -1010)
    grain.inputs["Scale"].default_value = 34.0
    grain.inputs["Detail"].default_value = 14.0
    grain.inputs["Roughness"].default_value = 0.62
    ramp = material.node_tree.nodes.new("ShaderNodeValToRGB")
    ramp.label = "authored elongated leaf grain ramp"
    ramp.location = (-500, -1010)
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[1].position = 0.86
    leaf_bump = material.node_tree.nodes.new("ShaderNodeBump")
    leaf_bump.label = "authored elongated leaf grain bump"
    leaf_bump.location = (-130, -930)
    leaf_bump.inputs["Strength"].default_value = 0.008
    leaf_bump.inputs["Distance"].default_value = 0.003
    leaf_displacement = material.node_tree.nodes.new("ShaderNodeDisplacement")
    leaf_displacement.label = "authored leaf micro-displacement"
    leaf_displacement.location = (260, -890)
    leaf_displacement.inputs["Scale"].default_value = 0.001
    leaf_displacement.inputs["Midlevel"].default_value = 0.5
    output = next(node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL")
    links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], grain.inputs["Vector"])
    links.new(grain.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], leaf_bump.inputs["Height"])
    if normal_output:
        links.new(normal_output, leaf_bump.inputs["Normal"])
    normal_output = leaf_bump.outputs["Normal"]
    links.new(ramp.outputs["Color"], leaf_displacement.inputs["Height"])
    links.new(leaf_displacement.outputs["Displacement"], output.inputs["Displacement"])
    if normal_output and "Normal" in bsdf.inputs:
        links.new(normal_output, bsdf.inputs["Normal"])

    return material, {key: str(value) if value else None for key, value in paths.items()}


def build_stem_material(obj: bpy.types.Object) -> bpy.types.Material:
    material, bsdf = new_principled_material(f"SWEEP_Stem_VertexColor_{obj.name}")
    set_input_default(bsdf, ("Roughness",), 0.72)
    set_input_default(bsdf, ("Metallic",), 0.0)
    set_input_default(bsdf, ("Base Color",), (0.34, 0.43, 0.19, 1.0))

    color_attributes = getattr(obj.data, "color_attributes", None)
    if color_attributes and len(color_attributes):
        attribute = material.node_tree.nodes.new("ShaderNodeAttribute")
        attribute.attribute_name = color_attributes[0].name
        attribute.location = (-240, 70)
        material.node_tree.links.new(attribute.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def build_simple_principled_material(
    name: str,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
    specular: float,
    diffuse_roughness: float = 0.35,
) -> bpy.types.Material:
    material, bsdf = new_principled_material(name)
    set_input_default(bsdf, ("Base Color",), base_color)
    set_input_default(bsdf, ("Metallic",), metallic)
    set_input_default(bsdf, ("Roughness",), roughness)
    set_input_default(bsdf, ("Specular IOR Level",), specular)
    set_input_default(bsdf, ("Diffuse Roughness",), diffuse_roughness)
    return material


def object_material_text(obj: bpy.types.Object) -> str:
    parts = [obj.name]
    for material in obj.data.materials if hasattr(obj.data, "materials") else []:
        if material:
            parts.append(material.name)
            if material.use_nodes:
                for node in material.node_tree.nodes:
                    if getattr(node, "image", None):
                        parts.append(node.image.filepath)
    return " ".join(parts).lower()


def is_leaf_object(obj: bpy.types.Object) -> bool:
    text = object_material_text(obj)
    return "sorghum leaves" in text or "sorghum_lsystem_leaf_variants_albedo" in text or "sorghum_leaf_stem_atlas" in text


def is_stem_object(obj: bpy.types.Object) -> bool:
    text = object_material_text(obj)
    return "sorghum internodes" in text or "internodes export mesh" in text


def is_parbar_metal_object(obj: bpy.types.Object) -> bool:
    name = obj.name.lower()
    return name.startswith("modular_metal_gutter_")


def is_parbar_panel_object(obj: bpy.types.Object) -> bool:
    return obj.name.lower().startswith("model.003")


def is_parbar_long_bar_object(obj: bpy.types.Object) -> bool:
    name = obj.name.lower()
    return (
        name == "model"
        or name.startswith("model.") and not name.startswith("model.003")
        or name.startswith("parbar_pawaga_")
        or name.startswith("parbar_btx_")
    )


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def configure_materials(texture_dir: Path) -> dict[str, object]:
    leaf_material, leaf_paths = build_leaf_material(texture_dir)
    parbar_metal_material = build_simple_principled_material(
        "SWEEP_PARBAR_Brushed_White_Metal_Cycles",
        (0.82, 0.82, 0.78, 1.0),
        1.0,
        0.38,
        1.0,
        0.55,
    )
    parbar_bar_material = build_simple_principled_material(
        "SWEEP_PARBAR_Long_Bar_Plastic_Cycles",
        (0.74, 0.75, 0.70, 1.0),
        0.0,
        0.48,
        0.46,
        0.6,
    )
    parbar_panel_material = build_simple_principled_material(
        "SWEEP_PARBAR_Solar_Panel_Plastic_Cycles",
        (0.05, 0.075, 0.105, 1.0),
        0.0,
        0.36,
        0.58,
        0.5,
    )
    leaf_objects = []
    stem_objects = []
    parbar_metal_objects = []
    parbar_bar_objects = []
    parbar_panel_objects = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.name.lower().startswith("slice"):
            obj.hide_viewport = True
            obj.hide_render = True
            continue
        if is_leaf_object(obj):
            assign_material(obj, leaf_material)
            leaf_objects.append(obj.name)
        elif is_stem_object(obj):
            assign_material(obj, build_stem_material(obj))
            stem_objects.append(obj.name)
        elif is_parbar_metal_object(obj):
            assign_material(obj, parbar_metal_material)
            parbar_metal_objects.append(obj.name)
        elif is_parbar_panel_object(obj):
            assign_material(obj, parbar_panel_material)
            parbar_panel_objects.append(obj.name)
        elif is_parbar_long_bar_object(obj):
            assign_material(obj, parbar_bar_material)
            parbar_bar_objects.append(obj.name)
        else:
            for material in obj.data.materials:
                if material:
                    material.blend_method = "OPAQUE"
                    material.use_backface_culling = False
    return {
        "leaf_objects": leaf_objects,
        "stem_objects": stem_objects,
        "parbar_metal_objects": parbar_metal_objects,
        "parbar_long_bar_objects": parbar_bar_objects,
        "parbar_panel_objects": parbar_panel_objects,
        "leaf_textures": leaf_paths,
    }


def configure_cycles(samples: int, resolution_x: int, resolution_y: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    else:
        # Make the compatibility fallback explicit so reopening the file cannot
        # inherit a workstation default.
        scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.9
    scene.view_settings.gamma = 1.0
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"


def visible_mesh_bounds(objects: list[bpy.types.Object] | None = None) -> tuple[Vector, Vector]:
    points = []
    source = objects if objects is not None else bpy.context.scene.objects
    for obj in source:
        if obj.type != "MESH" or obj.hide_render:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return Vector((-1.0, -1.0, -1.0)), Vector((1.0, 1.0, 1.0))
    minimum = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    maximum = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    return minimum, maximum


def plant_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and (is_leaf_object(obj) or is_stem_object(obj))]


def framing_objects() -> list[bpy.types.Object]:
    return [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and (
            is_leaf_object(obj)
            or is_stem_object(obj)
            or is_parbar_metal_object(obj)
            or is_parbar_panel_object(obj)
            or is_parbar_long_bar_object(obj)
        )
    ]


def configure_camera() -> dict[str, object]:
    plants = plant_objects()
    framed = framing_objects() or plants
    minimum, maximum = visible_mesh_bounds(framed if framed else None)
    camera = next((obj for obj in bpy.context.scene.objects if obj.type == "CAMERA"), None)
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.object
    camera.name = "Cycles Paper Camera"
    camera.parent = None
    camera.rotation_mode = "XYZ"
    camera.matrix_world = Matrix(CAMERA_MATRIX_WORLD)
    for property_name, value in CAMERA_DATA_DEFAULTS.items():
        set_required_property(camera.data, property_name, value)
    camera.data.dof.use_dof = False
    bpy.context.scene.camera = camera
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    for obj in plants:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = plants[0] if plants else camera
    return {
        "framed_objects": len(framed),
        "plant_objects": len(plants),
        "bounds_min": list(minimum),
        "bounds_max": list(maximum),
        "matrix_world": [list(row) for row in camera.matrix_world],
        "location": list(camera.location),
        "rotation_euler": list(camera.rotation_euler),
        "data": {name: getattr(camera.data, name) for name in CAMERA_DATA_DEFAULTS},
        "dof_use": camera.data.dof.use_dof,
    }


def set_required_property(obj: object, name: str, value: object) -> None:
    if not hasattr(obj, name):
        raise RuntimeError(f"{type(obj).__name__} is missing required property: {name}")
    setattr(obj, name, value)


def configure_reference_photo_world() -> dict[str, object]:
    for obj in [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    world = bpy.context.scene.world or bpy.data.worlds.new("SWEEP High Noon Sky World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    output.location = (720, 0)
    mix = nodes.new("ShaderNodeMixShader")
    mix.label = "SWEEP camera/environment world mix"
    mix.location = (500, 0)
    background = nodes.new("ShaderNodeBackground")
    background.label = "SWEEP environment lighting"
    background.location = (250, 80)
    camera_background = nodes.new("ShaderNodeBackground")
    camera_background.label = "SWEEP camera-visible sky"
    camera_background.location = (250, -120)
    light_path = nodes.new("ShaderNodeLightPath")
    light_path.label = "SWEEP camera-ray sky selector"
    light_path.location = (250, -320)
    sky = nodes.new("ShaderNodeTexSky")
    sky.location = (-80, 0)
    sky.label = "Nishita multiple-scattering reference-photo sky"
    for property_name, value in NISHITA_SKY_DEFAULTS.items():
        set_required_property(sky, property_name, value)
    background.inputs["Strength"].default_value = WORLD_LIGHTING_STRENGTH
    camera_background.inputs["Strength"].default_value = WORLD_CAMERA_STRENGTH
    world.node_tree.links.new(sky.outputs["Color"], background.inputs["Color"])
    world.node_tree.links.new(sky.outputs["Color"], camera_background.inputs["Color"])
    world.node_tree.links.new(light_path.outputs["Is Camera Ray"], mix.inputs[0])
    world.node_tree.links.new(background.outputs["Background"], mix.inputs[1])
    world.node_tree.links.new(camera_background.outputs["Background"], mix.inputs[2])
    world.node_tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return {
        "model": "Nishita",
        **{name: getattr(sky, name) for name in NISHITA_SKY_DEFAULTS},
        "sun_elevation_deg": math.degrees(sky.sun_elevation),
        "background_strength": background.inputs["Strength"].default_value,
        "camera_background_strength": camera_background.inputs["Strength"].default_value,
        "sun_objects": sum(
            1 for obj in bpy.context.scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN"
        ),
    }


def report_path(output_blend: Path) -> Path:
    return output_blend.with_name(output_blend.stem + "_blender_report.json")


def main() -> None:
    args = parse_args()
    args.gltf = args.gltf.resolve()
    if args.manifest:
        args.manifest = args.manifest.resolve()
    args.output_blend = args.output_blend.resolve()
    if args.render_output:
        args.render_output = args.render_output.resolve()
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(args.gltf))
    texture_dir = args.gltf.parent / "textures"
    material_report = configure_materials(texture_dir)
    configure_cycles(args.samples, args.resolution_x, args.resolution_y)
    camera_report = configure_camera()
    world_report = configure_reference_photo_world()

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    if args.render_output:
        args.render_output.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.filepath = str(args.render_output)
        bpy.ops.render.render(write_still=True)

    manifest = {}
    if args.manifest and args.manifest.exists():
        manifest = json.loads(args.manifest.read_text())
    report = {
        "gltf": str(args.gltf),
        "blend": str(args.output_blend),
        "render": str(args.render_output) if args.render_output else None,
        "manifest": manifest,
        "objects": len(bpy.context.scene.objects),
        "mesh_objects": sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH"),
        "materials": len(bpy.data.materials),
        "camera": camera_report,
        "world": world_report,
        **material_report,
    }
    report_path(args.output_blend).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"SWEEP_BLENDER_PREPARE passed output={args.output_blend}")


if __name__ == "__main__":
    main()
