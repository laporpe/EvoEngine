#!/usr/bin/env python3
"""Publication figure: simulated vs field diurnal transmittance, with and without
the field context east/west of the measured plots.

Story: the EvoEngine illumination engine reproduces the field PARbar signal —
but only when the simulated scene represents the field beyond the measured
plots, exactly as in reality. Two panels, same axes:

  (a) measured plots only (field edge at the block boundary)
  (b) complete field context (full plot block + ~10 sorghum rows east)

Each panel: field PARbar curves (solid) vs simulation (dashed, 3-seed mean with
min-max band) for both genotypes on 2021-07-26.

    python analysis/fig_east_rows.py
"""

from __future__ import annotations

import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parents[1]

# Final calibrated pair (BTx623 v6 / Pawaga v8) in both layouts, n=25 each
PANELS = [
    ("(a) measured plots only", "results/tau_20210726_v1_E11v6_small_s*.csv"),
    ("(b) complete field context", "results/tau_20210726_v1_E10v6_full_s*.csv"),
]
COLORS = {"BTX": "#0072B2", "Pawaga": "#D55E00"}  # Okabe-Ito, CVD-validated
INK, GRID = "#1a1a1a", "#e4e4e0"


def sim_band(pattern: str):
    frames = []
    for path in sorted(glob.glob(str(HERE / pattern))):
        if "probes" in path:
            continue
        df = pd.read_csv(path)
        df["hour"] = df["time_mst"].str.split(":").apply(lambda p: int(p[0]) + int(p[1]) / 60)
        frames.append(df[df["valid"]])
    grouped = pd.concat(frames).groupby("hour")
    return {g: grouped[f"{g}_tau"].agg(["mean", "min", "max"]) for g in ("BTX", "Pawaga")}


def main() -> int:
    field = pd.read_csv(HERE / "targets" / "three_scan_dates_profiles.csv")
    f26 = field[field["date"] == "2021-07-26"]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True, sharex=True)
    for ax, (title, pattern) in zip(axes, PANELS):
        band = sim_band(pattern)
        for genotype, field_name in (("BTX", "BTx623"), ("Pawaga", "Pawaga")):
            fv = f26[(f26["genotype"] == field_name) & (f26["valid"])]
            ax.plot(fv["hb"], fv["tau"], "-", color=COLORS[genotype], lw=2.0,
                    label=f"{field_name}, field")
            m = band[genotype]
            ax.plot(m.index, m["mean"], "--", color=COLORS[genotype], lw=1.5,
                    label=f"{field_name}, simulated")
            ax.fill_between(m.index, m["min"], m["max"], color=COLORS[genotype], alpha=0.14,
                            lw=0)
        ax.set_title(title, color=INK, fontsize=10.5)
        ax.set_xlabel("Hour (MST)", color=INK)
        ax.grid(color=GRID, lw=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(colors=INK)
    axes[0].set_ylabel("Canopy transmittance $\\tau$", color=INK)
    axes[0].set_ylim(0, 0.55)
    axes[0].legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    out = HERE / "results" / "fig_field_context.png"
    fig.savefig(out, dpi=300)
    fig.savefig(out.with_suffix(".pdf"))
    print(f"wrote {out} (+ .pdf)")

    # agreement stats per panel, for the caption
    for title, pattern in PANELS:
        band = sim_band(pattern)
        for genotype, field_name in (("BTX", "BTx623"), ("Pawaga", "Pawaga")):
            fv = f26[(f26["genotype"] == field_name) & (f26["valid"])].set_index("hb")["tau"]
            m = band[genotype]["mean"]
            common = m.index.intersection(fv.index)
            r = m.loc[common].corr(fv.loc[common])
            rmse = ((m.loc[common] - fv.loc[common]) ** 2).mean() ** 0.5
            print(f"{title} {field_name}: r={r:.2f} RMSE={rmse:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
