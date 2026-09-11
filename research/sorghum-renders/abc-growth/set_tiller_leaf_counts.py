#!/usr/bin/env python3
"""Give each descriptor an empirical tiller leaf-count distribution.

Replaces the prescribed-height model with a data-driven one. Previously a tiller
got round(main_leaves x 0.90) leaves, clamped to [0.75, 1.05] x the main culm,
and its internodes were then rescaled so its tip reached 0.90 x culm height.
Height was prescribed; nothing emerged.

The measured tiller/main leaf-count ratio is strongly bimodal - late "baby"
tillers at 0.1-0.4 and established ones at 0.7-1.2, with a gap between - so the
old clamp kept only the upper mode and deleted the babies entirely.

This writes, per genotype and week:
  * `tiller_leaf_count_ratio_quantiles` - the inverse CDF of that week's measured
    tiller leaf counts, as a fraction of that week's mean main-culm leaf count.
    The engine draws a uniform value and reads the ratio off this curve.
  * `tiller_emergent_height: true` - the tiller then reads the culm's internode
    profile by absolute rank and its height is simply the sum of the internodes
    it carries.

    python set_tiller_leaf_counts.py
"""

from __future__ import annotations

import os
import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\Brenda\Downloads\SorghumCleanedData_weeks6-7 (1)\SorghumCleanedData_weeks6-7")
TILLERS = ROOT / "cleaned" / "tiller_long_wk6-7.csv"
PLANTS = ROOT / "cleaned" / "plant_level_wk6-7.csv"
DESC = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\HandoffTest\Assets\Descriptors")

KEY = "tiller_leaf_count_ratio_quantiles"


def curve_block(ratios: list[float]) -> str:
    """An inverse CDF as a Plot2D: value(t) = mix(0, max_ratio, curve(t))."""
    ordered = sorted(ratios)
    ceiling = max(ordered)
    points = []
    for index, ratio in enumerate(ordered):
        # Mid-rank plotting position, so the curve spans the sample evenly.
        quantile = (index + 0.5) / len(ordered)
        points.append((quantile, ratio / ceiling))
    # Anchor both ends so draws below/above the sampled quantiles stay in range.
    points = [(0.0, ordered[0] / ceiling)] + points + [(1.0, 1.0)]

    lines = [
        f"{KEY}:",
        "  mean:",
        "    min_value: 0",
        f"    max_value: {ceiling:.6g}",
        "    curve:",
        "      tangent_: false",
        "      min_: [0, 0]",
        "      max_: [1, 1]",
        "      values_:",
    ]
    for x, y in points:
        lines.append(f"        - [{x:.6g}, {y:.6g}]")
    lines += [
        "  deviation:",
        "    min_value: 0",
        "    max_value: 0",
        "    curve:",
        "      tangent_: false",
        "      min_: [0, 0]",
        "      max_: [1, 1]",
        "      values_:",
        "        - [0, 0]",
        "        - [1, 0]",
    ]
    return "\n".join(lines)


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()

    main_leaves = {}
    with PLANTS.open() as handle:
        for row in csv.DictReader(handle):
            if row["metric"] == "leaf_count":
                main_leaves[(row["genotype"], row["week"])] = float(row["mean"])

    counts = defaultdict(list)
    with TILLERS.open() as handle:
        for row in csv.DictReader(handle):
            leaves = row["num_leaves"].strip()
            if leaves:
                counts[(row["genotype"], row["week"])].append(float(leaves))

    for key in sorted(counts):
        genotype, week = key
        path = DESC / f"Genotype{genotype}_week{week}.sorghumls"
        culm = main_leaves[key]
        ratios = [n / culm for n in counts[key]]

        text = path.read_text(encoding="utf-8")
        block = curve_block(ratios)
        if f"\n{KEY}:" in text:
            text = re.sub(rf"\n{re.escape(KEY)}:\n(?:[ ].*\n)*", "\n" + block + "\n", text, count=1)
        else:
            anchor = re.search(r"^tiller_height_ratio:\n  mean: .*\n  deviation: .*$", text, re.M)
            if not anchor:
                raise SystemExit(f"{path.name}: no tiller_height_ratio anchor")
            text = text[:anchor.end()] + "\n" + block + text[anchor.end():]

        if "tiller_emergent_height:" in text:
            text = re.sub(r"^tiller_emergent_height: .*$", "tiller_emergent_height: true", text, flags=re.M)
        else:
            text = text.replace(f"\n{KEY}:", "\ntiller_emergent_height: true\n" + KEY + ":", 1)

        path.write_text(text, encoding="utf-8")
        leaves = sorted(int(n) for n in counts[key])
        print(f"{path.name:26s} culm={culm:4.1f}  n={len(ratios):2d}  "
              f"ratios {min(ratios):.2f}-{max(ratios):.2f}  tiller leaves={leaves}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
