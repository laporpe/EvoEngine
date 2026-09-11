#!/usr/bin/env python3
"""Aggregate per-seed stand leaf-area files into results/stand_lai_<tag>.csv.

Reads results/stand_lai_<tag>_s<seed>_plants.csv (from measure_stand_lai.py), computes
per seed and genotype

    LAI_one_sided = (sum leaf_area_m2 / SIDEDNESS) / (n_rows * COLUMNS * ROW_SPACING * COLUMN_SPACING)

and writes one row per genotype with mean/SD over seeds plus plant-level statistics.
SIDEDNESS = 2 because the engine's leaf_area_m2 counts both leaf faces (see
measure_stand_lai.py). No engine needed; runs in any env with pandas.

    python aggregate_stand_lai.py --tag cal1 --layout east10
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402
sys.path.insert(0, str(HERE))
from run_tau_diurnal import LAYOUTS, COLUMNS, COLUMN_SPACING_M, ROW_SPACING_M  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="cal1")
    ap.add_argument("--layout", choices=sorted(LAYOUTS), default="east10")
    ap.add_argument("--sidedness", type=float, default=2.0,
                    help="divide engine leaf area by this to get one-sided area (2 = both faces counted)")
    args = ap.parse_args()

    files = sorted(glob.glob(str(HERE / "results" / f"stand_lai_{args.tag}_s*_plants.csv")))
    if not files:
        raise SystemExit("no per-seed files found")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    row_genotypes, _ = LAYOUTS[args.layout]
    rows_per_geno = {g: row_genotypes.count(g) for g in set(row_genotypes)}

    per_seed = (df.groupby(["cultivar", "seed"])
                  .agg(leaf_area_two_sided=("leaf_area_m2", "sum"), n_plants=("leaf_area_m2", "size"))
                  .reset_index())
    per_seed["ground_m2"] = per_seed["cultivar"].map(
        lambda g: rows_per_geno[g] * COLUMNS * ROW_SPACING_M * COLUMN_SPACING_M)
    per_seed["lai_one_sided"] = per_seed["leaf_area_two_sided"] / args.sidedness / per_seed["ground_m2"]
    per_seed["lai_two_sided"] = per_seed["leaf_area_two_sided"] / per_seed["ground_m2"]
    print(per_seed.to_string(index=False))

    out_rows = []
    for geno, sub in per_seed.groupby("cultivar"):
        plants = df[df["cultivar"] == geno]
        out_rows.append({
            "genotype": geno,
            "lai_mean": round(sub["lai_one_sided"].mean(), 4),
            "lai_sd": round(sub["lai_one_sided"].std(ddof=1) if len(sub) > 1 else 0.0, 4),
            "n_seeds": len(sub),
            "lai_two_sided_mean": round(sub["lai_two_sided"].mean(), 4),
            "sidedness_divisor": args.sidedness,
            "layout": args.layout, "rows": rows_per_geno[geno], "columns": COLUMNS,
            "row_spacing_m": ROW_SPACING_M, "column_spacing_m": COLUMN_SPACING_M,
            "plants_per_m2": round(1.0 / (ROW_SPACING_M * COLUMN_SPACING_M), 3),
            "mean_one_sided_leaf_area_per_plant_m2": round(plants["leaf_area_m2"].mean() / args.sidedness, 4),
            "mean_plant_height_m": round(plants["plant_height_m"].mean(), 3),
            "mean_leaf_count": round(plants["leaf_count"].mean(), 2),
            "mean_primary_tiller_count": round(plants["primary_tiller_count"].mean(), 2),
            "seeds": ";".join(str(s) for s in sorted(sub["seed"])),
        })
    out = pd.DataFrame(out_rows)
    path = HERE / "results" / f"stand_lai_{args.tag}.csv"
    out.to_csv(path, index=False)
    print(f"\nwrote {path}")
    print(out[["genotype", "lai_mean", "lai_sd", "n_seeds", "mean_leaf_count", "mean_primary_tiller_count"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
