#!/usr/bin/env python3
"""Route B: 10x10 per-plant illumination grids on the calibrated BTX / Pawaga geometry.

For each genotype, plants a 10-row x 10-column stand at the field row geometry
(1.0 m rows, 0.30 m in-row) in the position-Y scene, binds the calibrated descriptor,
grows it, and calls EstimateSorghumLsGridIllumination, which returns per-plant absorbed
light in two scenarios: full context (all neighbours present) and plant alone (only that
plant visible to the ray tracer). Sun: fixed overhead reference (scene default), as in the
2026-06-30 10x10 handoff.

One geometry seed per process. Outputs (results/perplant_grid/):
    <geno>_<tag>_s<seed>_plants_long.csv   one row per plant, all record fields
Then aggregate over seeds with:  python aggregate_perplant_grid.py --tag cal1   which writes
    <geno>_<tag>_grid.csv          the fspm_cgm_bridge 3-section grid format consumed by
                                   fspm/evoengine_utils.parse_irradiance_csv and
                                   figures/plot_shading_heatmaps.py:
                                     "Per Plant Irradiance (Full Field Context)" 10x10
                                     "Per Plant Irradiance (Isolation)"          10x10
                                     "Difference (Full Field - Isolation)"       10x10
                                   values = per-leaf-area average absorbed flux scalar
                                   (engine units), seed-averaged; row = grid_row, col = grid_column.
    <geno>_<tag>_summary.csv       interior / edge / corner means of full, alone, retention.

NOTE these grids are per-plant ABSORBED light, not below-canopy transmittance, so they
must NOT be fed to rederive_k_from_evoengine.py (k comes from the PARbar tau route). They
serve the shading heatmap figure and the interior/edge/corner shading contrast.

    conda run -n evoengine --no-capture-output python run_perplant_grid.py --tag cal1 --seed 422021
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
from run_tau_diurnal import (  # noqa: E402
    BUILD, CONFIG, PROJECT, SCENE, COLUMN_SPACING_M, ROW_SPACING_M, CENTER_X_M,
    configure_engine_imports, stage_descriptors,
)

GRID_N = 10
CENTER_Z_M = 12.0   # east of the PARBAR masts (bars sit at z = 1.5 and 5.5)


def classify(row: int, col: int, n: int = GRID_N) -> str:
    on_r, on_c = row in (0, n - 1), col in (0, n - 1)
    if on_r and on_c:
        return "corner"
    if on_r or on_c:
        return "edge"
    return "interior"


def write_grid_csv(path: Path, full: list[list[float]], alone: list[list[float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write("Per Plant Irradiance (Full Field Context)\n")
        for r in full:
            fh.write(",".join(f"{v:.6f}" for v in r) + "\n")
        fh.write("\nPer Plant Irradiance (Isolation)\n")
        for r in alone:
            fh.write(",".join(f"{v:.6f}" for v in r) + "\n")
        fh.write("\nDifference (Full Field - Isolation)\n")
        for rf, ra in zip(full, alone):
            fh.write(",".join(f"{f - a:.6f}" for f, a in zip(rf, ra)) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btx-descriptor", default="BTX623_20210726_v4.sorghumls")
    parser.add_argument("--pawaga-descriptor", default="Pawaga_20210726_v8.sorghumls")
    parser.add_argument("--genotypes", nargs="+", default=["BTX", "Pawaga"])
    parser.add_argument("--seed", type=int, required=True, help="one geometry seed per process")
    parser.add_argument("--ray-seed", type=int, default=0)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--bounces", type=int, default=4)
    parser.add_argument("--leaf-vsub", type=float, default=0.02)
    parser.add_argument("--leaf-hsub", type=int, default=4)
    parser.add_argument("--tag", default="cal1")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    descriptors = stage_descriptors("v1", args.btx_descriptor, args.pawaga_descriptor)
    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo

    out_dir = HERE / "results" / "perplant_grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"

    for geno in args.genotypes:
        if not evo.RunLSystemSorghumProject(str(PROJECT), str(runtime_packages), str(SCENE)):
            raise RuntimeError(f"failed to load {SCENE}")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError("scene never became idle")
        if hasattr(evo, "RemoveParbarContext"):
            evo.RemoveParbarContext()
        expected = GRID_N * GRID_N
        markers = int(evo.ConfigureSorghumLsPlantingGrid(
            [geno] * GRID_N, GRID_N, COLUMN_SPACING_M, ROW_SPACING_M, CENTER_X_M, CENTER_Z_M))
        if markers != expected:
            raise RuntimeError(f"expected {expected} markers, got {markers}")
        if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
            raise RuntimeError("failed to instantiate plants")
        if int(evo.ConformSorghumLsPlantsToGroundMesh()) != expected:
            raise RuntimeError("failed to conform plants to ground")
        if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
            raise RuntimeError("failed to establish soil/illumination context")

        long_rows = []
        acc_full: dict[tuple[int, int], list[float]] = defaultdict(list)
        acc_alone: dict[tuple[int, int], list[float]] = defaultdict(list)
        for i, seed in [(args.ray_seed, args.seed)]:
            if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, seed)) != expected:
                raise RuntimeError("failed to bind descriptors")
            evo.ConfigureSorghumLsLeafMeshQuality(args.leaf_vsub, args.leaf_hsub, False, True, False)
            if int(evo.GrowSorghumLsPlantsToAdulthood(seed, "", False, True)) != expected:
                raise RuntimeError("failed to grow plants")
            if not evo.WaitForProjectIdle(args.max_wait_frames):
                raise RuntimeError("scene never became idle after growth")
            records = list(evo.EstimateSorghumLsGridIllumination(
                args.samples, args.bounces, 0, 0.001, i, geno))
            print(f"{geno} seed {seed}: {len(records)} plant records", flush=True)
            for r in records:
                area = float(r.area)
                if area <= 0:
                    continue
                row, col = int(r.row), int(r.column)
                full_pa = float(r.scalar) / area
                alone_pa = float(r.isolated_scalar) / area
                acc_full[(row, col)].append(full_pa)
                acc_alone[(row, col)].append(alone_pa)
                long_rows.append({
                    "genotype": geno, "seed": seed, "grid_row": row, "grid_column": col,
                    "plant_type": classify(row, col), "name": str(r.name),
                    "full_context_scalar": f"{float(r.scalar):.6f}",
                    "plant_alone_scalar": f"{float(r.isolated_scalar):.6f}",
                    "full_context_per_area": f"{full_pa:.6f}",
                    "plant_alone_per_area": f"{alone_pa:.6f}",
                    "retention_ratio": f"{float(r.retention_ratio):.5f}",
                    "shadow_loss": f"{float(r.shadow_loss):.5f}",
                    "green_area_m2": f"{area:.5f}", "leaf_area_m2": f"{float(r.leaf_area):.5f}",
                    "plant_height_m": f"{float(r.plant_height_m):.4f}",
                    "x_m": f"{float(r.position.x):.3f}", "z_m": f"{float(r.position.z):.3f}",
                    "ray_samples": args.samples, "ray_bounces": args.bounces, "ray_seed": i,
                })
        evo.Terminate()

        if not long_rows:
            raise RuntimeError(f"no records for {geno}")
        with (out_dir / f"{geno}_{args.tag}_s{args.seed}_plants_long.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(long_rows[0])); w.writeheader(); w.writerows(long_rows)

        print(f"wrote {out_dir / f'{geno}_{args.tag}_s{args.seed}_plants_long.csv'}", flush=True)

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
