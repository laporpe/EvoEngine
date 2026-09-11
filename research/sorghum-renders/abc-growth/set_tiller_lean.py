#!/usr/bin/env python3
"""Fit tiller lean from mature tillers only, so tillers stop splaying.

Small "baby" tillers lean far more than established ones: in the 2026 field data
both 40 deg tillers carry exactly 2 leaves, and across all 55 measured tillers
lean correlates negatively with leaf count (r = -0.28; median 10 deg for tillers
with >=9 leaves vs 14 deg for those with <=4).

The engine never produces a baby tiller. `ComputeSorghumTillerLeafBudget` clamps
every tiller to [0.75, 1.05] x the main culm's leaf count, so a modelled tiller
always has roughly as many leaves as the culm. Fitting lean on the full field
sample therefore mixes in a population the model does not simulate, and the
resulting spread tips mature tillers over to 30-40 deg.

So: keep only tillers at or above the engine's own 0.75 x main-leaf-count floor,
take the median for the centre and a MAD-based scale for the spread, and clamp
the spread to a sane band. `tiller_insertion_angle` tracks the centre so each
tiller axis stays straight.

The maturity filter is now off (MATURITY_FRACTION = 0). It was a workaround for
the engine only ever producing mature tillers; with emergent height the model
draws leaf counts from the measured distribution and produces both populations,
so the full measured lean sample is the right one to fit.

    python set_tiller_lean.py --deviation-cap 5
"""

from __future__ import annotations

import os
import argparse
import csv
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\Brenda\Downloads\SorghumCleanedData_weeks6-7 (1)\SorghumCleanedData_weeks6-7")
TILLERS = ROOT / "cleaned" / "tiller_long_wk6-7.csv"
PLANTS = ROOT / "cleaned" / "plant_level_wk6-7.csv"
DESC = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\HandoffTest\Assets\Descriptors")

MATURITY_FRACTION = 0.0  # no filter: the engine now models baby tillers too
MINIMUM_SAMPLE = 3        # below this, pool the genotype's mature tillers across weeks
INSERTION_DEV = 2.0


def set_block(text: str, key: str, mean: float, dev: float, name: str) -> str:
    block = f"{key}:\n  mean: {mean:.6g}\n  deviation: {dev:.6g}"
    text, count = re.subn(rf"{re.escape(key)}:\n  mean: .*\n  deviation: .*", block, text)
    if count != 1:
        raise SystemExit(f"{name}: matched {key} {count} times")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deviation-cap", type=float, default=5.0,
                        help="maximum tiller lean sd in degrees (default 5)")
    parser.add_argument("--deviation-floor", type=float, default=1.5,
                        help="minimum sd; field angles are recorded to the whole degree")
    args = parser.parse_args()

    main_leaves = {}
    with PLANTS.open() as handle:
        for row in csv.DictReader(handle):
            if row["metric"] == "leaf_count":
                main_leaves[(row["genotype"], row["week"])] = float(row["mean"])

    # angle from vertical = 90 - |y|, the convention proven by the ground plate
    measured = defaultdict(list)
    with TILLERS.open() as handle:
        for row in csv.DictReader(handle):
            angle, leaves = row["tiller_y_angle"].strip(), row["num_leaves"].strip()
            if angle and leaves:
                measured[(row["genotype"], row["week"])].append(
                    (float(leaves), 90.0 - abs(float(angle)))
                )

    mature = {key: [lean for leaves, lean in rows
                    if leaves >= MATURITY_FRACTION * main_leaves[key]]
              for key, rows in measured.items()}
    by_genotype = defaultdict(list)
    for (genotype, _), leans in mature.items():
        by_genotype[genotype].extend(leans)

    for key in sorted(measured):
        genotype, week = key
        path = DESC / f"Genotype{genotype}_week{week}.sorghumls"
        leans, source = sorted(mature[key]), "own mature tillers"
        if len(leans) < MINIMUM_SAMPLE:
            leans, source = sorted(by_genotype[genotype]), f"pooled genotype {genotype} (no mature tillers this week)"

        centre = st.median(leans)
        mad = st.median([abs(v - centre) for v in leans])
        spread = min(max(1.4826 * mad, args.deviation_floor), args.deviation_cap)

        text = path.read_text(encoding="utf-8")
        text = set_block(text, "tiller_final_lean_angle", centre, spread, path.name)
        text = set_block(text, "tiller_insertion_angle", centre, INSERTION_DEV, path.name)
        path.write_text(text, encoding="utf-8")

        dropped = len(measured[key]) - len(mature[key])
        print(f"{path.name:26s} lean={centre:5.2f} +/- {spread:4.2f} deg   n={len(leans):2d} "
              f"(dropped {dropped} immature)  [{source}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
