#!/usr/bin/env python3
"""Significance tests: simulated vs field canopy transmittance, per scan date.

Experimental unit = geometry seed (one simulated stand realization), n = 3 per date.
For each date x genotype (and the genotype contrast Pawaga - BTX, paired within seed):
one-sample t-test of the sim seed medians against the field value, and a t-based 95% CI.

Inputs : results/tau_<date>_v1_<tag>_s<seed>.csv (valid-window rows are used)
Output : results/seasonal_stats_table.csv + console table

    python analysis/seasonal_stats.py
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parents[1]

DATES = ["2021-07-26", "2021-08-22", "2021-09-21"]
PATTERNS = {
    "2021-07-26": "results/tau_20210726_v1_E10v6_full_s*.csv",
    "2021-08-22": "results/tau_20210822_v1_V0822v6_s*.csv",
    "2021-09-21": "results/tau_20210921_v1_V0921v6_s*.csv",
}
# Field valid-window median tau per methods_normalization.md (position Y, screened)
FIELD = {
    "2021-07-26": {"BTX": 0.247, "Pawaga": 0.265},
    "2021-08-22": {"BTX": 0.248, "Pawaga": 0.283},
    "2021-09-21": {"BTX": 0.179, "Pawaga": 0.208},
}


def seed_medians(pattern: str) -> dict[str, list[float]]:
    out = {"BTX": [], "Pawaga": [], "contrast": []}
    for path in sorted(glob.glob(str(HERE / pattern))):
        if "probes" in path:
            continue
        v = pd.read_csv(path)
        v = v[v["valid"]]
        b, p = v["BTX_tau"].median(), v["Pawaga_tau"].median()
        out["BTX"].append(b)
        out["Pawaga"].append(p)
        out["contrast"].append(p - b)
    return out


def one_sample(vals: list[float], target: float):
    n = len(vals)
    mean = sum(vals) / n
    sd = (sum((x - mean) ** 2 for x in vals) / (n - 1)) ** 0.5
    _, pval = stats.ttest_1samp(vals, target)
    half = stats.t.ppf(0.975, n - 1) * sd / n**0.5
    return mean, sd, half, pval


def main() -> int:
    rows = []
    sim = {date: seed_medians(pat) for date, pat in PATTERNS.items()}
    for date in DATES:
        for label, target in (
            ("BTX", FIELD[date]["BTX"]),
            ("Pawaga", FIELD[date]["Pawaga"]),
            ("Paw-BTX", FIELD[date]["Pawaga"] - FIELD[date]["BTX"]),
        ):
            vals = sim[date]["contrast" if label == "Paw-BTX" else label]
            mean, sd, half, pval = one_sample(vals, target)
            rows.append([date, label, round(target, 3), round(mean, 3), round(sd, 3),
                         f"[{mean - half:.3f},{mean + half:.3f}]", round(pval, 3),
                         "inside CI" if abs(mean - target) <= half else "OUTSIDE"])
    table = pd.DataFrame(rows, columns=["date", "quantity", "field", "sim_mean",
                                        "sim_sd", "sim_95CI", "p_ttest", "field_vs_CI"])
    print(table.to_string(index=False))
    out = HERE / "results" / "seasonal_stats_table.csv"
    table.to_csv(out, index=False)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
