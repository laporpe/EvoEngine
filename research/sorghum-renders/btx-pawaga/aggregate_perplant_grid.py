#!/usr/bin/env python3
"""Aggregate per-seed 10x10 per-plant illumination files (run_perplant_grid.py) into

    results/perplant_grid/<geno>_<tag>_grid.csv      bridge 3-section grid (seed-mean per-area
                                                     absorbed flux: full context / plant alone / diff)
    results/perplant_grid/<geno>_<tag>_summary.csv   interior / edge / corner means

    python aggregate_perplant_grid.py --tag cal1
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_perplant_grid import GRID_N, write_grid_csv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="cal1")
    ap.add_argument("--genotypes", nargs="+", default=["BTX", "Pawaga"])
    args = ap.parse_args()
    out_dir = HERE / "results" / "perplant_grid"

    for geno in args.genotypes:
        files = sorted(glob.glob(str(out_dir / f"{geno}_{args.tag}_s*_plants_long.csv")))
        if not files:
            print(f"{geno}: no per-seed files, skipped")
            continue
        df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
        seeds = sorted(df["seed"].unique())
        cell = (df.groupby(["grid_row", "grid_column"])[["full_context_per_area", "plant_alone_per_area"]]
                  .mean().reset_index())
        rows = sorted(cell["grid_row"].unique()); cols = sorted(cell["grid_column"].unique())
        if len(rows) != GRID_N or len(cols) != GRID_N:
            print(f"WARNING {geno}: grid is {len(rows)}x{len(cols)}, expected {GRID_N}x{GRID_N}")
        piv_f = cell.pivot(index="grid_row", columns="grid_column", values="full_context_per_area")
        piv_a = cell.pivot(index="grid_row", columns="grid_column", values="plant_alone_per_area")
        write_grid_csv(out_dir / f"{geno}_{args.tag}_grid.csv",
                       piv_f.values.tolist(), piv_a.values.tolist())

        summ = (df.groupby("plant_type")
                  .agg(n=("retention_ratio", "size"),
                       full_context_per_area_mean=("full_context_per_area", "mean"),
                       plant_alone_per_area_mean=("plant_alone_per_area", "mean"),
                       retention_ratio_mean=("retention_ratio", "mean"),
                       retention_ratio_sd=("retention_ratio", "std"))
                  .reindex(["interior", "edge", "corner"]).reset_index())
        summ.insert(0, "genotype", geno)
        summ["n_seeds"] = len(seeds)
        summ.to_csv(out_dir / f"{geno}_{args.tag}_summary.csv", index=False)
        print(f"{geno}: seeds {seeds}")
        print(summ.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
