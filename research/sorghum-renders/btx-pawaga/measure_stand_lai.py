#!/usr/bin/env python3
"""Geometric stand LAI of the calibrated BTX / Pawaga scenes (EvoEngine, no ray tracing).

Loads the same position-Y PARBAR scene and layout as run_tau_diurnal.py, binds the
calibrated descriptors, grows the stand, then reads per-plant leaf area from
GetSorghumLsPlantSceneMetadata(measure_geometry=True). Stand LAI per genotype is

    LAI = sum(leaf_area_m2 of that genotype's plants) / (n_rows * COLUMNS * ROW_SPACING * COLUMN_SPACING)

The engine's leaf_area_m2 sums sampler areas over BOTH leaf faces (SamplerSurfaceArea adds
front and back), i.e. it is TWO-SIDED; aggregate_stand_lai.py halves it to the one-sided
LAI used by Beer-Lambert. The tau runs used a static canopy for all three scan dates, so
one LAI per genotype (per seed) applies to 2021-07-26, 08-22 and 09-21 alike.

One geometry seed per process (batch_seeds.py uses the same pattern; multi-seed re-binding
inside one process failed after the first seed on 2026-09-11).

Outputs (results/):
    stand_lai_<tag>_s<seed>_plants.csv   one row per plant (leaf area, height, leaf/tiller counts)
Then:  python aggregate_stand_lai.py --tag cal1   ->  results/stand_lai_<tag>.csv

    conda run -n evoengine --no-capture-output python measure_stand_lai.py --layout east10 \
        --seed 422021 --tag cal1
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_tau_diurnal import (  # noqa: E402  (same scene/layout definitions as the tau runs)
    BUILD, CONFIG, PROJECT, SCENE, LAYOUTS, COLUMNS, COLUMN_SPACING_M, ROW_SPACING_M,
    CENTER_X_M, configure_engine_imports, stage_descriptors,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", choices=sorted(LAYOUTS), default="east10")
    parser.add_argument("--btx-descriptor", default="BTX623_20210726_v4.sorghumls")
    parser.add_argument("--pawaga-descriptor", default="Pawaga_20210726_v8.sorghumls")
    parser.add_argument("--seed", type=int, required=True, help="one geometry seed per process")
    parser.add_argument("--leaf-vsub", type=float, default=0.02)
    parser.add_argument("--leaf-hsub", type=int, default=4)
    parser.add_argument("--tag", default="cal1")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    descriptors = stage_descriptors("v1", args.btx_descriptor, args.pawaga_descriptor)
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
    rows_per_geno = {g: row_genotypes.count(g) for g in set(row_genotypes)}
    markers = int(evo.ConfigureSorghumLsPlantingGrid(
        row_genotypes, COLUMNS, COLUMN_SPACING_M, ROW_SPACING_M, CENTER_X_M, center_z))
    if markers != expected:
        raise RuntimeError(f"expected {expected} markers, got {markers}")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise RuntimeError("failed to instantiate plants")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != expected:
        raise RuntimeError("failed to conform plants to ground")

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    plants_path = out_dir / f"stand_lai_{args.tag}_s{args.seed}_plants.csv"

    per_geno_lai: dict[str, list[float]] = defaultdict(list)
    plant_rows = []
    for seed in [args.seed]:
        if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, seed)) != expected:
            raise RuntimeError("failed to bind descriptors")
        evo.ConfigureSorghumLsLeafMeshQuality(args.leaf_vsub, args.leaf_hsub, False, True, False)
        if int(evo.GrowSorghumLsPlantsToAdulthood(seed, "", False, True)) != expected:
            raise RuntimeError("failed to grow plants")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError("scene never became idle after growth")
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        area_by_geno: dict[str, float] = defaultdict(float)
        n_by_geno: dict[str, int] = defaultdict(int)
        for r in records:
            if not bool(r.has_geometry):
                continue
            cultivar = str(r.cultivar)
            area_by_geno[cultivar] += float(r.leaf_area_m2)
            n_by_geno[cultivar] += 1
            plant_rows.append({
                "seed": seed, "cultivar": cultivar, "name": str(r.name),
                "leaf_area_m2": f"{float(r.leaf_area_m2):.5f}",
                "plant_height_m": f"{float(r.plant_height_m):.4f}",
                "leaf_count": int(r.leaf_count), "main_culm_leaf_count": int(r.main_culm_leaf_count),
                "tiller_leaf_count": int(r.tiller_leaf_count),
                "primary_tiller_count": int(r.primary_tiller_count),
                "x_m": f"{float(r.global_position.x):.3f}", "z_m": f"{float(r.global_position.z):.3f}",
            })
        for cultivar, area in area_by_geno.items():
            ground = rows_per_geno[cultivar] * COLUMNS * ROW_SPACING_M * COLUMN_SPACING_M
            lai = area / ground
            per_geno_lai[cultivar].append(lai)
            print(f"seed {seed} {cultivar}: n={n_by_geno[cultivar]} leaf area {area:.2f} m2 "
                  f"over {ground:.2f} m2 -> LAI {lai:.3f}", flush=True)

    with plants_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(plant_rows[0]))
        w.writeheader(); w.writerows(plant_rows)

    print(f"wrote {plants_path}", flush=True)
    evo.Terminate()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
