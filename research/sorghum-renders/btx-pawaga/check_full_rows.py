#!/usr/bin/env python3
"""Instantiate the block grid and print each plant row's cultivar vs z position."""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "test_lsystem_sorghum.eveproj"
SCENE = Path("ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene")

ROWS = ["Pawaga"] * 4 + ["BTX"] * 4 + ["Pawaga"] * 3 + ["BTX"] * 4 + ["Pawaga"] * 2

paths = (
    BUILD / "PythonBinding" / CONFIG,
    BUILD / "EvoEngine_App" / CONFIG,
    BUILD / "EvoEngine_App" / CONFIG / "Packages",
    BUILD / "EvoEngine_SDK" / CONFIG,
    BUILD / "EvoEngine_Services" / "CudaModule" / CONFIG,
)
sys.path.insert(0, str(paths[0]))
for p in paths:
    if p.exists():
        os.add_dll_directory(str(p))
os.chdir(BUILD / "PythonBinding" / CONFIG)
import PyDigitalAgriculture as evo  # noqa: E402

if not evo.RunLSystemSorghumProject(str(PROJECT), str(BUILD / "EvoEngine_App" / CONFIG / "Packages"), str(SCENE)):
    raise RuntimeError("load failed")
evo.WaitForProjectIdle(30000)
n = int(evo.ConfigureSorghumLsPlantingGrid(ROWS, 12, 0.30, 1.00, 0.0, 4.0))
print("markers:", n)
if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != n:
    raise RuntimeError("instantiate failed")
records = list(evo.GetSorghumLsPlantSceneMetadata(False))
byrow = defaultdict(set)
for r in records:
    byrow[round(float(r.global_position.z), 2)].add(r.cultivar)
for z in sorted(byrow):
    print(f"z={z:+.2f}  {sorted(byrow[z])}")
print("bars: BTX furrow z=1.5, Pawaga furrow z=5.5")
evo.Terminate()
sys.stdout.flush()
os._exit(0)
