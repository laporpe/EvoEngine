#!/usr/bin/env python3
"""Diurnal canopy-transmittance (tau) run on the position-Y PARBAR scene.

Loads Sorghum_PositionY_PARBAR45.evescene, plants the position-Y block (7 rows at 1 m:
BTX plots 7410-7413 at z=0..3, Pawaga 7414-7416 at z=4..6), grows the v-draft descriptors,
then sweeps the ray-tracer sun through the 15-min solar positions of a target date and
records per-bar sensor means. tau = bottom/top per cultivar, unit-free.

Sun convention (PyDigitalAgriculture.SetSunDirection, vec3 = pitch/yaw/roll degrees,
rotating (0,0,-1); OptiX sun_direction points TOWARD the sun, default zenith):
    d = (-sin(yaw)cos(pitch), sin(pitch), -cos(yaw)cos(pitch))
World frame: +X = north (rows), +Z = east. Compass azimuth A (N->E) needs
    pitch = elevation, yaw = 270 - A.
Check: yaw=90 -> d horizontal = (-1, 0) = due south = azimuth 180. Correct.

    conda run -n evoengine --no-capture-output python run_tau_diurnal.py --tag E2_baseline
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "test_lsystem_sorghum.eveproj"
PROJECT_ASSETS = EVOENGINE / "Resources" / "DigitalAgricultureProject" / "Assets"
SCENE = Path("ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene")
STAGE_DIR = "BtxPawagaDrafts"

# Position-Y block: rows west->east are plots 7410..7416 (1 row per plot [PROV]).
# Bars sit at z=1.5 (BTX, furrow 7411/7412) and z=5.5 (Pawaga, furrow 7415/7416),
# so whatever layout is chosen must keep those furrows in place.
LAYOUTS = {
    # rows z = 0..6 (7410-7413 BTX, 7414-7416 Pawaga)
    "small": (["BTX"] * 4 + ["Pawaga"] * 3, 3.0),
    # rows z = -8..6: full block sequence 7402-7405 BTX, 7406-7409 Pawaga,
    # 7410-7413 BTX, 7414-7416 Pawaga (per 2021 naming key)
    "block": (["BTX"] * 4 + ["Pawaga"] * 4 + ["BTX"] * 4 + ["Pawaga"] * 3, -1.0),
    # rows z = 0..16: position-Y block + 10 rows of sorghum east of 7416
    # (field truth: ~30 rows of BTX/Pawaga-like sorghum east; 10 saturates
    # direct-beam paths for the valid window's lowest elevation, 31 deg)
    "east10": (["BTX"] * 4 + ["Pawaga"] * 3 + ["BTX"] * 4 + ["Pawaga"] * 4 + ["BTX"] * 2, 8.0),
    # rows z = -4..12: field context on BOTH sides of both bars. Beams at the
    # valid window's lowest elevation (31 deg) traverse <= ~2.5 m of canopy to
    # reach a bottom bar, so >= 4 rows (4 m) of context per side is optically
    # equivalent to the real field's ~30; the far-west plots are omitted only
    # for GPU memory (300 plants OOMs the 8 GB card).
    "full": (["Pawaga"] * 4 + ["BTX"] * 4 + ["Pawaga"] * 3 + ["BTX"] * 4
             + ["Pawaga"] * 2, 4.0),
}
COLUMNS = 12               # ~3.5 m row at 0.30 m in-row spacing
COLUMN_SPACING_M = 0.30
ROW_SPACING_M = 1.00
CENTER_X_M = 0.0

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


def stage_descriptors(version: str, btx_file: str | None, pawaga_file: str | None) -> dict[str, str]:
    stage = PROJECT_ASSETS / STAGE_DIR
    stage.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for cultivar, filename in (
        ("BTX", btx_file or f"BTX623_20210726_{version}.sorghumls"),
        ("Pawaga", pawaga_file or f"Pawaga_20210726_{version}.sorghumls"),
    ):
        source = HERE / "descriptors" / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, stage / filename)
        mapping[cultivar] = f"{STAGE_DIR}/{filename}"
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1", help="descriptor draft version")
    parser.add_argument("--btx-descriptor", default=None,
                        help="override BTX descriptor filename (in descriptors/)")
    parser.add_argument("--pawaga-descriptor", default=None,
                        help="override Pawaga descriptor filename (in descriptors/)")
    parser.add_argument("--sun-csv", type=Path, default=HERE / "sun_positions_20210726.csv")
    parser.add_argument("--tag", default="run", help="output file tag")
    parser.add_argument("--seed", type=int, default=42_2021, help="geometry seed")
    parser.add_argument("--samples", type=int, default=128, help="rays per probe")
    parser.add_argument("--bounces", type=int, default=4)
    parser.add_argument("--valid-only", action="store_true",
                        help="run only bins inside the azimuth/elevation validity screen")
    parser.add_argument("--layout", choices=sorted(LAYOUTS), default="small",
                        help="field extent (bars stay at z=1.5 and z=5.5)")
    parser.add_argument("--leaf-vsub", type=float, default=0.01,
                        help="leaf mesh vertical subdivision (m); coarser for big scenes")
    parser.add_argument("--leaf-hsub", type=int, default=6,
                        help="leaf mesh horizontal subdivisions")
    parser.add_argument("--sky", nargs=3, type=float, default=None,
                        metavar=("SUN", "SKYLIGHT", "AMBIENT"),
                        help="explicit skydome intensities via ConfigureRayTracerSkydome "
                             "(default: scene/ray-tracer defaults via SetSunDirection)")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    bins = []
    with args.sun_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["elevation_deg"] = float(row["elevation_deg"])
            row["azimuth_deg"] = float(row["azimuth_deg"])
            row["valid"] = row["valid"] == "True"
            if args.valid_only and not row["valid"]:
                continue
            bins.append(row)
    print(f"{len(bins)} sun bins from {args.sun_csv.name}", flush=True)

    descriptors = stage_descriptors(args.version, args.btx_descriptor, args.pawaga_descriptor)
    print(f"descriptors: {descriptors}", flush=True)

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo

    runtime_packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(runtime_packages), str(SCENE)):
        raise RuntimeError(f"failed to load {SCENE}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("scene never became idle")

    row_genotypes, center_z = LAYOUTS[args.layout]
    expected = len(row_genotypes) * COLUMNS
    markers = int(evo.ConfigureSorghumLsPlantingGrid(
        row_genotypes, COLUMNS, COLUMN_SPACING_M, ROW_SPACING_M, CENTER_X_M, center_z))
    if markers != expected:
        raise RuntimeError(f"expected {expected} markers, got {markers}")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise RuntimeError("failed to instantiate plants")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != expected:
        raise RuntimeError("failed to conform plants to ground")
    if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, args.seed)) != expected:
        raise RuntimeError("failed to bind descriptors")
    evo.ConfigureSorghumLsLeafMeshQuality(args.leaf_vsub, args.leaf_hsub, False, True, False)
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("failed to establish soil/illumination context")
    if int(evo.GrowSorghumLsPlantsToAdulthood(args.seed, "", False, True)) != expected:
        raise RuntimeError("failed to grow plants")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("scene never became idle after growth")
    print(f"grown {expected} plants", flush=True)

    handle = evo.CreateParbarTopFaceSensorGroup(PROBES_PER_PANEL)

    def sun_vec(elevation_deg: float, azimuth_deg: float):
        v = evo.Vec3()
        v.x, v.y, v.z = float(elevation_deg), float(270.0 - azimuth_deg), 0.0
        return v

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    date_label = args.sun_csv.stem.replace("sun_positions_", "")
    summary_path = out_dir / f"tau_{date_label}_{args.version}_{args.tag}.csv"
    probes_path = out_dir / f"tau_{date_label}_{args.version}_{args.tag}_probes.csv"

    with summary_path.open("w", newline="", encoding="utf-8") as s_fh, \
         probes_path.open("w", newline="", encoding="utf-8") as p_fh:
        summary = csv.writer(s_fh)
        summary.writerow(["time_mst", "elevation_deg", "azimuth_deg", "valid",
                          "BTX_top", "BTX_bottom", "BTX_tau", "BTX_bottom_cv",
                          "Pawaga_top", "Pawaga_bottom", "Pawaga_tau", "Pawaga_bottom_cv"])
        probes_csv = csv.writer(p_fh)
        probes_csv.writerow(["time_mst", "cultivar", "level", "column", "scalar"])

        for index, b in enumerate(bins):
            if args.sky is not None:
                sun_i, sky_i, amb_i = args.sky
                if not evo.ConfigureRayTracerSkydome(
                        sun_vec(b["elevation_deg"], b["azimuth_deg"]),
                        sun_intensity=sun_i, skylight_intensity=sky_i,
                        ambient_light_intensity=amb_i):
                    raise RuntimeError("ConfigureRayTracerSkydome failed")
            else:
                evo.SetSunDirection(sun_vec(b["elevation_deg"], b["azimuth_deg"]))
            evo.EstimatePARSensors(handle, args.samples, args.bounces, 0.001, index + 1)
            records = list(evo.GetParbarTopFaceSensorResults(handle, PROBES_PER_PANEL))
            panels = defaultdict(list)
            for r in records:
                panels[(r.cultivar, r.sensor_bar_level)].append(r)
                probes_csv.writerow([b["time_mst"], r.cultivar, r.sensor_bar_level,
                                     r.column, f"{float(r.scalar):.6f}"])
            row = [b["time_mst"], b["elevation_deg"], b["azimuth_deg"], b["valid"]]
            for cultivar in ("BTX", "Pawaga"):
                top = [float(r.scalar) for r in panels[(cultivar, "top")]]
                bot = [float(r.scalar) for r in panels[(cultivar, "bottom")]]
                top_mean = sum(top) / len(top) if top else float("nan")
                bot_mean = sum(bot) / len(bot) if bot else float("nan")
                tau = bot_mean / top_mean if top_mean else float("nan")
                bot_cv = (math.sqrt(sum((v - bot_mean) ** 2 for v in bot) / len(bot)) / bot_mean
                          if bot and bot_mean else float("nan"))
                row += [f"{top_mean:.5f}", f"{bot_mean:.5f}", f"{tau:.4f}", f"{bot_cv:.3f}"]
            summary.writerow(row)
            s_fh.flush()
            print(f"[{index + 1}/{len(bins)}] {b['time_mst']} elev={b['elevation_deg']:.1f} "
                  f"az={b['azimuth_deg']:.1f} BTX tau={row[6]} Pawaga tau={row[10]}", flush=True)

    print(f"wrote {summary_path}", flush=True)
    evo.Terminate()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
