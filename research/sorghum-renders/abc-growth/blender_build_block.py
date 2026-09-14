"""Build the BTx623 / Pawaga PARBAR block in Blender, with two publication cameras.

    blender --background --python blender_build_block.py -- [block.fbx] [out.blend] [key=value ...]

Keys: exposure=-3.5  samples=96  litter=400  guard=0  sun_el=74  sun_az=149

Reuses the field builder's materials, soil, sky and calibration, then adds what
this block has that the genotype stand does not: two genotypes labelled by row,
the PARBAR sensor rig (poles and three bars each, placed from the transforms
decoded out of the engine scene file), and two cameras:

  CamTopDown       nadir, orthographic, sized to the block plus a margin
  CamCrossSection  end view along the rows from the south, wide enough that no
                   plant is cut off at either edge or at the top

Both are framed from the block's measured extent rather than fixed numbers, so
a different layout or growth stage reframes itself.
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blender_build_field as field  # noqa: E402

EXPORT = HERE / "blender-export"
# Each camera is rendered at its own size; projections must use the same frame.
CAMERA_RES = {"CamTopDown": (1500, 2000), "CamCrossSection": (2400, 1100)}
SUN_DEFAULT_EL, SUN_DEFAULT_AZ = 74.0, 149.0        # 12:00 MST 2021-07-26, from the figure
POLE_GREY = (0.62, 0.63, 0.65, 1.0)
PANEL_GREY = (0.30, 0.31, 0.33, 1.0)


def engine_to_blender(v):
    """EvoEngine is Y-up with rows along z; Blender is Z-up. x stays, y = -z, z = y."""
    return Vector((v[0], -v[2], v[1]))


def build_parbar_rig(sidecar):
    """Poles and bars from parbar_transforms.json.

    Bar heights: the top bar is where the file puts it (2.28 m). The middle bar
    is repositioned by the engine at run time to two thirds of plant height and
    the stored transform is the pre-move one, so it is placed from the sidecar's
    measured mean height instead. The bottom bar stays at its stored ~0.1 m.
    """
    path = EXPORT / "parbar_transforms.json"
    if not path.is_file():
        print("[block] no parbar_transforms.json - rig skipped")
        return
    entries = json.loads(path.read_text())
    mean_h = sum(sidecar["mean_height_m"].values()) / max(1, len(sidecar["mean_height_m"]))

    pole_mat = bpy.data.materials.new("PoleSteel")
    pole_mat.use_nodes = True
    b = pole_mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = POLE_GREY
    b.inputs["Metallic"].default_value = 0.9
    b.inputs["Roughness"].default_value = 0.35
    panel_mat = bpy.data.materials.new("SensorPanel")
    panel_mat.use_nodes = True
    b = panel_mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = PANEL_GREY
    b.inputs["Roughness"].default_value = 0.6

    made = 0
    for e in entries:
        name = e["name"]
        pos = engine_to_blender(e["world_translation"])
        if not e["is_mesh"] and name.count("_") == 1:            # PARBAR_BTX / PARBAR_Pawaga roots
            bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=2.4,
                                                location=(pos.x, pos.y, 1.2))
            pole = bpy.context.active_object
            pole.name = f"{name}_Pole"
            pole.data.materials.append(pole_mat)
            made += 1
        elif e["is_mesh"]:
            M = e["world_matrix"]
            axis = engine_to_blender((M[0][0], M[1][0], M[2][0]))   # bar's long axis
            yaw = math.atan2(axis.y, axis.x)
            z = pos.z
            if "Middle" in name:
                z = mean_h * (2.0 / 3.0)
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(pos.x, pos.y, z))
            bar = bpy.context.active_object
            bar.name = name
            bar.scale = (1.05, 0.07, 0.03)
            bar.rotation_euler = (0.0, 0.0, yaw)
            bar.data.materials.append(pole_mat)
            # The sensor head: a small dark panel on the bar's upper face.
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(pos.x, pos.y, z + 0.03))
            head = bpy.context.active_object
            head.name = f"{name}_Head"
            head.scale = (0.22, 0.10, 0.025)
            head.rotation_euler = (0.0, 0.0, yaw)
            head.data.materials.append(panel_mat)
            made += 2
    print(f"[block] PARBAR rig: {made} objects (middle bars at {mean_h * 2 / 3:.2f} m)")


FLAG = {"BTX": (0.10, 0.36, 0.85, 1.0), "Pawaga": (0.85, 0.30, 0.08, 1.0)}   # blue / orange tape


def rows_from_plants(plants):
    """Per-row extent from the imported plant roots, named <geno>_LSystem_R<i>_C<j>."""
    import re
    rows = {}
    for p in plants:
        if p.parent is not None:
            continue
        m = re.match(r"(\w+)_LSystem_R(\d+)_C(\d+)", p.name)
        if not m:
            continue
        geno, i = m.group(1), int(m.group(2))
        r = rows.setdefault(i, {"genotype": geno, "xs": [], "ys": []})
        r["xs"].append(p.matrix_world.translation.x)
        r["ys"].append(p.matrix_world.translation.y)
    return {i: {"genotype": r["genotype"], "x_min": min(r["xs"]), "x_max": max(r["xs"]),
                "y": sum(r["ys"]) / len(r["ys"])} for i, r in rows.items()}


def build_row_stakes(rows, lo):
    """A plot stake with a flag at the south end of every row.

    This is how a trial is actually marked in the field, and it is the only
    honest way to make the genotype boundary legible end-on: seven rows of
    sorghum look alike, but seven flags in two colours do not.
    """
    stake_mat = bpy.data.materials.new("StakeWood")
    stake_mat.use_nodes = True
    stake_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.42, 0.25, 1)
    flag_mats = {}
    for geno, colour in FLAG.items():
        m = bpy.data.materials.new(f"Flag_{geno}")
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = colour
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
        flag_mats[geno] = m
    for i, r in sorted(rows.items()):
        x, y = r["x_min"] - 0.45, r["y"]
        bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.75, location=(x, y, lo.z + 0.375))
        stake = bpy.context.active_object
        stake.name = f"Stake_R{i}_{r['genotype']}"
        stake.data.materials.append(stake_mat)
        # Vertical tape facing the end-view camera (normal along X): rotating the
        # plane about Y sends its local X to world Z, so scale (height, width, 1).
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=(x - 0.006, y + 0.08, lo.z + 0.66))
        flag = bpy.context.active_object
        flag.name = f"Flag_R{i}_{r['genotype']}"
        flag.rotation_euler = (0.0, math.radians(90.0), 0.0)
        flag.scale = (0.09, 0.16, 1.0)
        flag.data.materials.append(flag_mats[r["genotype"]])
        # Horizontal tag on the stake top so the nadir view reads the colour too.
        bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.01, location=(x, y, lo.z + 0.755))
        tag = bpy.context.active_object
        tag.name = f"Tag_R{i}_{r['genotype']}"
        tag.data.materials.append(flag_mats[r["genotype"]])
    print(f"[block] row stakes: {len(rows)} ({', '.join(r['genotype'] for _, r in sorted(rows.items()))})")


def write_row_screen_positions(rows, cams, lo, out_json):
    """Where each row's base lands in each camera, for the annotation pass."""
    from bpy_extras.object_utils import world_to_camera_view
    scene = bpy.context.scene
    # The cameras were just created and moved; their world matrices are not
    # valid until the dependency graph runs, and projecting through a stale
    # identity matrix puts every row a hundred frames off-screen.
    bpy.context.view_layer.update()
    result = {}
    for cam in cams:
        # world_to_camera_view derives the frame from the scene resolution, so
        # set it to what this camera is actually rendered at.
        if cam.name in CAMERA_RES:
            scene.render.resolution_x, scene.render.resolution_y = CAMERA_RES[cam.name]
        entry = {}
        for i, r in sorted(rows.items()):
            base = Vector(((r["x_min"] + r["x_max"]) * 0.5, r["y"], lo.z))
            near = Vector((r["x_min"], r["y"], lo.z))
            u, v, _ = world_to_camera_view(scene, cam, base)
            un, vn, _ = world_to_camera_view(scene, cam, near)
            entry[str(i)] = {"genotype": r["genotype"], "u": u, "v": v, "u_near": un, "v_near": vn}
        result[cam.name] = entry
    Path(out_json).write_text(json.dumps(result, indent=1))
    print(f"[block] wrote row screen positions -> {Path(out_json).name}")


