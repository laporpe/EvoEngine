"""Render the late-season panel C transmission-ratio comparison figure."""

from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

DATES = ["2021-08-18", "2021-08-30", "2021-09-02"]
COLORS = {"BTx623": "#3a7d3a", "Pawaga": "#7a4fb0"}


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=script_dir / "panelC_inputs.csv")
    parser.add_argument("--output", type=Path, default=script_dir / "panelC_transmission_ratio_late.png")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    data = pd.read_csv(args.input)
    data["ratio_observed"] = data["field_below_mol_m2_day"] / data["field_above_par_mol_m2_day"]
    data["ratio_simulated"] = data["tau_sim"]
    data = data[data["date"].isin(DATES)]

    x = np.arange(len(DATES))
    fig, ax = plt.subplots(figsize=(4.2, 3.6))

    for genotype, color in COLORS.items():
        rows = data[data["genotype"] == genotype].set_index("date").reindex(DATES)
        ax.plot(x, rows["ratio_observed"], color=color, lw=1.6, marker="o", ms=6, zorder=3)
        ax.plot(
            x,
            rows["ratio_simulated"],
            color=color,
            lw=1.4,
            ls="--",
            marker="o",
            ms=6,
            mfc="white",
            mew=1.3,
            zorder=2,
        )

    ax.set_title("transmission ratio (below / above)", fontsize=8.5, loc="left")
    ax.set_ylabel("\u03c4 (unitless)")
    ax.set_xticks(x)
    ax.set_xticklabels([date[5:] for date in DATES], rotation=30, ha="right", fontsize=7)
    ax.set_ylim(0, 0.6)
    ax.margins(x=0.12)
    ax.spines[["top", "right"]].set_visible(False)

    genotype_handles = [Line2D([0], [0], color=COLORS[genotype], lw=1.6) for genotype in COLORS]
    style_handles = [
        Line2D([0], [0], color="0.3", lw=1.6, marker="o", ms=6),
        Line2D([0], [0], color="0.3", lw=1.4, ls="--", marker="o", ms=6, mfc="white", mew=1.3),
    ]
    genotype_legend = ax.legend(
        genotype_handles,
        list(COLORS),
        fontsize=7,
        frameon=False,
        loc="upper left",
        title="genotype",
        title_fontsize=7,
    )
    ax.add_artist(genotype_legend)
    ax.legend(
        style_handles,
        ["observed (field)", "simulated (EvoEngine)"],
        fontsize=7,
        frameon=False,
        loc="upper right",
    )

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
