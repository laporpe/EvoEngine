#!/usr/bin/env python3
"""Fit one .sorghumls per genotype per week from the 2026 field record.

Each week becomes its own L-system descriptor, so a GDD sweep can step through
real measured states while keeping everything the LS path models that the
growth-stages (.sgs) path cannot - above all tillers, which `SorghumState` has
no representation for at all.

Leaf angle convention, per the field protocol:
    leafY = pitch, angle from HORIZONTAL -> insertion angle = 90 - |leafY|
            (verified: matches the dataset's own angle_from_vertical on all 590
             leaves that carry both)
    leafX = yaw, rotation of the leaf around the stem -> leaf_roll_angle,
            a deviation about the distichous base (median 0)
    leafZ = roll of the leaf surface plane -> no descriptor parameter; ignored.

Everything else - tiller lean, base offset, emergent height, erect culm - is
inherited from the tuned week-7 template, so this only overrides what the field
actually measured that week.

Coverage is uneven and the script says so per file: leafX/Y/Z and tillers exist
only for weeks 6-8, internodes from week 3, and week 1 has genotype B alone.
Anything absent is carried from the nearest week that has it.

    python build_weekly_descriptors.py
"""

from __future__ import annotations

import os
import argparse
import csv
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

FIELD_CSV = Path(os.environ.get("SORGHUM_FIELD_CSV",
                    Path(__file__).resolve().parent.parent / "data"
                    / "sorghum_all_weeks_long_gdd.csv"))
TEMPLATE_DIR = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\HandoffTest\Assets\Descriptors")
OUT_DIR = TEMPLATE_DIR / "weekly"
GDD_COLUMN = "gdd_cumulative_F_8655"

# Field range -> genotype. Weeks 2-3 left the genotype column blank but the
# plant_id prefix still carries the range.
RANGE_TO_GENOTYPE = {"73": "C", "74": "B", "75": "A"}
GENOTYPES = ("A", "B", "C")
WEEKS = tuple(range(1, 9))


# --------------------------------------------------------------------------
# Field record
# --------------------------------------------------------------------------
def load_field():
    """(genotype, week) -> measurements, plus week -> (date, GDD)."""
    per_plant = defaultdict(lambda: defaultdict(dict))
    weeks = {}
    with FIELD_CSV.open() as handle:
        for row in csv.DictReader(handle):
            week = int(row["week"])
            gdd = row[GDD_COLUMN].strip()
            if gdd:
                weeks[week] = (row["date"], float(gdd))
            genotype = row["genotype"].strip() or RANGE_TO_GENOTYPE.get(row["plant_id"][:2], "")
            if not genotype:
                continue
            value = row["value"].strip()
            if not value:
                continue
            if row["variable"] == "panicle_emerged":
                value = value.lower() in ("true", "1", "yes")
            else:
                try:
                    value = float(value)
                except ValueError:
                    continue
            key = (genotype, week, row["plant_id"])
            rank = row["rank"].strip()
            rank = int(float(rank)) if rank else None
            per_plant[key][(row["organ"], row["variable"])][rank] = value
    return per_plant, dict(sorted(weeks.items()))


def rank_profile(per_plant, genotype, week, organ, variable, scale=1.0, transform=None):
    """Mean value at each rank across the plants measured that week."""
    by_rank = defaultdict(list)
    for (g, w, _), measures in per_plant.items():
        if g != genotype or w != week:
            continue
        for rank, value in measures.get((organ, variable), {}).items():
            if rank is None:
                continue
            by_rank[rank].append(transform(value) if transform else value)
    if not by_rank:
        return []
    return [st.mean(by_rank[r]) * scale for r in sorted(by_rank)]


def plant_scalar(per_plant, genotype, week, organ, variable, scale=1.0, transform=None):
    values = []
    for (g, w, _), measures in per_plant.items():
        if g != genotype or w != week:
            continue
        for value in measures.get((organ, variable), {}).values():
            values.append(transform(value) if transform else value)
    if not values:
        return None
    return (st.mean(values) * scale,
            (st.pstdev(values) if len(values) > 1 else 0.0) * scale,
            len(values))


def panicle_emerged(per_plant, genotype, week):
    """Fraction of plants with an emerged panicle, or None if never scored.

    Only weeks 6-8 were scored; earlier weeks have no record, which for a
    reproductive organ means "not yet", not "unknown".
    """
    flags = []
    for (g, w, _), measures in per_plant.items():
        if g == genotype and w == week:
            flags.extend(measures.get(("plant", "panicle_emerged"), {}).values())
    if not flags:
        return None
    return sum(1 for f in flags if f) / len(flags)


