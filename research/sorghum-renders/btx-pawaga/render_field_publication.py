#!/usr/bin/env python3
"""Publication renders of the calibrated position-Y field.

Loads the PARBAR position-Y scene, plants the small layout (BTX rows z=0-3,
Pawaga z=4-6, 12 plants/row at 0.30 m, 1 m rows) with the calibrated cal1
descriptors, grows at fine mesh quality, lights the scene with the Nishita
atmosphere (mid-morning sun), and captures three views:

  field_overview.png   - elevated 3/4 view of the whole block from the south-west
  field_furrow.png     - low view down the BTX furrow with the PAR bar in frame
  field_topdown.png    - nadir orthophoto-style view of the block

    conda run -n evoengine --no-capture-output python render_field_publication.py
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "test_lsystem_sorghum.eveproj"
PROJECT_ASSETS = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "Assets"
SCENE = Path("ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene")
STAGE_DIR = "BtxPawagaDrafts"

ROW_GENOTYPES = ["BTX"] * 4 + ["Pawaga"] * 3
COLUMNS = 12
COLUMN_SPACING_M = 0.30
ROW_SPACING_M = 1.00
CENTER_X_M, CENTER_Z_M = 0.0, 3.0
BLOCK_CENTER = (0.0, 3.0)  # x, z

SUN_AZIMUTH_DEG = 135.0    # mid-morning south-east sun: modelling long soft shadows
SUN_ELEVATION_DEG = 40.0


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btx-descriptor", default="BTX623_20210726_cal1.sorghumls")
    parser.add_argument("--pawaga-descriptor", default="Pawaga_20210726_cal1.sorghumls")
    parser.add_argument("--seed", type=int, default=422021)
    parser.add_argument("--width", type=int, default=2400)
    parser.add_argument("--height", type=int, default=1500)
    parser.add_argument("--warmup-frames", type=int, default=10)
    args = parser.parse_args()

    stage = PROJECT_ASSETS / STAGE_DIR
    stage.mkdir(parents=True, exist_ok=True)
    descriptors = {}
    for cultivar, filename in (("BTX", args.btx_descriptor), ("Pawaga", args.pawaga_descriptor)):
        source = HERE / "descriptors" / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, stage / filename)
        descriptors[cultivar] = f"{STAGE_DIR}/{filename}"

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo

    runtime_packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(runtime_packages), str(SCENE)):
        raise RuntimeError(f"failed to load {SCENE}")
    if not evo.WaitForProjectIdle(30000):
        raise RuntimeError("scene never became idle")

    expected = len(ROW_GENOTYPES) * COLUMNS
    if int(evo.ConfigureSorghumLsPlantingGrid(ROW_GENOTYPES, COLUMNS, COLUMN_SPACING_M,
                                              ROW_SPACING_M, CENTER_X_M, CENTER_Z_M)) != expected:
        raise RuntimeError("marker count mismatch")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise RuntimeError("instantiate failed")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != expected:
        raise RuntimeError("ground conform failed")
    if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, args.seed)) != expected:
        raise RuntimeError("descriptor bind failed")
    evo.ConfigureSorghumLsLeafMeshQuality(0.01, 6, False, True, False)
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("soil context failed")
    if int(evo.GrowSorghumLsPlantsToAdulthood(args.seed, "", False, True)) != expected:
        raise RuntimeError("growth failed")
    if not evo.WaitForProjectIdle(30000):
        raise RuntimeError("post-growth idle failed")

    from sorghum_4x10_presentation import DEFAULT_PROFILE, set_ground_extension
    set_ground_extension(evo, True, DEFAULT_PROFILE)
    if not evo.SetNishitaSky(SUN_AZIMUTH_DEG, SUN_ELEVATION_DEG, 1.0, 2.2, 512, True, 3.0):
        raise RuntimeError("SetNishitaSky failed")

    def vec3(values):
        v = evo.Vec3()
        v.x, v.y, v.z = (float(x) for x in values)
        return v

    def capture(position, target, up, fov, name, width=None, height=None):
        w, h = width or args.width, height or args.height
        if not evo.SetMainCameraLookAt(vec3(position), vec3(target), vec3(up), float(fov)):
            raise RuntimeError("camera placement failed")
        evo.LoopFrames(args.warmup_frames)
        out = HERE / "renders" / "publication" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        if not evo.CaptureCurrentScene(w, h, str(out), args.warmup_frames):
            raise RuntimeError(f"capture failed: {name}")
        print(f"captured {out}", flush=True)

    cx, cz = BLOCK_CENTER
    # 1. Elevated 3/4 overview from the south-west: rows recede diagonally.
    capture(position=(cx - 7.5, 4.2, cz - 6.5), target=(cx, 0.7, cz), up=(0, 1, 0),
            fov=32, name="field_overview.png")
    # 2. Low view down the BTX furrow (z = 1.5): canopy walls + PAR bar.
    capture(position=(cx - 4.6, 0.9, 1.5), target=(cx + 1.0, 0.75, 1.5), up=(0, 1, 0),
            fov=38, name="field_furrow.png")
    # 3. Nadir block view (screen-up = +Z i.e. east; rows run across the frame).
    capture(position=(cx, 11.5, cz), target=(cx, 0.0, cz), up=(0, 0, 1),
            fov=34, name="field_topdown.png", width=2000, height=2000)
    # 4. End view down the rows from the south: all 7 rows in cross-section.
    #    Camera looks +X (north); screen-right = +Z (east), so BTx623 (rows
    #    z=0-3) fills the LEFT half and Pawaga (z=4-6) the RIGHT half.
    #    Tight framing keeps the canopy band and crops the sky bars out.
    capture(position=(cx - 6.0, 1.55, cz), target=(cx + 1.0, 0.85, cz), up=(0, 1, 0),
            fov=30, name="field_endview.png", width=2400, height=1100)

    evo.Terminate()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