def cameras(lo, hi, sidecar, opts):
    """Two cameras framed from the measured extent, each with head room."""
    centre = (lo + hi) * 0.5
    span_x, span_y, height = hi.x - lo.x, hi.y - lo.y, hi.z - lo.z
    scene = bpy.context.scene

    # (a) nadir, orthographic. Ortho scale is the width of the view in metres;
    # the longer block axis plus 12 % clears the leaf tips at both ends.
    bpy.ops.object.camera_add(location=(centre.x, centre.y, hi.z + 12.0))
    top = bpy.context.active_object
    top.name = "CamTopDown"
    top.data.type = "ORTHO"
    # Rendered portrait (1500x2000): ortho_scale spans the taller frame axis,
    # which holds the 7 rows; screen-up = -Y puts Pawaga (engine z 4-6) at the
    # top and BTx623 at the bottom, as in the published panel.
    top.data.ortho_scale = span_y * 1.10
    top.rotation_euler = (0.0, 0.0, math.radians(180.0))
    top.data.dof.use_dof = False

    # (b) end view down the rows from the south (-X), looking +X. Fit all rows
    # across the frame and the full plant height plus headroom vertically, by
    # solving distance from the wider of the two required half-angles.
    bpy.ops.object.camera_add()
    cross = bpy.context.active_object
    cross.name = "CamCrossSection"
    cross.data.lens = 50.0
    cross.data.sensor_width = 36.0
    aspect = float(opts.get("cross_w", 2400)) / float(opts.get("cross_h", 1100))
    pole_top = 2.45                                            # PARBAR top bar + head
    half_w = span_y * 0.5 * 1.06
    half_h = max(height, pole_top) * 0.5 * 1.12
    fov_h = 2.0 * math.atan(36.0 / (2.0 * cross.data.lens))
    fov_v = 2.0 * math.atan(math.tan(fov_h / 2.0) / aspect)
    dist = max(half_w / math.tan(fov_h / 2.0), half_h / math.tan(fov_v / 2.0))
    # Aim at the middle of what must fit (canopy and poles), from a little
    # above canopy mid-height so the foreground soil does not dominate.
    fit_mid = lo.z + max(height, pole_top) * 0.5
    cross.location = (lo.x - dist, centre.y, lo.z + height * 0.60)
    target = Vector((centre.x, centre.y, fit_mid))
    cross.rotation_euler = (target - cross.location).to_track_quat("-Z", "Y").to_euler()
    cross.data.dof.use_dof = True
    cross.data.dof.focus_distance = (target - cross.location).length
    cross.data.dof.aperture_fstop = 5.6
    print(f"[block] cross-section camera {dist:.1f} m south of the block, "
          f"{span_y:.1f} m of rows across, {height:.2f} m of canopy")
    scene.camera = top
    return top, cross


