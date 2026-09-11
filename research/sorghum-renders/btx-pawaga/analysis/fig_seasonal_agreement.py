#!/usr/bin/env python3
"""Publication figure: seasonal canopy-transmittance agreement, field vs simulation.

Single panel: valid-window median tau per scan date; field values (filled squares,
one stand realization each) and simulation (open circles, mean with t-based 95% CI
over n = 3 geometry seeds). The one statistically detected difference (Pawaga,
Aug 22; p = 0.04, see analysis/seasonal_stats.py) is marked with an asterisk.

    python analysis/fig_seasonal_agreement.py
"""

from __future__ import annotations

import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parents[1]

DATES = ["2021-07-26", "2021-08-22", "2021-09-21"]
XLABELS = ["Jul 26", "Aug 22", "Sep 21"]
PATTERNS = {
    "2021-07-26": "results/tau_20210726_v1_E10v6_full_s*.csv",
    "2021-08-22": "results/tau_20210822_v1_V0822v6_s*.csv",
    "2021-09-21": "results/tau_20210921_v1_V0921v6_s*.csv",
}
FIELD = {
    "2021-07-26": {"BTX": 0.247, "Pawaga": 0.265},
    "2021-08-22": {"BTX": 0.248, "Pawaga": 0.283},
    "2021-09-21": {"BTX": 0.179, "Pawaga": 0.208},
}
COLORS = {"BTX": "#0072B2", "Pawaga": "#D55E00"}  # Okabe-Ito, CVD-validated
INK, GRID = "#1a1a1a", "#e4e4e0"
SIGNIFICANT = {("2021-08-22", "BTX")}  # p = 0.037 per seasonal_stats.py (n=8-12 ensembles)


def seed_medians(pattern: str) -> dict[str, list[float]]:
    out = {"BTX": [], "Pawaga": []}
    for path in sorted(glob.glob(str(HERE / pattern))):
        if "probes" in path:
            continue
        v = pd.read_csv(path)
        v = v[v["valid"]]
        out["BTX"].append(v["BTX_tau"].median())
        out["Pawaga"].append(v["Pawaga_tau"].median())
    return out


def mean_ci(vals: list[float]) -> tuple[float, float]:
    n = len(vals)
    mean = sum(vals) / n
    sd = (sum((x - mean) ** 2 for x in vals) / (n - 1)) ** 0.5
    return mean, stats.t.ppf(0.975, n - 1) * sd / n**0.5


def main() -> int:
    sim = {date: seed_medians(pat) for date, pat in PATTERNS.items()}
    fig, ax = plt.subplots(figsize=(6.0, 4.4))
    x = range(len(DATES))
    for genotype, dx in (("BTX", -0.08), ("Pawaga", +0.08)):
        name = "BTx623" if genotype == "BTX" else "Pawaga"
        fy = [FIELD[d][genotype] for d in DATES]
        sy, se = zip(*(mean_ci(sim[d][genotype]) for d in DATES))
        ax.plot([i + dx for i in x], fy, "-", color=COLORS[genotype], lw=1.3, alpha=0.5)
        ax.plot([i + dx for i in x], fy, "s", color=COLORS[genotype], ms=7,
                label=f"{name}, field")
        ax.errorbar([i + dx + 0.11 for i in x], sy, yerr=se, fmt="o", mfc="white",
                    color=COLORS[genotype], ms=7, lw=1.5, capsize=3.5,
                    label=f"{name}, simulated")
        for i, d in enumerate(DATES):
            if (d, genotype) in SIGNIFICANT:
                ax.text(i + dx, FIELD[d][genotype] + 0.012, "*", ha="center",
                        fontsize=13, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels(XLABELS)
    ax.set_xlim(-0.45, 2.55)
    ax.set_ylabel("Canopy transmittance $\\tau$", color=INK)
    ax.set_ylim(0.10, 0.36)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors=INK)
    ax.legend(fontsize=8.5, frameon=False, ncol=2, loc="lower left")
    fig.tight_layout()
    out = HERE / "results" / "tau_seasonal_agreement.png"
    fig.savefig(out, dpi=300)
    fig.savefig(out.with_suffix(".pdf"))
    print(f"wrote {out} (+ .pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