def leaf_count(per_plant, genotype, week):
    counts = []
    for (g, w, _), measures in per_plant.items():
        if g == genotype and w == week:
            ranks = measures.get(("leaf", "length_cm"), {})
            if ranks:
                counts.append(len(ranks))
    return (st.mean(counts), st.pstdev(counts) if len(counts) > 1 else 0.0) if counts else None


# --------------------------------------------------------------------------
# Descriptor editing
# --------------------------------------------------------------------------
def curve_points(values):
    """Normalized (position, fraction) pairs plus the peak used as max_value."""
    peak = max(values)
    if peak <= 0:
        return None, None
    n = len(values)
    points = [((i / (n - 1)) if n > 1 else 0.0, v / peak) for i, v in enumerate(values)]
    return peak, points


def set_plotted(text: str, key: str, values, name: str) -> str:
    """Rewrite the `mean:` sub-block of a PlottedDistribution from a rank profile."""
    peak, points = curve_points(values)
    if peak is None:
        return text
    body = [f"{key}:", "  mean:", "    min_value: 0", f"    max_value: {peak:.6g}",
            "    curve:", "      tangent_: false", "      min_: [0, 0]", "      max_: [1, 1]",
            "      values_:"]
    body += [f"        - [{x:.8g}, {y:.8g}]" for x, y in points]
    pattern = re.compile(
        rf"^{re.escape(key)}:\n  mean:\n    min_value: .*\n    max_value: .*\n"
        rf"    curve:\n(?:      .*\n)*?      values_:\n(?:        - \[.*\]\n)+",
        re.M)
    replacement = "\n".join(body) + "\n"
    text, count = pattern.subn(lambda _m: replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"{name}: could not rewrite {key} ({count} matches)")
    return text


def set_single(text: str, key: str, mean: float, deviation: float, name: str,
               insert_after: str | None = None) -> str:
    """Rewrite a SingleDistribution, or insert it when the template omits the key.

    The handoff only wrote the panicle size keys for genotypes that had a
    panicle, so for A and B those have to be created rather than edited.
    """
    block = f"{key}:\n  mean: {mean:.6g}\n  deviation: {deviation:.6g}"
    text, count = re.subn(rf"{re.escape(key)}:\n  mean: .*\n  deviation: .*", block, text, count=1)
    if count == 1:
        return text
    if insert_after:
        anchor = re.search(rf"^{re.escape(insert_after)}: .*$", text, re.M)
        if anchor:
            return text[:anchor.end()] + "\n" + block + text[anchor.end():]
    raise SystemExit(f"{name}: could not rewrite or insert {key}")


