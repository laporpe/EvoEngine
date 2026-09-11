#!/usr/bin/env python3
"""Publication figure: genotype architecture contrast in the simulated field.

Composites the top-down and row-end renders (from render_field_publication.py)
into one labeled two-panel figure so the BTx623 vs Pawaga blocks are explicit.

Row layout in both renders: BTx623 occupies rows z = 0-3, Pawaga rows z = 4-6.
Top-down: screen-up = +Z (east), so Pawaga is the TOP band and BTx623 the
bottom band. End view: camera looks east down the rows; z increases to frame
LEFT, so Pawaga is the LEFT group and BTx623 the right group.

    python analysis/fig_genotype_views.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

HERE = Path(__file__).resolve().parents[1]
INK = "white"
BOX = dict(facecolor="black", alpha=0.55, boxstyle="round,pad=0.35", lw=0)


def main() -> int:
    top = mpimg.imread(HERE / "renders" / "publication" / "field_topdown.png")
    end = mpimg.imread(HERE / "renders" / "publication" / "field_endview.png")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 5.2),
                                   gridspec_kw={"width_ratios": [1.0, 1.55]})
    ax1.imshow(top)
    h, w = top.shape[0], top.shape[1]
    # top-down: Pawaga = upper (east) band, BTx623 = lower band
    ax1.text(0.05 * w, 0.16 * h, "Pawaga", color=INK, fontsize=13, bbox=BOX)
    ax1.text(0.05 * w, 0.72 * h, "BTx623", color=INK, fontsize=13, bbox=BOX)
    ax1.set_title("(a) top-down", fontsize=11)

    # crop the sky band (raised reference bars float there and distract)
    end = end[int(0.355 * end.shape[0]):int(0.97 * end.shape[0]), :, :]
    ax2.imshow(end)
    h, w = end.shape[0], end.shape[1]
    # end view camera looks +X (north): screen-right = +Z (east), so
    # BTx623 (rows z=0-3) is the LEFT group, Pawaga (z=4-6) the RIGHT group
    ax2.text(0.08 * w, 0.13 * h, "BTx623", color=INK, fontsize=13, bbox=BOX)
    ax2.text(0.74 * w, 0.13 * h, "Pawaga", color=INK, fontsize=13, bbox=BOX)
    ax2.set_title("(b) row cross-section", fontsize=11)

    for ax in (ax1, ax2):
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.tight_layout()
    out = HERE / "results" / "fig_genotype_architecture.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
