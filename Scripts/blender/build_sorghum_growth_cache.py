"""Build and render an animated Blender scene from native EvoEngine snapshots.

Run with Blender --background --python-exit-code 1 --python this_file -- --manifest ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from pxr import Gf, Sdf, Usd, UsdGeom, Vt

PARTS = ("culm", "leaves", "panicle")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "PythonBinding"))
from sorghum_growth_export import aligned_triangles, validate_manifest


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def blender_point(point):
    return Vector((point[0], -point[2], point[1]))


def mesh_name(plant_id, part):
    return f"{plant_id}_{part}"


def build_cache(manifest, source, output):
    stage = Usd.Stage.CreateNew(str(output))
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(len(manifest["frames"]))
    stage.SetTimeCodesPerSecond(manifest["fps"])
    stage.SetFramesPerSecond(manifest["fps"])
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    transforms, meshes = {}, {}
    for plant in manifest["plants"]:
        key = plant["id"]
        node = UsdGeom.Xform.Define(stage, f"/Plants/{key}")
        node.GetPrim().SetCustomDataByKey("genotype", plant["genotype"])
        node.GetPrim().SetCustomDataByKey("seed", str(plant["seed"]))
        transforms[key] = node.AddTransformOp()
        for part in PARTS:
            mesh = UsdGeom.Mesh.Define(stage, f"/Plants/{key}/{mesh_name(key, part)}")
            mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            mesh.CreateDoubleSidedAttr(True)
            mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
            meshes[key, part] = (
                mesh,
                UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
                    "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
                ),
                mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex),
                mesh.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.vertex),
            )
    for sample in manifest["frames"]:
        path, frame = source / sample["file"], sample["frame"]
        if file_hash(path) != sample["sha256"]:
            raise ValueError(f"Snapshot hash mismatch: {path}")
        with np.load(path, allow_pickle=False) as arrays:
            for plant in manifest["plants"]:
                key = plant["id"]
                transforms[key].Set(
                    Gf.Matrix4d(
                        arrays[f"{key}/world_transform"].T.astype(float).tolist()
                    ),
                    frame,
                )
                for part in PARTS:
                    mesh, uv, color, opacity = meshes[key, part]
                    prefix = f"{key}/{part}"
                    points = arrays[f"{prefix}/positions"]
                    triangles = aligned_triangles(
                        points,
                        arrays[f"{prefix}/normals"],
                        arrays[f"{prefix}/triangles"],
                    )
                    colors = arrays[f"{prefix}/colors"]
                    mesh.CreatePointsAttr().Set(Vt.Vec3fArray.FromNumpy(points), frame)
                    mesh.CreateFaceVertexCountsAttr().Set(
                        Vt.IntArray.FromNumpy(np.full(len(triangles), 3, np.int32)),
                        frame,
                    )
                    mesh.CreateFaceVertexIndicesAttr().Set(
                        Vt.IntArray.FromNumpy(triangles.reshape(-1).astype(np.int32)),
                        frame,
                    )
                    mesh.CreateNormalsAttr().Set(
                        Vt.Vec3fArray.FromNumpy(arrays[f"{prefix}/normals"]), frame
                    )
                    uv.Set(Vt.Vec2fArray.FromNumpy(arrays[f"{prefix}/uv"]), frame)
                    color.Set(
                        Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(colors[:, :3])),
                        frame,
                    )
                    opacity.Set(
                        Vt.FloatArray.FromNumpy(np.ascontiguousarray(colors[:, 3])),
                        frame,
                    )
                    extent = (
                        [points.min(axis=0), points.max(axis=0)]
                        if len(points)
                        else [(0, 0, 0), (0, 0, 0)]
                    )
                    mesh.CreateExtentAttr().Set(
                        Vt.Vec3fArray.FromNumpy(np.asarray(extent, np.float32)), frame
                    )
        if frame % 20 == 0 or frame == len(manifest["frames"]):
            print(f"USD_SAMPLE {frame}/{len(manifest['frames'])}", flush=True)
    stage.GetRootLayer().Save()


def material(name, base, roughness=0.6):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return value, bsdf


def plant_material(part, textures):
    value, bsdf = material(f"Growth_{part}", (0.20, 0.38, 0.07))
    nodes, links = value.node_tree.nodes, value.node_tree.links
    colors = nodes.new("ShaderNodeVertexColor")
    colors.layer_name = "displayColor"
    links.new(colors.outputs["Color"], bsdf.inputs["Base Color"])
    if part == "leaves":
        bsdf.inputs["Subsurface Weight"].default_value = 0.06
        bsdf.inputs["Subsurface Radius"].default_value = (0.55, 0.78, 0.36)
        bsdf.inputs["Subsurface Scale"].default_value = 0.009
        bsdf.inputs["Sheen Weight"].default_value = 0.07
        bsdf.inputs["Specular IOR Level"].default_value = 0.35
        for kind in ("albedo", "normal", "roughness"):
            path = textures / f"sorghum_lsystem_leaf_variants_{kind}.png"
            if not path.is_file():
                continue
            image = bpy.data.images.load(str(path), check_existing=True)
            image.colorspace_settings.name = "sRGB" if kind == "albedo" else "Non-Color"
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = image
            if kind == "albedo":
                multiply = nodes.new("ShaderNodeMixRGB")
                multiply.blend_type = "MULTIPLY"
                multiply.inputs[0].default_value = 0.35
                links.new(colors.outputs["Color"], multiply.inputs[1])
                links.new(texture.outputs["Color"], multiply.inputs[2])
                links.new(multiply.outputs[0], bsdf.inputs["Base Color"])
                links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
            elif kind == "normal":
                normal = nodes.new("ShaderNodeNormalMap")
                normal.inputs["Strength"].default_value = 0.3
                links.new(texture.outputs["Color"], normal.inputs["Color"])
                links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
            else:
                links.new(texture.outputs["Color"], bsdf.inputs["Roughness"])
    return value


def add_text(body, camera, x, y, size, ink):
    curve = bpy.data.curves.new(body, "FONT")
    curve.body, curve.align_x, curve.size = body, "CENTER", size
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(body, curve)
    bpy.context.collection.objects.link(obj)
    obj.parent = camera
    obj.location = (x, y, -1)
    mat = bpy.data.materials.new(body + " ink")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    emission, out = (
        nodes.new("ShaderNodeEmission"),
        nodes.new("ShaderNodeOutputMaterial"),
    )
    emission.inputs["Color"].default_value = (*ink, 1)
    mat.node_tree.links.new(emission.outputs[0], out.inputs["Surface"])
    curve.materials.append(mat)
    obj.visible_shadow = False
    obj.visible_diffuse = False
    obj.visible_glossy = False
    return obj


def prepare_scene(manifest, source, output, args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.usd_import(
        filepath=str(output / "growth.usdc"),
        import_visible_only=False,
        set_frame_range=True,
        import_materials=False,
    )
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transparent_max_bounces = 16
    preferences = bpy.context.preferences.addons["cycles"].preferences
    try:
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == "OPTIX"
        if any(d.use for d in preferences.devices):
            scene.cycles.device = "GPU"
    except TypeError:
        pass
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = manifest["fps"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    textures = output / "textures"
    textures.mkdir(exist_ok=True)
    if args.leaf_atlas:
        for path in args.leaf_atlas.glob("sorghum_lsystem_leaf_variants_*.png"):
            if path.resolve() != (textures / path.name).resolve():
                shutil.copy2(path, textures / path.name)
    materials = {part: plant_material(part, textures) for part in PARTS}
    for plant in manifest["plants"]:
        for part in PARTS:
            obj = bpy.data.objects.get(mesh_name(plant["id"], part))
            if obj is None:
                raise RuntimeError(f"Missing imported plant mesh: {plant['id']}/{part}")
            obj.data.materials.clear()
            obj.data.materials.append(materials[part])
            # USD replaces mesh data as topology changes; retain the presentation material on the object.
            obj.material_slots[0].link = "OBJECT"
            obj.material_slots[0].material = materials[part]
            obj["evoengine_plant_id"], obj["genotype"] = plant["id"], plant["genotype"]

    ground, ground_bsdf = material("Soil", (0.075, 0.050, 0.032), 0.92)
    noise = ground.node_tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 65
    bump = ground.node_tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.008
    ground.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    ground.node_tree.links.new(bump.outputs["Normal"], ground_bsdf.inputs["Normal"])
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.012))
    bpy.context.object.name = "Presentation_Ground"
    bpy.context.object.data.materials.append(ground)
    world = bpy.data.worlds.new("Growth daylight")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (
        0.66,
        0.77,
        0.92,
        1,
    )
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = manifest[
        "lighting"
    ]["world_strength"]
    light = bpy.data.lights.new("Scheduled sun", "SUN")
    light.energy = manifest["lighting"]["sun_energy"]
    light.angle = math.radians(2.5)
    sun = bpy.data.objects.new("Scheduled sun", light)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (
        math.radians(90 - manifest["lighting"]["sun_elevation_degrees"]),
        0,
        math.radians(manifest["lighting"]["sun_azimuth_degrees"]),
    )

    shot = manifest["camera"]
    camera = bpy.data.objects.new(
        "EvoEngine shot", bpy.data.cameras.new("EvoEngine shot")
    )
    scene.collection.objects.link(camera)
    camera.location = blender_point(shot["position"])
    camera.rotation_euler = (
        (blender_point(shot["target"]) - camera.location)
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    camera.data.type = "ORTHO"
    # Blender's ortho_scale is horizontal for this landscape frame.
    camera.data.ortho_scale = shot["ortho_scale"] * (args.width / args.height)
    scene.camera = camera
    h = shot["ortho_scale"]
    add_text(
        "SORGHUM  /  GROWTH STUDY", camera, 0, h * 0.43, h * 0.033, (0.92, 0.96, 0.89)
    )
    add_text(
        "Native EvoEngine simulation  -  Blender Cycles",
        camera,
        0,
        h * 0.385,
        h * 0.016,
        (0.58, 0.68, 0.54),
    )
    bpy.context.view_layer.update()
    with np.load(source / manifest["frames"][-1]["file"], allow_pickle=False) as arrays:
        for plant in manifest["plants"]:
            origin = blender_point(arrays[f"{plant['id']}/world_transform"][:3, 3])
            local = camera.matrix_world.inverted() @ origin
            add_text(
                plant["genotype"].replace("Genotype", "GENOTYPE  "),
                camera,
                local.x,
                -h * 0.35,
                h * 0.024,
                (0.88, 0.93, 0.81),
            )
    add_text(
        f"{manifest['frames'][0]['gdd']:.0f} - {manifest['frames'][-1]['gdd']:.0f} GDD   /   fixed seeds   /   {len(manifest['plants'])} plants",
        camera,
        0,
        -h * 0.44,
        h * 0.018,
        (0.62, 0.71, 0.57),
    )
    scene["growth_manifest_sha256"] = file_hash(args.manifest)
    scene["growth_cache_sha256"] = file_hash(output / "growth.usdc")
    scene.frame_start, scene.frame_end = 1, len(manifest["frames"])
    scene.frame_set(scene.frame_end)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "abc_growth.blend"))
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "abc_growth.blend"))


def validate_scene(manifest, source, all_frames=False):
    result = []
    count = len(manifest["frames"])
    frames = (
        range(1, count + 1)
        if all_frames
        else {f for f in (1, 2, count // 3, count * 2 // 3, count) if 1 <= f <= count}
    )
    for frame in sorted(frames, reverse=True):
        sample = manifest["frames"][frame - 1]
        bpy.context.scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        with np.load(source / sample["file"], allow_pickle=False) as arrays:
            for plant in manifest["plants"]:
                key = plant["id"]
                for part in PARTS:
                    prefix = f"{key}/{part}"
                    obj = bpy.data.objects[mesh_name(key, part)]
                    evaluated = obj.evaluated_get(depsgraph)
                    mesh = evaluated.to_mesh()
                    expected = arrays[f"{prefix}/positions"]
                    assert len(mesh.vertices) == len(expected), (
                        frame,
                        prefix,
                        "vertices",
                    )
                    assert len(mesh.polygons) == len(arrays[f"{prefix}/triangles"]), (
                        frame,
                        prefix,
                        "triangles",
                    )
                    actual = np.empty(len(mesh.vertices) * 3, np.float32)
                    mesh.vertices.foreach_get("co", actual)
                    np.testing.assert_allclose(
                        actual.reshape(-1, 3), expected, atol=2e-6
                    )
                    if len(expected):
                        engine_world = arrays[f"{key}/world_transform"]
                        world_expected = (
                            expected @ engine_world[:3, :3].T + engine_world[:3, 3]
                        )
                        world_expected = world_expected[:, [0, 2, 1]] * np.array(
                            [1, -1, 1]
                        )
                        matrix = np.asarray(evaluated.matrix_world)
                        world_actual = (
                            actual.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3]
                        )
                        np.testing.assert_allclose(
                            world_actual, world_expected, atol=1e-5
                        )
                        assert mesh.uv_layers and mesh.color_attributes, (
                            frame,
                            prefix,
                            "attributes",
                        )
                        uv = np.empty(len(mesh.loops) * 2, np.float32)
                        mesh.uv_layers[0].data.foreach_get("uv", uv)
                        indices = np.empty(len(mesh.loops), np.int32)
                        mesh.loops.foreach_get("vertex_index", indices)
                        np.testing.assert_array_equal(
                            indices.reshape(-1, 3),
                            aligned_triangles(
                                expected,
                                arrays[f"{prefix}/normals"],
                                arrays[f"{prefix}/triangles"],
                            ),
                        )
                        np.testing.assert_allclose(
                            uv.reshape(-1, 2),
                            arrays[f"{prefix}/uv"][indices],
                            atol=2e-6,
                        )
                        normals = np.empty(len(mesh.corner_normals) * 3, np.float32)
                        mesh.corner_normals.foreach_get("vector", normals)
                        expected_normals = arrays[f"{prefix}/normals"][indices]
                        lengths = np.linalg.norm(
                            expected_normals, axis=1, keepdims=True
                        )
                        expected_normals = expected_normals / np.maximum(lengths, 1e-10)
                        imported = normals.reshape(-1, 3)
                        if not np.isfinite(imported).all():
                            raise ValueError(
                                f"Nonfinite Blender normals at frame {frame}, {prefix}"
                            )
                        imported_lengths = np.linalg.norm(
                            imported, axis=1, keepdims=True
                        )
                        dots = np.sum(
                            imported
                            / np.maximum(imported_lengths, 1e-10)
                            * expected_normals,
                            axis=1,
                        )
                        errors = np.degrees(np.arccos(np.clip(dots, -1, 1)))
                        normal_error = float(errors.max())
                        # Degenerate source faces can disrupt Blender's custom-normal fan encoding.
                        # Keep source geometry intact; report shading differences separately.
                        color = mesh.color_attributes.get("displayColor")
                        rgba = np.empty(len(color.data) * 4, np.float32)
                        color.data.foreach_get("color", rgba)
                        colors = arrays[f"{prefix}/colors"][:, :3]
                        if color.domain == "CORNER":
                            colors = colors[indices]
                        np.testing.assert_allclose(
                            rgba.reshape(-1, 4)[:, :3], colors, atol=2e-6
                        )
                    result.append(
                        {
                            "frame": frame,
                            "mesh": prefix,
                            "vertices": len(mesh.vertices),
                            "triangles": len(mesh.polygons),
                            "corners_with_normal_error_over_one_degree": int(
                                (errors > 1).sum()
                            )
                            if len(expected)
                            else 0,
                            "maximum_normal_error_degrees": normal_error
                            if len(expected)
                            else 0,
                        }
                    )
                    evaluated.to_mesh_clear()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--leaf-atlas",
        type=Path,
        default=ROOT
        / "Resources/DigitalAgricultureProject/Assets/GeneratedAssets/Materials/SorghumLeaves/LeafAtlas/atlas",
    )
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--reuse-scene", action="store_true")
    parser.add_argument(
        "--scene", type=Path, help="Edited .blend to open with --reuse-scene"
    )
    parser.add_argument(
        "--render-output",
        type=Path,
        help="New frame directory for a different Blender presentation",
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        help="Compare every frame instead of milestones",
    )
    parser.add_argument("--frame-start", type=int)
    parser.add_argument("--frame-end", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if any(v is not None and v <= 0 for v in (args.width, args.height, args.samples)):
        parser.error("Resolution and sample count must be positive")
    if (
        not args.reuse_scene
        and not (args.leaf_atlas / "sorghum_lsystem_leaf_variants_albedo.png").is_file()
    ):
        parser.error(
            "Leaf atlas albedo is missing; pass --leaf-atlas with the atlas directory"
        )
    source = args.manifest.resolve().parent
    output = (args.output or source / "blender").resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    start = args.frame_start if args.frame_start is not None else 1
    end = args.frame_end if args.frame_end is not None else len(manifest["frames"])
    if not 1 <= start <= end <= len(manifest["frames"]):
        parser.error("Render range must lie within the exported frame schedule")
    if args.scene and not args.reuse_scene:
        parser.error("--scene requires --reuse-scene")
    scene_path = (args.scene or output / "abc_growth.blend").resolve()
    if args.reuse_scene:
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
        scene = bpy.context.scene
        if scene.get("growth_manifest_sha256") != file_hash(args.manifest):
            raise ValueError(
                "This Blender scene belongs to another export; rebuild in a new output directory"
            )
        if scene.get("growth_cache_sha256") != file_hash(output / "growth.usdc"):
            raise ValueError("USD cache changed since scene creation")
        for cache in bpy.data.cache_files:
            if (
                Path(bpy.path.abspath(cache.filepath)).resolve()
                != output / "growth.usdc"
            ):
                raise ValueError("Scene references an unexpected USD cache")
        for sample in manifest["frames"]:
            if file_hash(source / sample["file"]) != sample["sha256"]:
                raise ValueError(f"Snapshot hash mismatch: {sample['file']}")
    else:
        if scene_path.exists():
            parser.error(
                "Scene already exists: use --reuse-scene to preserve edits, or choose a new --output"
            )
        args.width, args.height, args.samples = (
            args.width or 1280,
            args.height or 720,
            args.samples or 32,
        )
        build_cache(manifest, source, output / "growth.usdc")
        prepare_scene(manifest, source, output, args)
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    checks = validate_scene(manifest, source, args.validate_all)
    report = {
        "passed": True,
        "native_geometry": not manifest.get("synthetic_only", False),
        "blender": bpy.app.version_string,
        "validation_scope": "Geometry, transforms, UVs and colors; imported normals are diagnostic only",
        "source_manifest_sha256": file_hash(args.manifest),
        "samples_checked": checks,
        "cache_sha256": file_hash(output / "growth.usdc"),
        "texture_sha256": {
            p.name: file_hash(p) for p in (output / "textures").glob("*.png")
        },
    }
    (output / "validation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("GROWTH_CACHE_VALIDATED", flush=True)
    if args.render:
        scene = bpy.context.scene
        scene.frame_start, scene.frame_end = start, end
        if scene.render.fps != manifest["fps"] or scene.render.fps_base != 1:
            raise ValueError("Scene FPS must match the exported schedule")
        if args.width is not None:
            scene.render.resolution_x = args.width
        if args.height is not None:
            scene.render.resolution_y = args.height
        if args.samples is not None:
            scene.cycles.samples = args.samples
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        render_output = (args.render_output or output / "renders").resolve()
        render_output.mkdir(parents=True, exist_ok=True)
        binding = {
            "source_manifest_sha256": file_hash(args.manifest),
            "cache_sha256": file_hash(output / "growth.usdc"),
            "scene_sha256": file_hash(scene_path),
            "fps": manifest["fps"],
            "textures": {
                image.name: file_hash(bpy.path.abspath(image.filepath))
                for image in bpy.data.images
                if image.source == "FILE" and image.filepath and not image.packed_file
            },
            "resolution": [
                scene.render.resolution_x,
                scene.render.resolution_y,
                scene.render.resolution_percentage,
            ],
            "samples": scene.cycles.samples,
        }
        binding_path = render_output / "source.json"
        if binding_path.exists():
            if json.loads(binding_path.read_text()) != binding:
                raise ValueError(
                    "Frames belong to a different export/presentation; choose a new --render-output"
                )
        elif any(render_output.glob("growth_*.png")):
            raise ValueError(
                "Existing frames have no source record; choose a new --render-output"
            )
        binding_path.write_text(json.dumps(binding, indent=2), encoding="utf-8")
        scene.render.filepath = str(render_output / "growth_")
        bpy.ops.render.render(animation=True)
        print("GROWTH_RENDER_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