def main() -> None:
    positional, opts = field.parse_argv()
    # parse_argv fills in the field builder's defaults (guard=1, litter=700);
    # this block is the measured plot and should render alone unless asked.
    explicit = {a.split("=", 1)[0] for a in sys.argv if "=" in a}
    if "guard" not in explicit:
        opts["guard"] = 0
    if "litter" not in explicit:
        opts["litter"] = 150
    if "exposure" not in explicit:
        opts["exposure"] = -3.5
    opts["litter"], opts["guard"] = int(opts["litter"]), int(opts["guard"])
    source = Path(positional[0]) if positional else EXPORT / "btx_block_small.fbx"
    out = Path(positional[1]) if len(positional) > 1 else source.with_suffix(".blend")
    sidecar = json.loads(source.with_suffix(".json").read_text())
    rng = random.Random(field.SEED)

    field.SUN_ELEVATION_DEG = float(opts.get("sun_el", SUN_DEFAULT_EL))
    field.SUN_AZIMUTH_DEG = float(opts.get("sun_az", SUN_DEFAULT_AZ))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    print(f"[block] importing {source.name} ({source.stat().st_size / 1e6:.0f} MB)")
    plants = field.import_stand(source)
    lo, hi = field.bounds(plants)
    centre = (lo + hi) * 0.5
    extent = max(hi.x - lo.x, hi.y - lo.y)
    print(f"[block] {len([p for p in plants if p.type == 'MESH'])} organs, block "
          f"{hi.x - lo.x:.1f} x {hi.y - lo.y:.1f} m, {hi.z - lo.z:.2f} m tall")

    field.fix_culm_normals(plants)
    field.restyle_materials(plants)
    if opts["guard"]:
        field.add_guard_rows(rng, plants, lo, hi, opts["guard"])
    field.build_soil(centre, lo, extent * 90.0)
    field.scatter_litter(rng, lo, hi, opts["litter"])
    field.build_sky(opts)
    build_parbar_rig(sidecar)
    rows = rows_from_plants(plants)
    build_row_stakes(rows, lo)
    top, cross = cameras(lo, hi, sidecar, opts)
    field.configure_render(bpy.context.scene, opts)
    write_row_screen_positions(rows, (top, cross), lo, out.with_name(out.stem + "_rows.json"))

    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"[block] saved {out.name} - {len(bpy.data.objects)} objects")


if __name__ == "__main__":
    main()
