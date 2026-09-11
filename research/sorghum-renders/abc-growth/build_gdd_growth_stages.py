#!/usr/bin/env python3
"""Re-key the per-week SorghumGrowthStages onto the measured field GDD axis.

`SorghumGrowthStages` (.sgs) is the engine's "states over time" mechanism: a list
of (Time, SorghumState) pairs, each state a full geometric snapshot of one
measured week. `SorghumGrowthStages::Apply(descriptor, time)` brackets the two
states around `time`, computes a = (t - t0) / (t1 - t0), and interpolates every
organ between them. Time is an arbitrary float, so it can be cumulative GDD.

The handoff shipped these states on a NORMALIZED axis (0.005 per day, origin
2026-07-09), which spaces the weeks evenly regardless of how much heat actually
accumulated between them. This rewrites Time to `gdd_cumulative_F_8655` from the
field record - 86 F upper cap, 55 F lower cap - so interpolation runs on thermal
time, and the uneven weeks are spaced as they really were.

Geometry is untouched: only each state's Time value changes.

    python build_gdd_growth_stages.py
"""

from __future__ import annotations

import os
import argparse
import csv
import re
import shutil
from collections import OrderedDict
from pathlib import Path

FIELD_CSV = Path(os.environ.get("SORGHUM_FIELD_CSV",
                    Path(__file__).resolve().parent.parent / "data"
                    / "sorghum_all_weeks_long_gdd.csv"))
SOURCE_DIR = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\HandoffTest\Assets\GrowthStages")
GDD_COLUMN = "gdd_cumulative_F_8655"

STATE_RE = re.compile(r"^- Time: (?P<time>[-\d.eE+]+)\s*$")
NAME_RE = re.compile(r"^  name: (?P<name>.+?)\s*$")


def field_gdd() -> "OrderedDict[str, tuple[int, float, str]]":
    """.sgs date-name (DD/MM/YYYY) -> (week, cumulative GDD, ISO date)."""
    by_week: dict[int, tuple[str, float]] = {}
    with FIELD_CSV.open() as handle:
        for row in csv.DictReader(handle):
            gdd = row[GDD_COLUMN].strip()
            if not gdd:
                continue
            by_week[int(row["week"])] = (row["date"], float(gdd))
    table: "OrderedDict[str, tuple[int, float, str]]" = OrderedDict()
    for week in sorted(by_week):
        iso, gdd = by_week[week]
        year, month, day = iso.split("-")
        table[f"{day}/{month}/{year}"] = (week, gdd, iso)
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--suffix", default="_gdd",
                        help="written alongside the originals as Genotype_X<suffix>.sgs")
    args = parser.parse_args()

    table = field_gdd()
    print(f"field GDD axis ({GDD_COLUMN}, 86/55 F caps):")
    for name, (week, gdd, iso) in table.items():
        print(f"  week {week}  {iso}  {name}  GDD {gdd:8.1f}")

    sources = sorted(p for p in args.source.glob("Genotype_?.sgs") if args.suffix not in p.stem)
    if not sources:
        raise SystemExit(f"no source .sgs under {args.source}")

    for source in sources:
        lines = source.read_text(encoding="utf-8").splitlines()
        # Each state block opens with "- Time:" and carries "  name:" a line or two later.
        pending: int | None = None
        remapped, missing = [], []
        for index, line in enumerate(lines):
            if STATE_RE.match(line):
                pending = index
                continue
            match = NAME_RE.match(line)
            if match and pending is not None:
                name = match.group("name")
                if name in table:
                    week, gdd, _ = table[name]
                    lines[pending] = f"- Time: {gdd:g}"
                    remapped.append((week, name, gdd))
                else:
                    missing.append(name)
                pending = None

        if not remapped:
            raise SystemExit(f"{source.name}: no state names matched the field record")

        target = source.with_name(f"{source.stem}{args.suffix}.sgs")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        meta = source.with_suffix(".sgs.evefilemeta")
        if meta.is_file():
            shutil.copy2(meta, target.with_name(f"{target.name}.evefilemeta"))

        span = f"{remapped[0][2]:.0f} -> {remapped[-1][2]:.0f} GDD"
        print(f"\n{target.name}: {len(remapped)} states, {span}")
        for week, name, gdd in remapped:
            print(f"    week {week}  {name}  Time={gdd:8.1f}")
        if missing:
            print(f"    unmatched state names (left as-is): {missing}")
        covered = {w for w, _, _ in remapped}
        absent = [w for w in (v[0] for v in table.values()) if w not in covered]
        if absent:
            print(f"    weeks present in the field record but absent from this .sgs: {absent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
