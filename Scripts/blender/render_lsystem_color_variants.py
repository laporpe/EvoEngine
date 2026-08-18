"""Render controlled Blender-side color variants from an exported sorghum scene."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


LEAF_MATERIAL = "SWEEP_LSystem_Leaf_Cycles"
GROUND_MATERIAL = "SWEEP_Ground_Soil_Displaced_Cycles"
COLOR_NODE_LABEL = "SWEEP reference-photo color calibration"
CAMERA_BACKGROUND_LABEL = "SWEEP camera-visible sky"
CAMERA_LIGHT_PATH_LABEL = "SWEEP camera-ray sky selector"
CAMERA_MIX_LABEL = "SWEEP camera/environment world mix"

PROFILES = {
    "baseline": {
        "exposure": -0.2,
        "world_strength": 1.0,
        "sun_elevation_deg": 90.0,
        "sun_rotation_deg": 0.0,
        "sun_intensity": 0.1,
        "sun_size_deg": 0.0,
        "leaf_saturation": 1.0,
        "leaf_value": 1.0,
        "leaf_sss_weight": 0.14,
        "leaf_sss_scale": 0.018,
        "leaf_specular": 0.72,
        "leaf_sheen": 0.18,
        "soil_saturation": 1.0,
        "soil_value": 1.0,
    },
    "reference_photo": {
        "exposure": -0.90,
        "world_strength": 0.65,
        "camera_sky_strength": 1.40,
        "sun_elevation_deg": 55.0,
        "sun_rotation_deg": 135.0,
        "sun_intensity": 0.35,
        "sun_size_deg": 0.53,
        "leaf_saturation": 1.05,
        "leaf_value": 0.88,
        "leaf_sss_weight": 0.06,
        "leaf_sss_scale": 0.009,
        "leaf_specular": 0.35,
        "leaf_sheen": 0.07,
        "soil_saturation": 1.75,
        "soil_value": 0.15,
    },
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--profiles", default="reference_photo")
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--resolution-x", type=int, default=960)
    parser.add_argument("--resolution-y", type=int, default=640)
    parser.add_argument("--camera-profile", choices=("saved", "close"), default="saved")
    return parser.parse_args(argv)


def required_material(name: str) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if not material or not material.node_tree:
        raise RuntimeError(f"Required material is missing: {name}")
    return material


def principled(material: bpy.types.Material) -> bpy.types.Node:
    nodes = [node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"]
    if len(nodes) != 1:
        raise RuntimeError(f"{material.name}: expected one Principled BSDF, found {len(nodes)}")
    return nodes[0]


def ensure_color_node(material: bpy.types.Material) -> bpy.types.Node:
    nodes = material.node_tree.nodes
    matches = [node for node in nodes if node.label == COLOR_NODE_LABEL]
    if len(matches) > 1:
        raise RuntimeError(f"{material.name}: duplicate color calibration nodes")
    if matches:
        return matches[0]

    bsdf = principled(material)
    base_color = bsdf.inputs["Base Color"]
    incoming = list(base_color.links)
    if len(incoming) != 1:
        raise RuntimeError(f"{material.name}: expected one Base Color link, found {len(incoming)}")
    source = incoming[0].from_socket
    material.node_tree.links.remove(incoming[0])
    node = nodes.new("ShaderNodeHueSaturation")
    node.name = f"{material.name} Reference Color Calibration"
    node.label = COLOR_NODE_LABEL
    node.location = (40, 150)
    material.node_tree.links.new(source, node.inputs["Color"])
    material.node_tree.links.new(node.outputs["Color"], base_color)
    return node


def set_input(node: bpy.types.Node, name: str, value: float) -> None:
    if name not in node.inputs:
        raise RuntimeError(f"{node.name}: required input is missing: {name}")
    node.inputs[name].default_value = value


def configure_close_camera() -> None:
    scene = bpy.context.scene
    camera = scene.camera
    if not camera:
        raise RuntimeError("The scene has no active camera")
    prefixes = (
        LEAF_MATERIAL,
        "SWEEP_Stem_VertexColor_",
        "SWEEP_PARBAR_",
    )
    framed = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        if any(
            slot.material and slot.material.name.startswith(prefixes)
            for slot in obj.material_slots
        ):
            framed.append(obj)
    if not framed:
        raise RuntimeError("No plant or PARBAR objects were available for close framing")
    points = [obj.matrix_world @ Vector(corner) for obj in framed for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    center = (minimum + maximum) * 0.5
    diagonal = max((maximum - minimum).length, 1.0)
    camera.location = center + Vector((-0.46 * diagonal, -0.52 * diagonal, 0.22 * diagonal))
    target = center
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 40.0
    camera.data.clip_end = diagonal * 8.0


def configure_color_management(scene: bpy.types.Scene, exposure: float) -> None:
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    else:
        raise RuntimeError("The authored AgX Medium High Contrast look is unavailable")
    scene.view_settings.exposure = exposure
    scene.view_settings.gamma = 1.0


def ensure_camera_background(world: bpy.types.World, sky: bpy.types.Node, lighting: bpy.types.Node) -> bpy.types.Node:
    nodes = world.node_tree.nodes
    camera_nodes = [node for node in nodes if node.label == CAMERA_BACKGROUND_LABEL]
    if camera_nodes:
        if len(camera_nodes) != 1:
            raise RuntimeError("The world has duplicate camera-visible sky nodes")
        return camera_nodes[0]

    outputs = [node for node in nodes if node.type == "OUTPUT_WORLD"]
    if len(outputs) != 1:
        raise RuntimeError(f"Expected one World Output node, found {len(outputs)}")
    output = outputs[0]
    surface_links = list(output.inputs["Surface"].links)
    if len(surface_links) != 1 or surface_links[0].from_node != lighting:
        raise RuntimeError("The authored environment background is not directly linked to World Output")
    world.node_tree.links.remove(surface_links[0])

    camera = nodes.new("ShaderNodeBackground")
    camera.name = "SWEEP Camera-Visible Sky"
    camera.label = CAMERA_BACKGROUND_LABEL
    camera.location = (250, -190)
    light_path = nodes.new("ShaderNodeLightPath")
    light_path.label = CAMERA_LIGHT_PATH_LABEL
    light_path.location = (250, -390)
    mix = nodes.new("ShaderNodeMixShader")
    mix.label = CAMERA_MIX_LABEL
    mix.location = (500, 0)
    world.node_tree.links.new(sky.outputs["Color"], camera.inputs["Color"])
    world.node_tree.links.new(light_path.outputs["Is Camera Ray"], mix.inputs[0])
    world.node_tree.links.new(lighting.outputs["Background"], mix.inputs[1])
    world.node_tree.links.new(camera.outputs["Background"], mix.inputs[2])
    world.node_tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return camera


def configure_world(profile: dict[str, float]) -> None:
    world = bpy.context.scene.world
    if not world or not world.node_tree:
        raise RuntimeError("The scene has no authored world node tree")
    sky_nodes = [node for node in world.node_tree.nodes if node.type == "TEX_SKY"]
    background_nodes = [
        node
        for node in world.node_tree.nodes
        if node.type == "BACKGROUND" and node.label != CAMERA_BACKGROUND_LABEL
    ]
    if len(sky_nodes) != 1 or len(background_nodes) != 1:
        raise RuntimeError("Expected one Sky Texture and one Background node")
    sky = sky_nodes[0]
    background = background_nodes[0]
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = True
    sky.sun_elevation = math.radians(profile["sun_elevation_deg"])
    sky.sun_rotation = math.radians(profile["sun_rotation_deg"])
    sky.sun_intensity = profile["sun_intensity"]
    sky.sun_size = math.radians(profile["sun_size_deg"])
    background.inputs["Strength"].default_value = profile["world_strength"]
    camera = ensure_camera_background(world, sky, background)
    camera.inputs["Strength"].default_value = profile.get("camera_sky_strength", profile["world_strength"])


def apply_profile(name: str, profile: dict[str, float]) -> dict[str, object]:
    scene = bpy.context.scene
    configure_color_management(scene, profile["exposure"])
    configure_world(profile)

    leaf = required_material(LEAF_MATERIAL)
    leaf_bsdf = principled(leaf)
    leaf_color = ensure_color_node(leaf)
    set_input(leaf_color, "Saturation", profile["leaf_saturation"])
    set_input(leaf_color, "Value", profile["leaf_value"])
    set_input(leaf_bsdf, "Subsurface Weight", profile["leaf_sss_weight"])
    set_input(leaf_bsdf, "Subsurface Scale", profile["leaf_sss_scale"])
    set_input(leaf_bsdf, "Specular IOR Level", profile["leaf_specular"])
    set_input(leaf_bsdf, "Sheen Weight", profile["leaf_sheen"])

    ground = required_material(GROUND_MATERIAL)
    ground_color = ensure_color_node(ground)
    set_input(ground_color, "Saturation", profile["soil_saturation"])
    set_input(ground_color, "Value", profile["soil_value"])
    return {"profile": name, **profile}


def main() -> None:
    args = parse_args()
    args.blend = args.blend.resolve()
    args.output_dir = args.output_dir.resolve()
    selected = [name.strip() for name in args.profiles.split(",") if name.strip()]
    unknown = [name for name in selected if name not in PROFILES]
    if unknown:
        raise ValueError(f"Unknown profiles: {', '.join(unknown)}")

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if args.camera_profile == "close":
        configure_close_camera()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report = []
    for name in selected:
        applied = apply_profile(name, PROFILES[name])
        render_path = args.output_dir / f"{name}.png"
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        if not render_path.exists():
            raise RuntimeError(f"Render was not created: {render_path}")
        report.append({**applied, "render": str(render_path)})
        print(f"SWEEP_COLOR_VARIANT passed profile={name} output={render_path}")

    (args.output_dir / "color_variants.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
