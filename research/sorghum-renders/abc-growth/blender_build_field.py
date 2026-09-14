"""Build a photographic field scene in Blender from an exported sorghum stand.

    blender --background --python blender_build_field.py -- <stand.fbx> [out.blend] [key=value ...]

Keys: engine=CYCLES|EEVEE  samples=96  exposure=-6.0  guard=1  litter=700  dof=1  volume=0

The first version of this scene lit the stand with a dim lamp under a bright
sky and came out flat: darkest pixels at 59/255 where the field photographs
reach 6-15, a 4x dynamic range where the photographs show 16-38x, and a sky that
was near white. Sunlight is 5-10x brighter than the sky it comes with, and that
ratio is what puts the blue in the sky and the black in the shadows. So this
version lights the scene from the physical sky's own sun disc, with nothing
else, and exposes for the sunlit foliage.

Colours are taken from the photographs: soil rust-red, panicles pale straw (not
the engine's dark olive), leaves olive rather than neon, culms with the waxy
blue-green bloom sorghum carries.
"""
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# ----------------------------------------------------------------- targets ---
SOIL_BASE = (0.310, 0.105, 0.048, 1.0)      # rust, IMG_4163 sunlit alley
SOIL_DARK = (0.120, 0.045, 0.025, 1.0)      # damp clods and shadow
LITTER = (0.300, 0.215, 0.105, 1.0)         # dried blades on the ground, IMG_4137
PANICLE = (0.560, 0.500, 0.290, 1.0)        # pale straw, IMG_4163
CULM_BLOOM = (0.480, 0.560, 0.430, 1.0)     # glaucous wax on stems, IMG_4171
SUN_ELEVATION_DEG = 52.0                    # August, late morning, Maricopa
SUN_AZIMUTH_DEG = 135.0
SEED = 20260913

DEFAULTS = {"engine": "CYCLES", "samples": 96, "exposure": -3.75, "guard": 1,
            "litter": 700, "dof": 1, "volume": 0,
            # Sun:sky ratio. Exposure alone cannot hit both a bright canopy and a
            # deep sky - AgX desaturates the sky as it brightens - so the disc is
            # pushed up and the dome pulled down, holding the sun roughly constant
            # while the sky sits ~0.6 stops darker and keeps its blue.
            "sun": 1.5, "skystr": 0.65, "ozone": 2.5}


def parse_argv():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [a for a in argv if "=" not in a]
    opts = dict(DEFAULTS)
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            opts[k] = type(DEFAULTS.get(k, v))(v) if k in DEFAULTS else v
    return positional, opts


def import_stand(path: Path):
    before = set(bpy.data.objects)
    # Mesh is metric already; FBX's centimetre convention would shrink roots 100x.
    bpy.ops.import_scene.fbx(filepath=str(path), global_scale=100.0)
    return [o for o in bpy.data.objects if o not in before]


def bounds(objects):
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], p[i]) for i in range(3)))
            hi = Vector((max(hi[i], p[i]) for i in range(3)))
    return lo, hi


def find_node(tree_owner, bl_idname):
    return next((n for n in tree_owner.node_tree.nodes if n.bl_idname == bl_idname), None)


def image_node_feeding(mat, socket):
    """The image texture wired into `socket`, if any."""
    for link in mat.node_tree.links:
        if link.to_socket == socket and link.from_node.bl_idname == "ShaderNodeTexImage":
            return link.from_node
    return None


