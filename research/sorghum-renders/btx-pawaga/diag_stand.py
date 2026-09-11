#!/usr/bin/env python3
"""Grow the small-layout stand for one seed and dump per-plant geometry near the bars."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 422021

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "test_lsystem_sorghum.eveproj"
SCENE = Path("ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene")

paths = (BUILD / "PythonBinding" / CONFIG, BUILD / "EvoEngine_App" / CONFIG,
         BUILD / "EvoEngine_App" / CONFIG / "Packages", BUILD / "EvoEngine_SDK" / CONFIG,
         BUILD / "EvoEngine_Services" / "CudaModule" / CONFIG)
sys.path.insert(0, str(paths[0]))
for p in paths:
    if p.exists():
        os.add_dll_directory(str(p))
os.chdir(BUILD / "PythonBinding" / CONFIG)
import PyDigitalAgriculture as evo  # noqa: E402

assert evo.RunLSystemSorghumProject(str(PROJECT), str(BUILD / "EvoEngine_App" / CONFIG / "Packages"), str(SCENE))
evo.WaitForProjectIdle(30000)
rows = ["BTX"] * 4 + ["Pawaga"] * 3
n = int(evo.ConfigureSorghumLsPlantingGrid(rows, 12, 0.30, 1.00, 0.0, 3.0))
assert int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) == n
assert int(evo.ConformSorghumLsPlantsToGroundMesh()) == n
desc = {"BTX": "BtxPawagaDrafts/BTX623_20210726_v3.sorghumls",
        "Pawaga": "BtxPawagaDrafts/Pawaga_20210726_v7.sorghumls"}
assert int(evo.SetSorghumLsGenotypeDescriptors(desc, False, SEED)) == n
evo.ConfigureSorghumLsLeafMeshQuality(0.02, 4, False, True, False)
assert evo.EnsureIlluminationSoilContext() and evo.ValidateIlluminationContext()
assert int(evo.GrowSorghumLsPlantsToAdulthood(SEED, "", False, True)) == n
evo.WaitForProjectIdle(30000)

records = list(evo.GetSorghumLsPlantSceneMetadata(True))
print(f"seed {SEED}: {len(records)} plants")
for r in sorted(records, key=lambda r: (round(float(r.global_position.z)), float(r.global_position.x))):
    z = float(r.global_position.z)
    x = float(r.global_position.x)
    if z >= 4.0:  # Pawaga rows only
        gmin, gmax = r.geometry_min_position, r.geometry_max_position
        width = max(float(gmax.x) - float(gmin.x), float(gmax.z) - float(gmin.z))
        near = "  <-- near bar" if z >= 5.0 and 0.4 <= x <= 2.4 else ""
        print(f"z={z:4.1f} x={x:+5.2f} h={float(r.plant_height_m):5.2f} spread={width:5.2f}{near}")
v = evo.Vec3(); v.x, v.y, v.z = 1.4, 7.0, 5.5
t = evo.Vec3(); t.x, t.y, t.z = 1.4, 0.0, 5.5
up = evo.Vec3(); up.x, up.y, up.z = 0.0, 0.0, 1.0
assert evo.SetMainCameraLookAt(v, t, up, 40.0)
evo.LoopFrames(8)
out = str(Path(__file__).resolve().parent / "renders" / f"diag_pawaga_topdown_seed{SEED}.png")
assert evo.CaptureCurrentScene(1024, 1024, out, 8)
print("captured", out)
evo.Terminate()
sys.stdout.flush()
os._exit(0)