def set_scalar(text: str, key: str, value, name: str) -> str:
    text, count = re.subn(rf"^{re.escape(key)}: .*$", f"{key}: {value}", text, count=1, flags=re.M)
    if count != 1:
        raise SystemExit(f"{name}: could not rewrite {key} ({count} matches)")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    per_plant, weeks = load_field()
    print("field GDD axis (86/55 F caps):")
    for week, (date, gdd) in weeks.items():
        print(f"  week {week}  {date}  {gdd:8.1f} GDD")

    # Pass 1: gather everything measurable, so gaps can be filled from neighbours.
    fitted = {}
    for genotype in GENOTYPES:
        for week in WEEKS:
            entry = {
                "leaf_count": leaf_count(per_plant, genotype, week),
                "blade_length": rank_profile(per_plant, genotype, week, "leaf", "length_cm", 0.01),
                "blade_width": rank_profile(per_plant, genotype, week, "leaf", "width_cm", 0.01),
                # pitch: field angle is from horizontal, so 90 - |y| is from vertical
                "insertion": rank_profile(per_plant, genotype, week, "leaf", "angle_from_vertical"),
                # yaw: deviation of the leaf around the stem, signed
                "roll": rank_profile(per_plant, genotype, week, "leaf", "leafX"),
                "internode_length": rank_profile(per_plant, genotype, week, "internode",
                                                 "seg_length_cm", 0.01),
                "internode_thickness": rank_profile(per_plant, genotype, week, "internode",
                                                    "dia_sheath_mm", 0.001),
                "height": plant_scalar(per_plant, genotype, week, "plant", "height_cm", 0.01),
                "tiller_count": plant_scalar(per_plant, genotype, week, "plant", "tiller_number"),
                "tiller_lean": plant_scalar(per_plant, genotype, week, "tiller", "tiller_y_angle",
                                            transform=lambda v: 90.0 - abs(v)),
                "panicle_emerged": panicle_emerged(per_plant, genotype, week),
                "panicle_len": plant_scalar(per_plant, genotype, week, "plant",
                                            "panicle_len_cm", 0.01),
                "panicle_wid": plant_scalar(per_plant, genotype, week, "plant",
                                            "panicle_wid_cm", 0.01),
            }
            fitted[(genotype, week)] = entry

    def nearest(genotype, week, field):
        """Value for this week, else from the closest week that has one."""
        if fitted[(genotype, week)].get(field):
            return fitted[(genotype, week)][field], week
        for distance in range(1, len(WEEKS) + 1):
            for candidate in (week - distance, week + distance):
                if candidate in WEEKS and fitted[(genotype, candidate)].get(field):
                    return fitted[(genotype, candidate)][field], candidate
        return None, None

    print(f"\nwriting descriptors to {args.out}")
    written = 0
    for genotype in GENOTYPES:
        template_path = TEMPLATE_DIR / f"Genotype{genotype}_week7.sorghumls"
        template = template_path.read_text(encoding="utf-8")
        for week in WEEKS:
            entry = fitted[(genotype, week)]
            name = f"Genotype{genotype}_w{week}.sorghumls"
            text = template
            borrowed = []

            counts, src = nearest(genotype, week, "leaf_count")
            if counts:
                text = set_single(text, "total_phytomer_count", counts[0], counts[1], name)
                if src != week:
                    borrowed.append(f"leaf_count<-w{src}")

            for field, key in (("blade_length", "leaf_blade_length"),
                               ("blade_width", "leaf_blade_max_width"),
                               ("insertion", "leaf_insertion_angle"),
                               ("roll", "leaf_roll_angle"),
                               ("internode_length", "internode_length"),
                               ("internode_thickness", "internode_thickness")):
                profile, src = nearest(genotype, week, field)
                if not profile:
                    continue
                if field == "roll":
                    # yaw is signed about zero; the curve carries magnitude, so fit |X|
                    profile = [abs(v) for v in profile]
                text = set_plotted(text, key, profile, name)
                if src != week:
                    borrowed.append(f"{field}<-w{src}")

            tillers, src = nearest(genotype, week, "tiller_count")
            if tillers:
                text = set_single(text, "tiller_count", tillers[0], tillers[1], name)
                if src != week:
                    borrowed.append(f"tiller_count<-w{src}")

            lean, src = nearest(genotype, week, "tiller_lean")
            if lean:
                spread = min(max(lean[1], 1.5), 5.0)
                text = set_single(text, "tiller_final_lean_angle", lean[0], spread, name)
                text = set_single(text, "tiller_insertion_angle", lean[0], 2.0, name)
                if src != week:
                    borrowed.append(f"tiller_lean<-w{src}")

            # A panicle only exists from the week it actually emerged. Weeks with no
            # scoring at all (1-5) count as not emerged rather than unknown.
            emerged = entry["panicle_emerged"]
            show_panicle = bool(emerged and emerged >= 0.5)
            text = set_scalar(text, "enable_panicle",
                              "true" if show_panicle else "false", name)
            if show_panicle:
                length, width = entry["panicle_len"], entry["panicle_wid"]
                if length:
                    text = set_single(text, "panicle_rachis_length_m", length[0],
                                      length[1], name, insert_after="enable_panicle")
                if width:
                    # branch length is the rachis-to-tip radius, so half the measured width
                    text = set_single(text, "panicle_branch_length_m", width[0] / 2.0,
                                      width[1] / 2.0, name, insert_after="enable_panicle")
                borrowed.append(f"panicle({emerged * 100:.0f}%)")

            (args.out / name).write_text(text, encoding="utf-8")
            written += 1
            height = entry["height"]
            leaves = entry["leaf_count"]
            print(f"  {name:26s} GDD {weeks[week][1]:7.1f}  "
                  f"leaves {leaves[0]:5.1f}  " if leaves else f"  {name:26s} ",
                  end="")
            print(f"height {height[0]:.2f} m  " if height else "height    -   ", end="")
            print(f"[{' '.join(borrowed)}]" if borrowed else "[all measured]")
    print(f"\n{written} descriptors written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
