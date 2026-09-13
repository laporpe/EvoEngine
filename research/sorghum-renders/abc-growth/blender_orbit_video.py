"""Render a slow orbit around a built field scene.

    blender --background --python blender_orbit_video.py -- <scene.blend> [out.mp4]

The camera circles the stand on a fixed ring, held on the canopy by a Track To
constraint, and the sun stays put so the light changes as the camera moves
rather than the other way round - which is what makes the canopy read as a
three-dimensional thing rather than a flat card.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FRAMES = 240                 # 10 s at 24 fps
FPS = 24
ELEVATION_DEG = 9.0          # low, like standing at the edge of the plot
RADIUS_SCALE = 0.82          # just outside the guard block corners
SAMPLES = 48                 # OptiX denoise makes 48 read like 96 in motion


def argv_after_ddash():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def plant_bounds():
    """Bounds of the plants only - the soil plane is enormous and would swamp it."""
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.name.startswith(("Soil", "Ground")):
            continue
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], p[i]) for i in range(3)))
            hi = Vector((max(hi[i], p[i]) for i in range(3)))
    return lo, hi


def main() -> None:
    argv = argv_after_ddash()
    if not argv:
        raise SystemExit("pass a .blend to orbit")
    blend = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else blend.with_name(blend.stem + "_orbit.mp4")
    frames = int(argv[2]) if len(argv) > 2 else FRAMES

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    lo, hi = plant_bounds()
    centre = (lo + hi) * 0.5
    footprint = max(hi.x - lo.x, hi.y - lo.y)
    height = hi.z - lo.z
    radius = footprint * RADIUS_SCALE
    print(f"[orbit] stand {footprint:.1f} m across, {height:.2f} m tall; "
          f"radius {radius:.1f} m")

    # Aim point sits inside the canopy, a little above half height, so the
    # horizon line stays below the panicles for the whole revolution.
    bpy.ops.object.empty_add(type="PLAIN_AXES",
                             location=(centre.x, centre.y, lo.z + height * 0.55))
    focus = bpy.context.active_object
    focus.name = "OrbitFocus"

    camera = bpy.context.scene.camera
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.active_object
        bpy.context.scene.camera = camera
    camera.data.lens = 30.0
    # Clear any rotation animation; the constraint owns aiming from here.
    camera.rotation_euler = (0.0, 0.0, 0.0)
    for c in list(camera.constraints):
        camera.constraints.remove(c)
    track = camera.constraints.new("TRACK_TO")
    track.target = focus
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, frames
    scene.render.fps = FPS

    lift = lo.z + height * 0.72 + radius * math.tan(math.radians(ELEVATION_DEG))
    camera.animation_data_clear()
    # Bezier easing on every key would make the orbit surge and stall between
    # them; linear keeps the angular rate constant. Blender 5 dropped
    # Action.fcurves for slotted actions, so set the default before inserting
    # rather than editing curves afterwards.
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except AttributeError:
        pass
    for frame in range(1, frames + 1):
        # Sample one extra step so frame 1 and frame FRAMES+1 would coincide:
        # the loop closes without a duplicated frame at the seam.
        angle = 2.0 * math.pi * (frame - 1) / frames
        camera.location = (centre.x + radius * math.cos(angle),
                           centre.y + radius * math.sin(angle),
                           lift)
        camera.keyframe_insert("location", frame=frame)


    view = scene.view_settings
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = SAMPLES
    # Keep focus on the stand as the camera circles: the ring radius is the
    # subject distance for the whole revolution.
    if camera.data.dof.use_dof:
        camera.data.dof.focus_distance = radius
    print(f"[orbit] {scene.render.engine} exposure {view.exposure:+.2f} "
          f"({view.view_transform} / {view.look})")
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.resolution_percentage = 100
    # This Blender build ships without the FFMPEG muxer - its file_format enum
    # is image formats only - so write a PNG sequence and let the project's
    # imageio-ffmpeg encode it, the same path the EvoEngine videos take.
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    frame_dir = out.with_suffix("")
    frame_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frame_dir / "f_")

    print(f"[orbit] rendering {frames} frames to {frame_dir.name}/")
    bpy.ops.render.render(animation=True)
    print(f"[orbit] frames in {frame_dir}")


main()
