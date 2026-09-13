"""Render one frame of a built scene, for calibration and stills.

    blender --background --python blender_render_still.py -- <scene.blend> <out.png> [key=value ...]

Keys: exposure=-6.0  samples=48  scale=50  frame=1

`scale` is the resolution percentage: 25-50 is enough to judge exposure and
colour, and it keeps a calibration round trip to well under a minute.
"""
import sys
from pathlib import Path

import bpy


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [a for a in argv if "=" not in a]
    opts = {"exposure": None, "samples": None, "scale": 100, "frame": 1}
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            opts[k] = v
    if len(positional) < 2:
        raise SystemExit("usage: <scene.blend> <out.png> [exposure=] [samples=] [scale=]")
    blend, out = Path(positional[0]), Path(positional[1])

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    if opts["exposure"] is not None:
        scene.view_settings.exposure = float(opts["exposure"])
    if opts["samples"] is not None and scene.render.engine == "CYCLES":
        scene.cycles.samples = int(opts["samples"])
    scene.render.resolution_percentage = int(opts["scale"])
    scene.frame_set(int(opts["frame"]))
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(out)
    print(f"[still] {scene.render.engine} exposure {scene.view_settings.exposure:+.2f} "
          f"scale {opts['scale']}% -> {out.name}")
    bpy.ops.render.render(write_still=True)
    print(f"[still] wrote {out}")


main()
