"""One BTx623 beside one Pawaga: a comparison portrait, built for Cycles.

    blender --background --python blender_build_pair.py -- [pair.fbx] [out.blend] [key=value ...]

Keys: exposure=-3.5  samples=192  sun_el=42  sun_az=205  device=CUDA|OPTIX|CPU

The block renders show the two genotypes as populations; this shows them as
individuals, so everything is arranged to make architecture legible: a raking
side sun so leaf angles and culm lines read as form rather than flat colour,
a lens long enough to avoid stretching the outer plant, and the camera at
standing eye height - the way a person compares two plants in a field.

Device defaults to CUDA rather than OptiX: a second OptiX process cannot start
while another Cycles render holds the GPU, and CUDA takes a separate path.
"""
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


def camera_for_pair(lo, hi, aspect):
    """Frame both plants with the longer lens, solving distance from the
    wider of the horizontal and vertical requirements."""
    centre = (lo + hi) * 0.5
    span_y, height = hi.y - lo.y, hi.z - lo.z
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.name = "CamPair"
    cam.data.lens = 70.0
    cam.data.sensor_width = 36.0
    half_w = span_y * 0.5 * 1.06
    half_h = height * 0.5 * 1.12
    fov_h = 2.0 * math.atan(36.0 / (2.0 * cam.data.lens))
    fov_v = 2.0 * math.atan(math.tan(fov_h / 2.0) / aspect)
    dist = max(half_w / math.tan(fov_h / 2.0), half_h / math.tan(fov_v / 2.0))
    # Slightly to the south-west so the two culms do not line up, and at
    # standing eye height looking a touch downward.
    cam.location = (lo.x - dist * 0.97, centre.y - dist * 0.22, lo.z + 1.25)
    target = Vector((centre.x, centre.y, lo.z + height * 0.48))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (target - cam.location).length
    cam.data.dof.aperture_fstop = 6.3
    bpy.context.scene.camera = cam
    print(f"[pair] camera {dist:.1f} m off, {span_y:.2f} m between plants, "
          f"{height:.2f} m tall")
    return cam


def main() -> None:
    positional, opts = field.parse_argv()
    explicit = {a.split("=", 1)[0] for a in sys.argv if "=" in a}
    for key, value in (("guard", 0), ("litter", 25), ("exposure", -3.75), ("samples", 192)):
        if key not in explicit:
            opts[key] = value
    device = str(opts.get("device", "CUDA")).upper()
    source = Path(positional[0]) if positional else EXPORT / "btx_block_pair.fbx"
    out = Path(positional[1]) if len(positional) > 1 else source.with_suffix(".blend")
    rng = random.Random(field.SEED)

    # A raking sun from the south-south-west: azimuth is measured the way the
    # sky node does, and this puts light across the plants from the camera's
    # left so every leaf shows a lit face and a shaded one.
    field.SUN_ELEVATION_DEG = float(opts.get("sun_el", 42.0))
    field.SUN_AZIMUTH_DEG = float(opts.get("sun_az", 205.0))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    print(f"[pair] importing {source.name}")
    plants = field.import_stand(source)
    lo, hi = field.bounds(plants)
    centre = (lo + hi) * 0.5
    extent = max(hi.x - lo.x, hi.y - lo.y)
    for root in (p for p in plants if p.parent is None):
        print(f"[pair]   {root.name}")

    field.fix_culm_normals(plants)          # harmless on a fixed export; needed on older ones
    field.restyle_materials(plants)
    field.build_soil(centre, lo, extent * 120.0)
    field.scatter_litter(rng, lo, hi, int(opts["litter"]))
    field.build_sky(opts)
    camera_for_pair(lo, hi, 3.0 / 2.0)
    field.configure_render(bpy.context.scene, opts)

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 2400, 1600
    if scene.render.engine == "CYCLES":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        if device in ("CUDA", "OPTIX"):
            try:
                prefs.compute_device_type = device
                prefs.get_devices()
                for d in prefs.devices:
                    d.use = d.type == device
                scene.cycles.device = "GPU"
            except TypeError:
                scene.cycles.device = "CPU"
        else:
            scene.cycles.device = "CPU"
        # OIDN runs on the CPU and does not need the OptiX context.
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        print(f"[pair] cycles device {scene.cycles.device} ({device}), "
              f"{scene.cycles.samples} samples, OIDN")

    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"[pair] saved {out.name} - {len(bpy.data.objects)} objects")


if __name__ == "__main__":
    main()
