"""Open an exported sorghum stand in Blender, framed and lit.

Run by Blender, not by the project's Python:

    blender --python blender_open_export.py -- <path to .fbx or .obj>

Defaults to the newest file in blender-export/ when no path is given. Starts from
an empty scene (no default cube, lamp or camera), imports the stand, gives it a
sun and a ground plane, and frames the camera on the actual bounds so the plots
fill the view instead of sitting as specks at the origin.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

EXPORT_DIR = Path(r"C:\Users\Brenda\Desktop\mf\claude evo engine\blender-export")


def chosen_file() -> Path:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if argv:
        return Path(argv[0])
    candidates = sorted(
        [p for p in EXPORT_DIR.glob("*") if p.suffix.lower() in (".fbx", ".obj")],
        key=lambda p: (p.suffix.lower() != ".fbx", -p.stat().st_mtime))
    if not candidates:
        raise SystemExit(f"no .fbx or .obj found in {EXPORT_DIR}")
    return candidates[0]


def import_stand(path: Path):
    before = set(bpy.data.objects)
    if path.suffix.lower() == ".fbx":
        # The mesh data is already in metres, but the FBX carries the format's
        # centimetre convention, so Blender scales every root down by 100 and a
        # 2 m plant arrives 2 cm tall. Cancel it on import rather than afterwards,
        # so object positions and scales stay consistent with each other.
        bpy.ops.import_scene.fbx(filepath=str(path), global_scale=100.0)
    else:
        # Blender 4.x+ renamed the OBJ operator; fall back for older builds.
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(path))
        else:
            bpy.ops.import_scene.obj(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def world_bounds(objects):
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    found = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], p[i]) for i in range(3)))
            hi = Vector((max(hi[i], p[i]) for i in range(3)))
            found = True
    if not found:
        raise SystemExit("the import produced no mesh objects")
    return lo, hi


def main() -> None:
    path = chosen_file()
    print(f"[sorghum] importing {path.name} ({path.stat().st_size / 1e6:.0f} MB)")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported = import_stand(path)
    meshes = [o for o in imported if o.type == "MESH"]
    tris = sum(len(o.data.loop_triangles) if o.data.loop_triangles else len(o.data.polygons)
               for o in meshes)
    print(f"[sorghum] {len(meshes)} mesh objects, ~{tris:,} faces")

    lo, hi = world_bounds(imported)
    centre = (lo + hi) * 0.5
    size = max((hi - lo).x, (hi - lo).y, (hi - lo).z)
    print(f"[sorghum] bounds {tuple(round(v, 2) for v in lo)} to "
          f"{tuple(round(v, 2) for v in hi)}  (largest span {size:.2f})")

    # Ground, sized off the stand so it reads as a field rather than a backdrop.
    bpy.ops.mesh.primitive_plane_add(size=size * 6.0, location=(centre.x, centre.y, lo.z))
    ground = bpy.context.active_object
    ground.name = "Ground"
    soil = bpy.data.materials.new("Soil")
    soil.use_nodes = True
    soil.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        0.35, 0.19, 0.11, 1.0)
    soil.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
    ground.data.materials.append(soil)

    # Sun high and to one side, matching the afternoon light the renders used.
    bpy.ops.object.light_add(type="SUN", location=(centre.x + size, centre.y - size,
                                                   lo.z + size * 2.0))
    sun = bpy.context.active_object
    sun.data.energy = 4.0
    sun.data.angle = math.radians(1.5)          # a tight disc casts a crisp shadow
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(35))

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.6, 0.85, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    bpy.context.scene.world = world

    # Camera framed on the bounds, low and to the side like the video renders.
    distance = size * 1.9
    bpy.ops.object.camera_add(location=(centre.x + distance * 0.85,
                                        centre.y - distance * 0.85,
                                        lo.z + size * 0.55))
    camera = bpy.context.active_object
    direction = centre - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera

    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT" \
        if "BLENDER_EEVEE_NEXT" in bpy.context.scene.render.bl_rna.properties["engine"].enum_items \
        else "BLENDER_EEVEE"
    bpy.context.scene.render.film_transparent = False

    # Material preview in every 3D viewport, so the leaf textures are visible
    # immediately rather than after hunting through the shading dropdown.
    screen = getattr(bpy.context, "screen", None)
    for area in (screen.areas if screen else []):
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
                    space.clip_end = max(1000.0, size * 40.0)

    blend_path = path.with_suffix(".blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"[sorghum] saved {blend_path.name} - ready")


main()
