#!/usr/bin/env python3
"""Hold the main culm erect: main_culm_lean_angle = 0.

The field data records a stem angle of 4-11 deg off vertical, and that was
originally fitted straight into `main_culm_lean_angle`. Two problems with using
it as a whole-plant lean:

  * The engine applies it rigidly. `SorghumRules.cpp` sets
    `internode.branch_angle = rank == 0 ? main_culm_lean_angle : 0` with
    `curvature = 0` on every internode above, so the entire culm is a straight
    rod offset from vertical - there is no gravitropic straightening, unlike
    tillers which ramp from insertion angle to final lean. Even 5 deg applied
    along a 2 m culm puts the tip ~17 cm off plumb.
  * The measurement is instantaneous and includes transient deflection. The
    week-6 note on plant 73-3 records "Windy during these measurements, which
    can impact angles", and the genotype-C week-7 plants carry panicles, which
    makes them top-heavy.

Real sorghum culms stand erect, so 0 is the better approximation. Tiller lean is
left untouched - tillers genuinely do depart from the culm, and the engine models
that departure correctly.

    python set_main_culm_erect.py
"""

from __future__ import annotations

import os
import argparse
import re
from pathlib import Path

DESC = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\HandoffTest\Assets\Descriptors")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lean", type=float, default=0.0,
                        help="degrees off vertical for the main culm (default 0 = erect)")
    parser.add_argument("--deviation", type=float, default=0.0,
                        help="plant-to-plant spread in that lean (default 0)")
    args = parser.parse_args()

    for path in sorted(DESC.glob("*.sorghumls")):
        text = path.read_text(encoding="utf-8")
        block = (f"main_culm_lean_angle:\n  mean: {args.lean:.6g}\n"
                 f"  deviation: {args.deviation:.6g}")
        text, count = re.subn(r"main_culm_lean_angle:\n  mean: .*\n  deviation: .*", block, text)
        if count != 1:
            raise SystemExit(f"{path.name}: matched main_culm_lean_angle {count} times")
        path.write_text(text, encoding="utf-8")
        print(f"{path.name:26s} main_culm_lean_angle = {args.lean:g} +/- {args.deviation:g} deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
