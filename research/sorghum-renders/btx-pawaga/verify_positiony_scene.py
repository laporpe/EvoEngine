#!/usr/bin/env python3
"""Load the position-Y PARBAR scene and report where the sensor probes actually sit.

No plants needed: creates the top-face sensor group, then prints per-panel probe
statistics (mean position, bar-axis direction, span) so the rig translations in
build_positiony_scene.py can be corrected against the intended furrow lines.

    conda run -n evoengine --no-capture-output python verify_positiony_scene.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "test_lsystem_sorghum.eveproj"
SCENE = Path("ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene")
PROBES_PER_PANEL = 50


def configure_engine_imports() -> None:
    paths = (
        BUILD / "PythonBinding" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG / "Packages",
        BUILD / "EvoEngine_SDK" / CONFIG,
        BUILD / "EvoEngine_Services" / "CudaModule" / CONFIG,
    )
    sys.path.insert(0, str(paths[0]))
    sys.path.insert(0, str(EVOENGINE / "PythonBinding"))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def main() -> int:
    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo

    runtime_packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(runtime_packages), str(SCENE)):
        raise RuntimeError(f"failed to load {SCENE}")
    if not evo.WaitForProjectIdle(30000):
        raise RuntimeError("scene never became idle")

    handle = evo.CreateParbarTopFaceSensorGroup(PROBES_PER_PANEL)
    records = list(evo.GetParbarTopFaceSensorResults(handle, PROBES_PER_PANEL))
    if not records:
        raise RuntimeError("no probe records - sensor group empty")

    panels: dict[tuple[str, str], list] = {}
    for r in records:
        panels.setdefault((r.cultivar, r.sensor_bar_level), []).append(r)

    measured = {}
    for (cultivar, level), probes in sorted(panels.items()):
        probes.sort(key=lambda r: r.column)
        xs = [float(p.position.x) for p in probes]
        ys = [float(p.position.y) for p in probes]
        zs = [float(p.position.z) for p in probes]
        n = len(probes)
        mean = (sum(xs) / n, sum(ys) / n, sum(zs) / n)
        dx, dz = xs[-1] - xs[0], zs[-1] - zs[0]
        span = math.hypot(dx, dz)
        axis_deg = math.degrees(math.atan2(dz, dx)) if span > 1e-6 else float("nan")
        print(f"{cultivar:7s} {level:7s} n={n:3d} mean=({mean[0]:7.3f},{mean[1]:6.3f},{mean[2]:7.3f}) "
              f"span={span:5.3f} m axis={axis_deg:6.1f} deg-from-+X", flush=True)
        measured[f"{cultivar}:{level}"] = {"center": list(mean), "axis_deg": axis_deg, "span_m": span}

    import json
    out = Path(__file__).resolve().parent / "measured_bars.json"
    out.write_text(json.dumps(measured, indent=1), encoding="utf-8")
    print(f"wrote {out}", flush=True)

    evo.Terminate()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