# --------------------------------------------------------------- materials ---
def restyle_leaf(mat):
    """Waxy, translucent, olive - the three things a sorghum blade is in sun.

    Backlight is what a canopy photograph is made of: leaves between the camera
    and the sun glow. A Principled BSDF alone cannot do that, so the diffuse
    lobe is mixed with a Translucent BSDF fed by the same albedo. The texture is
    pulled slightly toward olive and desaturated; the atlas reads neon next to
    the photographs.
    """
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    out = find_node(mat, "ShaderNodeOutputMaterial")
    if not bsdf or not out:
        return False
    albedo = image_node_feeding(mat, bsdf.inputs["Base Color"])

    grade = nodes.new("ShaderNodeHueSaturation")
    grade.inputs["Saturation"].default_value = 0.82
    grade.inputs["Value"].default_value = 0.92
    if albedo:
        links.new(albedo.outputs["Color"], grade.inputs["Color"])
    else:
        grade.inputs["Color"].default_value = (0.20, 0.30, 0.10, 1.0)
    links.new(grade.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = 0.38
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.55
    if "Coat Weight" in bsdf.inputs:                 # the cuticle sheen
        bsdf.inputs["Coat Weight"].default_value = 0.15
        bsdf.inputs["Coat Roughness"].default_value = 0.25

    trans = nodes.new("ShaderNodeBsdfTranslucent")
    tint = nodes.new("ShaderNodeHueSaturation")
    tint.inputs["Hue"].default_value = 0.52            # a touch yellower through the blade
    tint.inputs["Saturation"].default_value = 1.05
    tint.inputs["Value"].default_value = 1.10
    links.new(grade.outputs["Color"], tint.inputs["Color"])
    links.new(tint.outputs["Color"], trans.inputs["Color"])

    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.34
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    links.new(trans.outputs["BSDF"], mix.inputs[2])
    for link in list(links):
        if link.to_socket == out.inputs["Surface"]:
            links.remove(link)
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return True


def restyle_culm(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return False
    albedo = image_node_feeding(mat, bsdf.inputs["Base Color"])
    bloom = nodes.new("ShaderNodeMix")
    bloom.data_type = "RGBA"
    bloom.inputs["Factor"].default_value = 0.45
    bloom.inputs[7].default_value = CULM_BLOOM                       # B colour
    if albedo:
        links.new(albedo.outputs["Color"], bloom.inputs[6])           # A colour
    else:
        bloom.inputs[6].default_value = (0.25, 0.32, 0.14, 1.0)
    links.new(bloom.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.4
    return True


def restyle_panicle(mat):
    """Straw colour with the granular relief of packed spikelets."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return False
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0
    noise.inputs["Detail"].default_value = 4.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.42, 0.36, 0.20, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = PANICLE
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.002
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.8
    return True


def strip_import_artifacts(mat):
    """Undo two things the FBX importer wires that are wrong for these plants.

    It connects an all-black map to Roughness - a perfect mirror, which in
    Cycles reflects the dark ground and renders culms near black - and it feeds
    the albedo into Alpha, making organs partly transparent. Any explicit
    roughness or alpha set on the BSDF is ignored while those links exist, so
    they have to go first. The engine geometry already defines every organ's
    outline; alpha has no job here.
    """
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return
    links = mat.node_tree.links
    for name in ("Roughness", "Alpha"):
        for link in [l for l in links if l.to_socket == bsdf.inputs[name]]:
            links.remove(link)
    bsdf.inputs["Alpha"].default_value = 1.0


def fix_culm_normals(objects):
    """Recompute internode normals; the exported ones point into the stem.

    Cycles shades a diffuse surface whose normal faces away from the light as
    black, so every culm rendered as a black stick regardless of material. The
    engine's exporter aligns face winding to vertex normals for leaves only
    (`align_leaf_faces` in Prefab.cpp), never for internodes, so their custom
    split normals arrive inverted. Clearing them and recalculating outward is the
    Blender-side fix; the exporter is the place to fix it properly.
    """
    import bmesh
    meshes = {o.data for o in objects
              if o.type == "MESH" and o.name.startswith("Sorghum Internodes")}
    fixed = 0
    for me in meshes:
        owner = next(o for o in objects if o.type == "MESH" and o.data == me)
        with bpy.context.temp_override(object=owner, active_object=owner,
                                       selected_objects=[owner],
                                       selected_editable_objects=[owner]):
            try:
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
            except RuntimeError:
                pass
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
        fixed += 1
    print(f"[field] culm normals recalculated on {fixed} meshes")


def restyle_materials(objects):
    done, counts = set(), {"leaf": 0, "culm": 0, "panicle": 0}
    for obj in objects:
        if obj.type != "MESH":
            continue
        kind = obj.name.split(".")[0]
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes or mat.name in done:
                continue
            done.add(mat.name)
            strip_import_artifacts(mat)
            if kind.endswith("Panicle"):
                counts["panicle"] += restyle_panicle(mat)
            elif kind.endswith("Leaves"):
                counts["leaf"] += restyle_leaf(mat)
            else:
                counts["culm"] += restyle_culm(mat)
    print(f"[field] materials: {counts}")


# ------------------------------------------------------------------- scene ---
def build_soil(centre, lo, extent):
    bpy.ops.mesh.primitive_plane_add(size=extent, location=(centre.x, centre.y, lo.z))
    soil = bpy.context.active_object
    soil.name = "Soil"
    mat = bpy.data.materials.new("DesertSoil")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.97
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.15

    coords = nodes.new("ShaderNodeTexCoord")
    patch = nodes.new("ShaderNodeTexNoise")       # damp / dry patches
    patch.inputs["Scale"].default_value = 2.8
    patch.inputs["Detail"].default_value = 7.0
    clods = nodes.new("ShaderNodeTexNoise")       # tilled relief
    clods.inputs["Scale"].default_value = 45.0
    clods.inputs["Detail"].default_value = 9.0
    clods.inputs["Roughness"].default_value = 0.7
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = SOIL_DARK
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = SOIL_BASE
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.03
    links.new(coords.outputs["Object"], patch.inputs["Vector"])
    links.new(coords.outputs["Object"], clods.inputs["Vector"])
    links.new(patch.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(clods.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    soil.data.materials.append(mat)
    return soil


def scatter_litter(rng, lo, hi, count):
    """Dry blades on the ground. IMG_4137 shows the alley floor half covered.

    One small mesh, many linked instances - cheap, and it breaks the flat
    soil far more than any texture does because it casts real shadows.
    """
    if count <= 0:
        return
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, -100))
    blade = bpy.context.active_object
    blade.name = "LitterBlade"
    mat = bpy.data.materials.new("Litter")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = LITTER
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    blade.data.materials.append(mat)
    blade.hide_render = True
    blade.hide_viewport = True

    margin = 1.2
    for _ in range(count):
        inst = blade.copy()
        inst.hide_render = False
        inst.hide_viewport = False
        inst.location = (rng.uniform(lo.x - margin, hi.x + margin),
                         rng.uniform(lo.y - margin, hi.y + margin),
                         lo.z + 0.004)
        inst.rotation_euler = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15),
                               rng.uniform(0.0, math.tau))
        inst.scale = (0.14 * rng.uniform(0.6, 1.5), 0.028 * rng.uniform(0.7, 1.3), 1.0)
        bpy.context.collection.objects.link(inst)
    print(f"[field] litter: {count} blades")


def build_sky(opts):
    """The physical sky lights everything, sun disc included.

    Sun intensity is left at 1.0 and the *film* is exposed instead: that is what
    keeps the sun:sky ratio physical. A separate lamp always ends up either too
    weak (flat, grey sky) or fighting the sky's own disc.
    """
    world = bpy.data.worlds.new("DesertSky")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes["Background"]
    sky = nodes.new("ShaderNodeTexSky")
    available = {i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items}
    for candidate in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        if candidate in available:
            sky.sky_type = candidate
            break
    wanted = {"sun_disc": True, "sun_elevation": math.radians(SUN_ELEVATION_DEG),
              "sun_rotation": math.radians(SUN_AZIMUTH_DEG), "altitude": 361.0,
              "air_density": 1.0, "ozone_density": float(opts["ozone"]), "sun_intensity": float(opts["sun"]),
              "sun_size": math.radians(0.53), "turbidity": 2.2}
    applied = []
    for name, value in wanted.items():
        if hasattr(sky, name):
            try:
                setattr(sky, name, value)
                applied.append(name)
            except (AttributeError, TypeError):
                pass
    links.new(sky.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = float(opts["skystr"])

    if opts["volume"]:
        # Aerial perspective: a whisper of scatter so the far guard rows recede.
        scatter = nodes.new("ShaderNodeVolumeScatter")
        scatter.inputs["Density"].default_value = 0.0025
        out = find_node(world, "ShaderNodeOutputWorld")
        links.new(scatter.outputs["Volume"], out.inputs["Volume"])
    bpy.context.scene.world = world
    print(f"[field] sky {sky.sky_type}: {', '.join(applied)}")


def add_guard_rows(rng, plants, lo, hi, rings):
    """Ring the measured plots with neighbours - and make them not clones.

    Identical copies on a grid are the single most obvious tell in an orbit.
    Each guard plant gets its own yaw, a little scale, and a little jitter; the
    mesh data stays shared so it costs nothing.
    """
    if rings <= 0:
        return []
    span_x, span_y = hi.x - lo.x, hi.y - lo.y
    made = []
    roots = [p for p in plants if p.parent is None]
    for ix in range(-rings, rings + 1):
        for iy in range(-rings, rings + 1):
            if ix == 0 and iy == 0:
                continue
            for plant in roots:
                copy = plant.copy()
                copy.location = plant.location + Vector((
                    ix * span_x + rng.uniform(-0.09, 0.09),
                    iy * span_y + rng.uniform(-0.09, 0.09), 0.0))
                copy.rotation_euler = (plant.rotation_euler.x, plant.rotation_euler.y,
                                       plant.rotation_euler.z + rng.uniform(0, math.tau))
                copy.scale = Vector(plant.scale) * rng.uniform(0.92, 1.08)
                bpy.context.collection.objects.link(copy)
                for child in plant.children:
                    child_copy = child.copy()
                    child_copy.parent = copy
                    bpy.context.collection.objects.link(child_copy)
                    made.append(child_copy)
                made.append(copy)
    print(f"[field] guard rows: {(2 * rings + 1) ** 2 - 1} plots, {len(made)} linked objects, "
          f"each plant with its own yaw and scale")
    return made


def build_camera(lo, hi, centre, extent, opts):
    height = hi.z - lo.z
    bpy.ops.object.camera_add(location=(lo.x - extent * 0.30, lo.y - extent * 0.16,
                                        lo.z + 1.30))
    camera = bpy.context.active_object
    camera.data.lens = 35.0
    camera.data.sensor_width = 36.0
    target = Vector((centre.x, centre.y, lo.z + height * 0.70))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    if opts["dof"]:
        camera.data.dof.use_dof = True
        camera.data.dof.focus_distance = (target - camera.location).length
        camera.data.dof.aperture_fstop = 4.0
    bpy.context.scene.camera = camera
    return camera


def configure_render(scene, opts):
    if str(opts["engine"]).upper() == "CYCLES":
        scene.render.engine = "CYCLES"
        cycles = scene.cycles
        cycles.samples = int(opts["samples"])
        cycles.use_adaptive_sampling = True
        cycles.adaptive_threshold = 0.02
        cycles.max_bounces = 8
        cycles.diffuse_bounces = 4
        cycles.glossy_bounces = 4
        cycles.transmission_bounces = 4
        cycles.use_denoising = True
        try:
            cycles.denoiser = "OPTIX"
        except TypeError:
            cycles.denoiser = "OPENIMAGEDENOISE"
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for device_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = device_type
                prefs.get_devices()
                if any(d.type == device_type for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == device_type
                    cycles.device = "GPU"
                    print(f"[field] cycles on {device_type}: "
                          f"{[d.name for d in prefs.devices if d.use]}")
                    break
            except TypeError:
                continue
    else:
        engines = scene.render.bl_rna.properties["engine"].enum_items
        scene.render.engine = ("BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines
                               else "BLENDER_EEVEE")
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.resolution_percentage = 100

    view = scene.view_settings
    for transform in ("AgX", "Filmic", "Standard"):
        try:
            view.view_transform = transform
            break
        except TypeError:
            continue
    view.exposure = float(opts["exposure"])
    for look in ("AgX - Punchy", "Punchy", "AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            view.look = look
            break
        except TypeError:
            continue
    print(f"[field] {scene.render.engine}, {view.view_transform} / {view.look}, "
          f"exposure {view.exposure:+.2f}")


def main() -> None:
    positional, opts = parse_argv()
    source = Path(positional[0]) if positional else Path(
        r"C:\Users\Brenda\Desktop\mf\claude evo engine\blender-export\sorghum_nights_current.fbx")
    out = Path(positional[1]) if len(positional) > 1 else source.with_name(
        source.stem + "_field.blend")
    rng = random.Random(SEED)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    print(f"[field] importing {source.name}  opts={opts}")
    plants = import_stand(source)
    lo, hi = bounds(plants)
    centre = (lo + hi) * 0.5
    extent = max(hi.x - lo.x, hi.y - lo.y)
    print(f"[field] stand {extent:.2f} m across, {hi.z - lo.z:.2f} m tall")

    fix_culm_normals(plants)
    restyle_materials(plants)
    rings = int(opts["guard"])
    add_guard_rows(rng, plants, lo, hi, rings)
    build_soil(centre, lo, extent * 90.0)
    span = Vector((hi.x - lo.x, hi.y - lo.y, 0))
    scatter_litter(rng, lo - span * rings, hi + span * rings, int(opts["litter"]))
    build_sky(opts)
    build_camera(lo, hi, centre, extent, opts)
    configure_render(bpy.context.scene, opts)

    screen = getattr(bpy.context, "screen", None)
    for area in (screen.areas if screen else []):
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "RENDERED"
                    for flag in ("use_scene_world", "use_scene_lights",
                                 "use_scene_world_render", "use_scene_lights_render"):
                        if hasattr(space.shading, flag):
                            setattr(space.shading, flag, True)
                    space.clip_end = max(2000.0, extent * 60.0)

    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"[field] saved {out.name} - {len(bpy.data.objects)} objects")


if __name__ == "__main__":
    main()
