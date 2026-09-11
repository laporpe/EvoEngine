#!/usr/bin/env python3
"""Grow one plant of each genotype (A, B, C) side by side and film it.

Answers "can these plants grow over time?" - yes. `SorghumLS` is a developmental
model driven by growing-degree-days, not a static mesh. Every plant carries a
`target_gdd`, and the engine exposes two ways to move it:

  * `GrowSorghumLsPlantsToGdd`    -> LSystemLayer::RegenerateSorghumScene
      Rebuilds the plant from scratch at that GDD. Stateless, any order.
  * `AdvanceSorghumLsPlantsToGdd` -> LSystemLayer::AdvanceSorghumScene
      Carries the existing developmental state forward. Monotonic - GDD must
      increase - and this is what actually models growth.

This script uses Regenerate once to measure the mature canopy (so the camera can
be framed on the final size and held still), then rewinds and Advances through
the sequence, which is the real developmental progression.

Seeds are pinned to a constant base on every call, so the same three individuals
grow throughout instead of being redrawn each frame.

    python render_abc_growth.py --frames 120 --week 7
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

EVOENGINE = Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine"))
BUILD = EVOENGINE / "out" / "build" / "x64-Release"
CONFIG = "Release"
PROJECT_ROOT = EVOENGINE / "Resources" / "DigitalAgricultureProject"
PROJECT = PROJECT_ROOT / "test_lsystem_sorghum.eveproj"
TEMPLATE_SCENE = Path("ManualAssets/Scenes/Sorghum_6x10_2026.evescene")

SOURCE_DESCRIPTORS = EVOENGINE / "Resources" / "HandoffTest" / "Assets" / "Descriptors"
STAGE_DIR_NAME = "HandoffTuned"
GENOTYPES = ("A", "B", "C")

FIELD_CSV = Path(os.environ.get("SORGHUM_FIELD_CSV",
                    Path(__file__).resolve().parent.parent / "data"
                    / "sorghum_all_weeks_long_gdd.csv"))
GDD_COLUMN = "gdd_cumulative_F_8655"

# Calibrated against the field record: at 100 GDD per phytomer the model reaches
# 11 leaves by week 2 (measured 11.0-12.4) and 13 by weeks 4-6 (measured
# 12.4-14.2). 80 is far too fast - 12 leaves already at week 1 where 7.4 was
# measured - and 130 far too slow, 8 at week 2. maturity keeps the template's
# 8x plastochron ratio so organ expansion scales with emergence.
PLASTOCHRON_GDD = 100.0
MATURITY_RATIO = 8.0

# Maricopa Agricultural Center, AZMet station az06. Arizona keeps standard time
# all year, so the offset is a constant -7 with no daylight-saving shift.
SITE_LATITUDE = 33.069
SITE_LONGITUDE = -111.972
SITE_UTC_OFFSET = -7.0
# Chart surface and ink. Dark card so the readout is stable whether the frame
# behind it is a noon sky or midnight soil.
VIZ_SURFACE = (26, 26, 25)
VIZ_BORDER = (58, 58, 55)
VIZ_GRID = (47, 47, 45)
VIZ_INK = (232, 232, 228)
VIZ_MUTED = (154, 154, 149)
# Categorical slots 1-3, stepped for a dark surface. Validated as a set:
# all-pairs CVD dE 9.4 worst, normal-vision 20.9 worst, all >= 3:1 on #1a1a19.
GENOTYPE_INK = {"A": (57, 135, 229), "B": (217, 89, 38), "C": (25, 158, 112)}

HOURLY_WEATHER = Path(os.environ.get("SORGHUM_HOURLY_WEATHER",
                    Path(__file__).resolve().parent.parent / "data"
                    / "azmet_hourly_maricopa_2026.csv"))
PLANTING_DATE = date(2026, 6, 1)

# Logistic height model fitted to the 2024 Droneland trial:
#     height = K / (1 + exp(-r * (days_after_planting - t_mid)))
# Median of 233 genotypes, terrain-model method. The surface-model fits in the
# same file are not usable - a third of them fail to converge, giving canopy
# heights of hundreds of metres and growth rates above 1 m/day.
LOGISTIC_R = 0.097
LOGISTIC_T_MID = 41.38

SEED = 202_609_020
LEAF_VERTICAL_SUBDIVISION_M = 0.01
LEAF_HORIZONTAL_SUBDIVISIONS = 6


def configure_engine_imports() -> None:
    paths = (
        BUILD / "PythonBinding" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG,
        BUILD / "EvoEngine_App" / CONFIG / "Packages",
        BUILD / "EvoEngine_SDK" / CONFIG,
        BUILD / "EvoEngine_Services" / "CudaModule" / CONFIG,
    )
    sys.path.insert(0, str(paths[0]))
    sys.path.insert(0, str(EVOENGINE / "PythonBinding"))
    for path in paths:
        if path.exists() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(path))


def field_weeks() -> dict:
    """week -> (ISO date, cumulative GDD) on the 86/55 F axis."""
    weeks = {}
    with FIELD_CSV.open() as handle:
        for row in csv.DictReader(handle):
            gdd = row[GDD_COLUMN].strip()
            if gdd:
                weeks[int(row["week"])] = (row["date"], float(gdd))
    return dict(sorted(weeks.items()))


def set_single(text: str, key: str, mean: float) -> str:
    block = f"{key}:\n  mean: {mean:.6g}\n  deviation: 0"
    text, count = re.subn(rf"{re.escape(key)}:\n  mean: .*\n  deviation: .*",
                          block, text, count=1)
    if count != 1:
        raise SystemExit(f"could not rewrite {key}")
    return text


def stage_descriptors(week: int, plastochron: float, target_gdd: float) -> dict:
    """Stage the week's descriptors with the thermal axis rescaled to field GDD.

    The template runs on its own 0-660 GDD scale, while the field record is
    cumulative GDD from planting - 980 at week 1 through 2320 at week 8.
    Rewriting plastochron, maturity and target puts development on the field's
    axis, so sweeping real GDD advances the plant at the measured rate.

    The filename encodes the calibration: the engine caches assets by path, so a
    fixed name would silently serve the first variant for the whole run.
    """
    stage = PROJECT_ROOT / "Assets" / STAGE_DIR_NAME
    stage.mkdir(parents=True, exist_ok=True)
    tag = f"w{week}p{int(plastochron)}"
    mapping = {}
    for genotype in GENOTYPES:
        source = SOURCE_DESCRIPTORS / f"Genotype{genotype}_week{week}.sorghumls"
        if not source.is_file():
            raise SystemExit(f"missing descriptor: {source}")
        text = source.read_text(encoding="utf-8")
        text = set_single(text, "plastochron_gdd", plastochron)
        text = set_single(text, "maturity_gdd", plastochron * MATURITY_RATIO)
        text = set_single(text, "target_gdd", target_gdd)
        name = f"Genotype{genotype}_{tag}.sorghumls"
        (stage / name).write_text(text, encoding="utf-8")
        mapping[f"Genotype{genotype}"] = f"{STAGE_DIR_NAME}/{name}"
    return mapping


def logistic_fraction(days_after_planting: float, rate: float, midpoint: float) -> float:
    """Fraction of final height reached, by the fitted logistic."""
    return 1.0 / (1.0 + math.exp(-rate * (days_after_planting - midpoint)))


def build_height_schedule(evo, gdd_values, seed, wait_frames, samples=48):
    """Map 'fraction of final height' back to the heat total that produces it.

    The plant model emits a phytomer every plastochron, so height climbs in
    steps and the reported bounding box can even dip when leaves reorient. Left
    alone that reads as jerky, and its fastest days run two to three times the
    measured maximum growth rate. Sampling height against heat once, forcing the
    result to be non-decreasing, and then inverting it lets the render request a
    height fraction instead of a heat total - so the logistic sets the pace.
    """
    low, high = gdd_values[0], gdd_values[-1]
    probe = [low + (high - low) * i / (samples - 1) for i in range(samples)]
    if int(evo.GrowSorghumLsPlantsToGdd(probe[0], seed, True)) != 3:
        raise SystemExit("failed to start the height sweep")
    evo.WaitForProjectIdle(wait_frames)

    heights, running = [], 0.0
    for value in probe:
        if int(evo.AdvanceSorghumLsPlantsToGdd(value, seed, True)) != 3:
            raise SystemExit(f"failed to sweep to {value:.0f} GDD")
        evo.WaitForProjectIdle(wait_frames)
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        mean_height = sum(float(r.plant_height_m) for r in records) / max(1, len(records))
        running = max(running, mean_height)  # height cannot go backwards
        heights.append(running)

    span = heights[-1] - heights[0]
    fractions = [((h - heights[0]) / span) if span > 0 else 0.0 for h in heights]
    return probe, fractions


def gdd_for_fraction(probe, fractions, wanted: float) -> float:
    """Invert the sampled height curve."""
    wanted = min(max(wanted, 0.0), 1.0)
    for index in range(1, len(fractions)):
        if fractions[index] >= wanted:
            lower, upper = fractions[index - 1], fractions[index]
            if upper <= lower:
                return probe[index]
            share = (wanted - lower) / (upper - lower)
            return probe[index - 1] + share * (probe[index] - probe[index - 1])
    return probe[-1]


def solar_position(moment: datetime) -> tuple[float, float]:
    """Solar elevation and azimuth in degrees for the field site.

    Standard NOAA solar-position equations. Azimuth is measured clockwise from
    north, which is what the sky binding expects.
    """
    day_of_year = moment.timetuple().tm_yday
    hour = moment.hour + moment.minute / 60.0
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (hour - 12.0) / 24.0)

    equation_of_time = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                                 - 0.032077 * math.sin(gamma)
                                 - 0.014615 * math.cos(2 * gamma)
                                 - 0.040849 * math.sin(2 * gamma))
    declination = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
                   - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
                   - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))

    offset = equation_of_time + 4.0 * SITE_LONGITUDE - 60.0 * SITE_UTC_OFFSET
    #  already carries the minutes as a fraction; adding moment.minute again
    # double-counts them, which makes the sun race within each hour and snap back
    # at the top of it. Only shows up when sampling below hourly resolution.
    true_solar_time = hour * 60.0 + offset
    hour_angle = math.radians(true_solar_time / 4.0 - 180.0)

    latitude = math.radians(SITE_LATITUDE)
    cos_zenith = (math.sin(latitude) * math.sin(declination)
                  + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle))
    zenith = math.acos(max(-1.0, min(1.0, cos_zenith)))
    elevation = 90.0 - math.degrees(zenith)

    denominator = math.sin(zenith) * math.cos(latitude)
    if abs(denominator) < 1e-6:
        azimuth = 180.0
    else:
        cos_azimuth = (math.sin(declination) - math.sin(latitude) * cos_zenith) / denominator
        azimuth = math.degrees(math.acos(max(-1.0, min(1.0, cos_azimuth))))
        if hour_angle > 0:
            azimuth = 360.0 - azimuth
    return elevation, azimuth


def load_hourly_weather(path: Path, hours_per_frame: int,
                        heat_source: str = "thermal") -> list[dict]:
    """Hourly AZMet rows, thinned to one every `hours_per_frame`."""
    if not path.is_file():
        raise SystemExit(f"missing {path} - run fetch_azmet_hourly.py first")
    rows = []
    with path.open() as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "moment": datetime.fromisoformat(row["datetime"]),
                "gdd": float(row["gdd_field_cum"]),
                "radiation": float(row["sol_rad_total"]),
                "temperature": float(row["temp_airF"]),
                "gdd_raw": float(row["gdd_raw"]),
            })
    rows.sort(key=lambda r: r["moment"])
    if heat_source == "thermal":
        rows = spread_heat_over_full_day(rows)
    return rows[::max(1, hours_per_frame)]


def apply_heat_scenario(rows: list[dict], upper_cap: float, offset: float,
                        night_warming: float = 0.0, lower: float = 55.0) -> list[dict]:
    """Re-accrue heat across the window under a different temperature ceiling.

    Both scenarios open on the same plant: the cumulative total at the first row
    is kept, and only the rate from there on changes. So any divergence you see
    is caused by the window itself, not by starting somewhere else.

Warming is applied by time of day, because that is how warming actually arrives:
    night minimum temperatures have risen faster than daytime maxima, and under a
    95 F ceiling the nights are the only hours with headroom left. In this August
    window 75% of daylight hours are already at or above 95 F, so warming them is
    almost inert, while night air averages 91.7 F and can still take a few degrees
    before it caps out.

    The ceiling itself is 95 F throughout: 86 F is the maize convention, and
    sorghum's optimum runs 30-35 C (86-95 F), so the conventional cap truncates at
    the very bottom of sorghum's optimal range.

    The field record anchors the baseline, so the scenario is scaled by the same
    ratio the anchoring implies - the calibration is carried over, not discarded.
    """
    if not rows or (upper_cap == 86.0 and offset == 0.0 and night_warming == 0.0):
        return rows

    def accrue(cap: float, shift: float, night_shift: float = 0.0) -> list[float]:
        out, running = [], 0.0
        for row in rows:
            # Darkness is the warming target; daylight hours keep their own shift.
            warmed = row["temperature"] + shift
            if night_shift and row["radiation"] <= 0.0:
                warmed += night_shift
            running += max(0.0, (min(max(warmed, lower), cap) - lower) / 24.0)
            out.append(running)
        return out

    baseline = accrue(upper_cap, 0.0, 0.0)
    scenario = accrue(upper_cap, offset, night_warming)
    field_gain = rows[-1]["gdd"] - rows[0]["gdd"]
    ratio = (field_gain / baseline[-1]) if baseline[-1] > 0 else 1.0
    start = rows[0]["gdd"]
    out = [{**row, "gdd": start + scenario[i] * ratio} for i, row in enumerate(rows)]
    print(f"heat scenario: cap {upper_cap:.0f} F, offset {offset:+.0f} F, "
          f"night warming {night_warming:+.0f} F -> {scenario[-1] * ratio:.1f} GDD "
          f"accumulated, {(scenario[-1] / baseline[-1] - 1) * 100:+.1f} % vs the same "
          f"ceiling with present-day nights ({baseline[-1] * ratio:.1f} GDD)", flush=True)
    return out


def spread_heat_over_full_day(rows: list[dict]) -> list[dict]:
    """Re-time each day's heat gain across all twenty-four hours.

    `gdd_field_cum` hands the day's heat out in proportion to solar radiation,
    so it is perfectly flat overnight and the plants freeze between dusk and
    dawn. That is wrong for growth. Extension in grasses follows the
    temperature of the stem apex, which during vegetative growth sits deep in
    the whorl at or below the soil line, and in a well-watered plant it
    commonly runs *faster* after dark, once transpiration stops and turgor
    recovers. Light gates assimilation, not expansion.

    So keep every day's total exactly where the weekly field record anchors it,
    and redistribute it within the day in proportion to the hourly thermal
    contribution - which is what the 86/55 method integrates in the first
    place.
    """
    by_day: dict = {}
    for row in rows:
        by_day.setdefault(row["moment"].date(), []).append(row)

    out, running = [], 0.0
    for day in sorted(by_day):
        hours = by_day[day]
        increment = max(0.0, hours[-1]["gdd"] - running)
        weights = [max(0.0, h["gdd_raw"]) for h in hours]
        total = sum(weights)
        share = 0.0
        for hour, weight in zip(hours, weights):
            # Uniform if the whole day sat below the base temperature.
            share += (weight / total) if total > 0 else (1.0 / len(hours))
            out.append({**hour, "gdd": running + increment * share})
        running += increment
    return out


def draw_growth_panel(draw, size, history, scale, ink, total_frames, caption_font,
                      load_font, screen_order=None):
    """Culm tip height over the window, one line per genotype.

    Culm tip height is derived from internodes, which only ever elongate, so the
    lines cannot go backwards - unlike the bounding-box height, which a leaf
    arching over can pull down several centimetres while the plant is still
    growing.

    Each line is direct-labelled with its letter and current value, so identity
    never rests on colour alone, and the legend doubles as the map from a plant's
    position on screen to its line.
    """
    if not history:
        return
    width, height = size
    pad = max(12, height // 40)
    panel_w = max(250, int(width * 0.27))
    panel_h = max(150, int(height * 0.30))
    left, top = pad, height - pad - panel_h
    small = load_font(max(11, height // 52))
    title = load_font(max(12, height // 46))

    legend_h = int(small.size * 1.9)
    plot = (left + int(small.size * 2.9), top + int(title.size * 2.1),
            left + panel_w - int(small.size * 4.4), top + panel_h - legend_h)

    draw.rectangle((left, top, left + panel_w, top + panel_h), fill=VIZ_SURFACE)
    draw.rectangle((left, top, left + panel_w, top + panel_h), outline=VIZ_BORDER)
    draw.text((left + int(small.size * 0.8), top + int(title.size * 0.55)),
              "culm tip height  (m)", font=title, fill=VIZ_MUTED)

    low, high = scale
    span = max(1e-6, high - low)

    def to_y(metres):
        return plot[3] - (metres - low) / span * (plot[3] - plot[1])

    def to_x(index):
        return plot[0] + index / max(1, total_frames - 1) * (plot[2] - plot[0])

    step = 0.1 if span <= 0.6 else (0.25 if span <= 1.4 else 0.5)
    mark = math.ceil(low / step) * step
    while mark <= high + 1e-9:
        y = to_y(mark)
        draw.line((plot[0], y, plot[2], y), fill=VIZ_GRID)
        label = f"{mark:.1f}"
        draw.text((plot[0] - small.size * 0.6 - small.getlength(label), y - small.size * 0.62),
                  label, font=small, fill=VIZ_MUTED)
        mark += step

    latest = history[-1]
    for name in sorted(ink):
        if name not in latest:
            continue
        run = [(to_x(i), to_y(frame[name]["tip"])) for i, frame in enumerate(history)
               if name in frame]
        if len(run) > 1:
            draw.line(run, fill=ink[name], width=2)
        x, y = run[-1]
        # 8px end marker, with a surface ring so overlapping lines stay separable.
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=VIZ_SURFACE)
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ink[name])
        # Direct label in ink, never in the series colour.
        draw.text((x + small.size * 0.65, y - small.size * 0.62),
                  f"{name} {latest[name]['tip']:.2f}", font=small, fill=VIZ_INK)

    order = [g for g in (screen_order or sorted(ink)) if g in latest]
    x = left + int(small.size * 0.8)
    y = top + panel_h - legend_h + int(small.size * 0.35)
    draw.text((x, y), "left to right:", font=small, fill=VIZ_MUTED)
    x += small.getlength("left to right:") + small.size * 0.7
    for name in order:
        draw.ellipse((x, y + small.size * 0.22, x + small.size * 0.55,
                      y + small.size * 0.77), fill=ink[name])
        x += small.size * 0.8
        draw.text((x, y), name, font=small, fill=VIZ_INK)
        x += small.getlength(name) + small.size * 0.75


def resample_weather(rows, minutes_per_frame: int, first, last):
    """Interpolate the hourly record onto a finer, evenly spaced timeline.

    A few days at fine resolution is the safe way to show a sunrise: the
    brightness cycle then takes many seconds of playback rather than a few
    frames, so it reads as dawn breaking instead of a flash.
    """
    inside = [r for r in rows if first <= r["moment"] <= last]
    if len(inside) < 2:
        raise SystemExit("the weather window needs at least two hourly records")
    out, step = [], timedelta(minutes=minutes_per_frame)
    moment, index = inside[0]["moment"], 0
    while moment <= inside[-1]["moment"]:
        while index + 1 < len(inside) - 1 and inside[index + 1]["moment"] <= moment:
            index += 1
        lower, upper = inside[index], inside[index + 1]
        span = (upper["moment"] - lower["moment"]).total_seconds()
        share = ((moment - lower["moment"]).total_seconds() / span) if span else 0.0
        out.append({
            "moment": moment,
            "gdd": lower["gdd"] + share * (upper["gdd"] - lower["gdd"]),
            "radiation": lower["radiation"] + share * (upper["radiation"] - lower["radiation"]),
            "temperature": lower["temperature"] + share * (upper["temperature"]
                                                           - lower["temperature"]),
        })
        moment += step
    return out


def vec3(evo, values) -> object:
    result = evo.Vec3()
    result.x, result.y, result.z = (float(v) for v in values)
    return result


def scene_bounds(records):
    def read(record, name):
        value = getattr(record, name)
        return float(value.x), float(value.y), float(value.z)

    lows = [read(r, "geometry_min_position") for r in records]
    highs = [read(r, "geometry_max_position") for r in records]
    return (tuple(min(v[i] for v in lows) for i in range(3)),
            tuple(max(v[i] for v in highs) for i in range(3)))


def fixed_camera(low, high, aspect, fov_deg, elevation_deg, azimuth_deg, margin):
    """Held still through the whole sequence so the plants grow within the frame."""
    centre = [(low[i] + high[i]) * 0.5 for i in range(3)]
    span_y = high[1] - low[1]
    span_ground = max(high[0] - low[0], high[2] - low[2])
    half = max(span_y * 0.5, span_ground * 0.5 / max(aspect, 1e-3))
    distance = half / math.tan(math.radians(fov_deg) * 0.5) * margin

    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    target = (centre[0], low[1] + span_y * 0.42, centre[2])
    position = (target[0] + distance * math.cos(elevation) * math.cos(azimuth),
                low[1] + distance * math.sin(elevation) + span_y * 0.18,
                target[2] + distance * math.cos(elevation) * math.sin(azimuth))
    return position, target, (0.0, 1.0, 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", type=int, choices=(6, 7), default=7)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--plastochron", type=float, default=PLASTOCHRON_GDD,
                        help="GDD per phytomer; 100 matches the measured leaf timing")
    parser.add_argument("--start-gdd", type=float, default=200.0,
                        help="before the first field observation at 980 GDD")
    parser.add_argument("--end-gdd", type=float, default=None,
                        help="defaults to the field record's last week")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fov", type=float, default=36.0)
    parser.add_argument("--elevation", type=float, default=13.0)
    parser.add_argument("--azimuth", type=float, default=0.0,
                        help="the three plants are separated along Z, so 0 (viewing "
                             "from +X) shows them side by side; 90 stacks them")
    parser.add_argument("--margin", type=float, default=1.30)
    parser.add_argument("--spacing", type=float, default=0.76,
                        help="metres between the three plants")
    parser.add_argument("--ground-size", type=float, default=600.0)
    parser.add_argument("--quality", type=int, default=5)
    parser.add_argument("--hold", type=int, default=15,
                        help="extra frames held on the mature canopy at the end")
    parser.add_argument("--no-panel", action="store_true",
                        help="omit the plant-height and newest-leaf readout")
    parser.add_argument("--no-overlay", action="store_true",
                        help="omit the GDD / day readout burned into each frame")
    parser.add_argument("--gdd-per-day", type=float, default=10.0,
                        help="descriptor value, for converting GDD to days")
    parser.add_argument("--weather", action="store_true",
                        help="drive growth and sun from the hourly AZMet record, so heat "
                             "units only accrue while the sun is up")
    parser.add_argument("--weather-csv", type=Path, default=HOURLY_WEATHER)
    parser.add_argument("--hours-per-frame", type=int, default=3)
    parser.add_argument("--weather-from", default=None,
                        help="ISO date; restrict the weather window (the full season "
                             "packs 85 day-night cycles into one clip and strobes)")
    parser.add_argument("--weather-to", default=None, help="ISO date, inclusive")
    parser.add_argument("--heat-source", choices=("thermal", "solar"), default="thermal",
                        help="thermal spreads each day's heat over all 24 hours, so growth "
                             "continues overnight as it does in the field. solar confines it "
                             "to daylight hours - visually intuitive but not how extension "
                             "works. Daily totals are identical either way")
    parser.add_argument("--upper-cap-f", type=float, default=86.0,
                        help="upper temperature cap for heat accrual. 86 is the maize "
                             "convention the field record uses; 95 is the top of "
                             "sorghum's optimum and accrues about a fifth more heat")
    parser.add_argument("--temp-offset-f", type=float, default=0.0,
                        help="degrees added to air temperature. Near-inert in August "
                             "here - most hours are already above the cap")
    parser.add_argument("--panel-min", type=float, default=None,
                        help="fix the panel's lower axis bound. Two videos meant to be "
                             "compared must share one scale, or the comparison lies")
    parser.add_argument("--panel-max", type=float, default=None,
                        help="fix the panel's upper axis bound")
    parser.add_argument("--night-warming-f", type=float, default=0.0,
                        help="degrees added to air temperature during darkness only. "
                             "Night minimums have warmed faster than daytime maximums, "
                             "and under a 95 F ceiling the nights are the only hours "
                             "here with headroom left")
    parser.add_argument("--scenario-label", default=None,
                        help="short tag burned into the frame so a pair of videos "
                             "can be told apart")
    parser.add_argument("--minutes-per-frame", type=int, default=None,
                        help="resample the hourly record to this step, for a few days at "
                             "high resolution. Keep the whole window under a handful of "
                             "days so each dawn takes seconds of playback, not frames")
    parser.add_argument("--hours-of-day", default=None,
                        help="comma-separated local hours to keep each day, e.g. 11,13,15. "
                             "Several daylight hours per day give smooth motion without the "
                             "flicker of a full day-night cycle")
    parser.add_argument("--daily-at-hour", type=int, default=None,
                        help="keep one frame per day at this local hour. Use for a whole "
                             "season: 85 day-night cycles in one clip is a strobe, and "
                             "sampling at midday shows the growth without it")
    parser.add_argument("--clear-sky-radiation", type=float, default=0.95,
                        help="hourly solar radiation treated as full sun, for scaling brightness")
    parser.add_argument("--steady-light", action="store_true",
                        help="hold the sun at one hour of the day for every frame. Sampling "
                             "several hours per day makes the picture swing dark-bright-dark "
                             "a few times a second, which is a strobe; this removes it")
    parser.add_argument("--steady-hour", type=float, default=13.0,
                        help="local hour the sun is held at")
    parser.add_argument("--dap-from", type=float, default=6.0,
                        help="days after planting to open on, before the seedlings appear")
    parser.add_argument("--dap-to", type=float, default=85.0)
    parser.add_argument("--logistic", action="store_true",
                        help="pace height by the fitted 2024 logistic curve instead of "
                             "letting it track heat units directly")
    parser.add_argument("--logistic-r", type=float, default=LOGISTIC_R)
    parser.add_argument("--logistic-tmid", type=float, default=LOGISTIC_T_MID)
    parser.add_argument("--sun-arc", action="store_true",
                        help="run a Nishita-atmosphere sunrise-to-sunset across the sequence")
    parser.add_argument("--sun-cycles", type=float, default=1.0,
                        help="how many sunrise-to-sunset passes over the whole video")
    parser.add_argument("--sun-peak", type=float, default=72.0,
                        help="peak solar elevation in degrees; ~72 is Maricopa in midsummer")
    parser.add_argument("--sun-floor", type=float, default=-4.0,
                        help="elevation the arc starts and ends at; below 0 is below the horizon")
    parser.add_argument("--sun-azimuth-start", type=float, default=95.0)
    parser.add_argument("--sun-azimuth-end", type=float, default=265.0)
    parser.add_argument("--sky-resolution", type=int, default=512)
    parser.add_argument("--gif", action="store_true")
    parser.add_argument("--warmup-frames", type=int, default=6)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    if args.output is None:
        args.output = (Path(__file__).parent / "abc-growth"
                       / f"genotypeABC_week{args.week}_growth.mp4")
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    weeks = field_weeks()
    if args.end_gdd is None:
        args.end_gdd = max(g for _, g in weeks.values())
    descriptors = stage_descriptors(args.week, args.plastochron, args.end_gdd)
    print(f"thermal axis: plastochron {args.plastochron:.0f} GDD, "
          f"maturity {args.plastochron * MATURITY_RATIO:.0f}, "
          f"target {args.end_gdd:.0f} GDD", flush=True)
    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402
    from sorghum_4x10_presentation import (  # noqa: E402
        DEFAULT_PROFILE, apply_photo_grade, configure_lighting, set_ground_extension,
    )
    import imageio.v2 as imageio  # noqa: E402
    import numpy as np  # noqa: E402
    from PIL import Image, ImageDraw, ImageFont  # noqa: E402

    def load_font(pixels: int):
        for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, pixels)
            except OSError:
                continue
        return ImageFont.load_default()

    caption_font = load_font(max(14, args.height // 26))

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(packages), str(TEMPLATE_SCENE)):
        raise SystemExit(f"failed to load {TEMPLATE_SCENE}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("template scene never became idle")

    if hasattr(evo, "RemoveParbarContext"):
        evo.RemoveParbarContext()

    # One row per genotype, one plant each: A, B and C side by side as in the field.
    labels = [f"Genotype{g}" for g in GENOTYPES]
    if int(evo.ConfigureSorghumLsPlantingGrid(labels, 1, args.spacing, args.spacing)) != 3:
        raise SystemExit("expected 3 planting markers")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != 3:
        raise SystemExit("failed to instantiate the three plants")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != 3:
        raise SystemExit("failed to sit the plants on the ground")
    if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, SEED)) != 3:
        raise SystemExit("failed to bind the genotype descriptors")

    evo.ConfigureSorghumLsLeafMeshQuality(
        LEAF_VERTICAL_SUBDIVISION_M, LEAF_HORIZONTAL_SUBDIVISIONS, False, True, False)
    # These descriptors are fitted to a measured endpoint, and snapshot morphology
    # forces the full topology at ANY GDD - every frame would come out mature.
    # Disabling it hands development back to the growth model.
    if int(evo.SetSorghumLsFinalizeSnapshotMorphology(False)) != 3:
        raise SystemExit("failed to disable snapshot morphology")
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise SystemExit("failed to establish the soil context")

    if not args.sun_arc:
        configure_lighting(evo, DEFAULT_PROFILE)
    elif not hasattr(evo, "SetNishitaSky"):
        raise SystemExit("binding missing SetNishitaSky; rebuild PyDigitalAgriculture")
    if not int(evo.ConfigurePresentationGroundExtension(
            True, args.ground_size, DEFAULT_PROFILE.ground_texture_repeat_m,
            DEFAULT_PROFILE.ground_extension_grid_spacing_m)):
        set_ground_extension(evo, True, DEFAULT_PROFILE)

    # Pass 1: regenerate at the endpoint purely to frame the camera on the mature
    # canopy, so the plants grow into a fixed shot rather than the shot chasing them.
    if int(evo.GrowSorghumLsPlantsToGdd(args.end_gdd, SEED, True)) != 3:
        raise SystemExit("failed to grow to the endpoint")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("endpoint geometry never became idle")
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    low, high = scene_bounds(records)
    for record in sorted(records, key=lambda r: float(r.global_position.z)):
        print(f"  mature {record.cultivar}: {float(record.plant_height_m):.2f} m", flush=True)

    # Camera sits on +X looking toward -X with up=+Y, so right = forward x up = -Z:
    # the plant with the largest z appears leftmost.
    by_z = sorted(records, key=lambda r: float(r.global_position.z), reverse=True)
    screen_order = [r.cultivar.replace("Genotype", "") for r in by_z]
    order_caption = "  ".join(screen_order) + "   (left to right)"
    print(f"  screen order: {order_caption}", flush=True)

    position, target, up = fixed_camera(low, high, args.width / args.height, args.fov,
                                        args.elevation, args.azimuth, args.margin)
    if not evo.SetMainCameraLookAt(vec3(evo, position), vec3(evo, target),
                                   vec3(evo, up), float(args.fov)):
        raise SystemExit("failed to place the camera")

    # Pass 2: rewind to the start, then Advance monotonically through the sequence.
    if args.steady_light:
        # One frame per step along the season, every one lit at the same hour, so
        # brightness drifts slowly with the date instead of cycling within a day.
        daily_gdd = {}
        for entry in load_hourly_weather(args.weather_csv, 1, args.heat_source):
            daily_gdd[(entry["moment"].date() - PLANTING_DATE).days] = entry["gdd"]
        day_numbers = [args.dap_from + (args.dap_to - args.dap_from) * i / max(1, args.frames - 1)
                       for i in range(args.frames)]
        known = sorted(daily_gdd)

        def gdd_on(day_number: float) -> float:
            lower = max([d for d in known if d <= day_number], default=known[0])
            upper = min([d for d in known if d >= day_number], default=known[-1])
            if upper == lower:
                return daily_gdd[lower]
            share = (day_number - lower) / (upper - lower)
            return daily_gdd[lower] + share * (daily_gdd[upper] - daily_gdd[lower])

        weather = []
        for day_number in day_numbers:
            moment = (datetime.combine(PLANTING_DATE, datetime.min.time())
                      + timedelta(days=day_number))
            moment = moment.replace(hour=int(args.steady_hour),
                                    minute=int((args.steady_hour % 1) * 60),
                                    second=0, microsecond=0)
            weather.append({"moment": moment, "gdd": gdd_on(day_number),
                            "radiation": 1.0, "temperature": 0.0})
        gdds = [w["gdd"] for w in weather]
        print(f"steady light at {args.steady_hour:.0f}:00, {len(weather)} frames, "
              f"day {args.dap_from:.0f} to {args.dap_to:.0f} after planting", flush=True)
    elif args.weather:
        weather = load_hourly_weather(args.weather_csv, args.hours_per_frame, args.heat_source)
        weather = [w for w in weather if w["gdd"] <= args.end_gdd + 1e-6]
        if args.weather_from:
            start_day = datetime.fromisoformat(args.weather_from).date()
            weather = [w for w in weather if w["moment"].date() >= start_day]
        if args.weather_to:
            end_day = datetime.fromisoformat(args.weather_to).date()
            weather = [w for w in weather if w["moment"].date() <= end_day]
        if args.minutes_per_frame:
            hourly = load_hourly_weather(args.weather_csv, 1, args.heat_source)
            if args.weather_to:
                last_day = datetime.fromisoformat(args.weather_to).date()
                hourly = [w for w in hourly if w["moment"].date() <= last_day]
            # Accrue the scenario across the whole record up to the window's end,
            # so the divergence has had the season to build.
            hourly = apply_heat_scenario(hourly, args.upper_cap_f, args.temp_offset_f,
                                         args.night_warming_f)
            if args.weather_from:
                first_day = datetime.fromisoformat(args.weather_from).date()
                hourly = [w for w in hourly if w["moment"].date() >= first_day]
            if not hourly:
                raise SystemExit("the weather window is empty")
            weather = resample_weather(hourly, args.minutes_per_frame,
                                       hourly[0]["moment"], hourly[-1]["moment"])
            days = (weather[-1]["moment"] - weather[0]["moment"]).total_seconds() / 86400.0
            seconds = len(weather) / max(args.fps, 1e-6)
            print(f"sub-hourly: {len(weather)} frames every {args.minutes_per_frame} min, "
                  f"{days:.1f} days over {seconds:.0f} s of playback "
                  f"= {days / max(seconds, 1e-6):.2f} day-night cycles per second", flush=True)
            gdds = [w["gdd"] for w in weather]
            args.hours_of_day = None
            args.daily_at_hour = None
        if args.hours_of_day:
            wanted = {int(h) for h in args.hours_of_day.split(",")}
            weather = [w for w in weather if w["moment"].hour in wanted]
        if args.daily_at_hour is not None:
            chosen, seen = [], set()
            for entry in weather:
                day = entry["moment"].date()
                if day in seen:
                    continue
                if entry["moment"].hour == args.daily_at_hour:
                    chosen.append(entry)
                    seen.add(day)
            weather = chosen
        if not weather:
            raise SystemExit("the weather window is empty")
        gdds = [w["gdd"] for w in weather]
        print(f"weather: {len(weather)} frames, every {args.hours_per_frame} h, "
              f"{weather[0]['moment'].date()} to {weather[-1]['moment'].date()}", flush=True)
    else:
        weather = None
        gdds = [args.start_gdd + (args.end_gdd - args.start_gdd) * i / max(1, args.frames - 1)
                for i in range(args.frames)]
    if args.logistic:
        # Days after planting for each frame: real dates when the weather record
        # is driving, otherwise spread evenly across the season.
        if weather is not None:
            day_numbers = [(w["moment"].date() - PLANTING_DATE).days
                           + (w["moment"].hour * 60 + w["moment"].minute) / 1440.0
                           for w in weather]
        else:
            day_numbers = [85.0 * i / max(1, len(gdds) - 1) for i in range(len(gdds))]

        probe, fractions = build_height_schedule(evo, gdds, SEED, args.max_wait_frames)
        first = logistic_fraction(day_numbers[0], args.logistic_r, args.logistic_tmid)
        last = logistic_fraction(day_numbers[-1], args.logistic_r, args.logistic_tmid)
        span = max(1e-6, last - first)
        paced = []
        for day_number in day_numbers:
            share = (logistic_fraction(day_number, args.logistic_r, args.logistic_tmid)
                     - first) / span
            paced.append(gdd_for_fraction(probe, fractions, share))
        # Advance is monotonic, so never let the schedule step backwards.
        for index in range(1, len(paced)):
            paced[index] = max(paced[index], paced[index - 1])
        gdds = paced
        print(f"logistic pacing: r={args.logistic_r}, t_mid={args.logistic_tmid:.1f} DAP, "
              f"heat range {gdds[0]:.0f} to {gdds[-1]:.0f}", flush=True)

    def read_growth() -> dict:
        """Plant height and newest-collar height per genotype, from the live scene.

        The collar of the uppermost fully expanded leaf is the standard field
        measurement, and it is the one that steps each time a leaf finishes
        extending - so the two curves together separate steady stem extension
        from discrete leaf appearance.
        """
        out = {}
        for record in evo.GetSorghumLsPlantSceneMetadata(True):
            axes = list(record.axes)
            main = None
            for axis in axes:
                if int(axis.axis_id) == 0:
                    main = axis
                    break
            if main is None and axes:
                main = max(axes, key=lambda a: float(a.culm_tip_height_m))
            out[record.cultivar.replace("Genotype", "")] = {
                "tip": float(main.culm_tip_height_m) if main else 0.0,
            }
        return out

    # Probe both ends of the window so the panel's vertical scale is fixed for
    # the whole video. An axis that rescales as it fills makes a slow climb look
    # like a fast one.
    panel_scale = None
    if not args.no_overlay and not args.no_panel:
        if int(evo.GrowSorghumLsPlantsToGdd(gdds[-1], SEED, True)) != 3:
            raise SystemExit("failed to probe the end of the window")
        evo.WaitForProjectIdle(args.max_wait_frames)
        ending = read_growth()
        if int(evo.GrowSorghumLsPlantsToGdd(gdds[0], SEED, True)) != 3:
            raise SystemExit("failed to probe the start of the window")
        evo.WaitForProjectIdle(args.max_wait_frames)
        starting = read_growth()
        low_m = min(v["tip"] for v in starting.values())
        high_m = max(v["tip"] for v in ending.values())
        margin = max(0.02, 0.08 * (high_m - low_m))
        panel_scale = (max(0.0, low_m - margin), high_m + margin)
        if args.panel_min is not None or args.panel_max is not None:
            panel_scale = (args.panel_min if args.panel_min is not None else panel_scale[0],
                           args.panel_max if args.panel_max is not None else panel_scale[1])
        print(f"  panel scale: {panel_scale[0]:.2f} to {panel_scale[1]:.2f} m", flush=True)

    if int(evo.GrowSorghumLsPlantsToGdd(gdds[0], SEED, True)) != 3:
        raise SystemExit("failed to rewind to the start")

    scratch = args.output.with_name(f".{args.output.stem}.frame.png")
    writer = imageio.get_writer(args.output, fps=args.fps, codec="libx264",
                                quality=args.quality, macro_block_size=8)
    written = 0
    first_frame_max = 0
    last_frame = None
    gif_frames = [] if args.gif else None
    history: list[dict] = []
    # Okabe-Ito: legible to the common forms of colour blindness.
    genotype_ink = GENOTYPE_INK
    def place_sun(fraction: float) -> tuple[float, float]:
        """Sun elevation and azimuth at a point through the video.

        A half-sine carries elevation from just below the horizon up to the peak
        and back, while azimuth sweeps east to west, so the shadows rotate as
        well as lengthen.
        """
        phase = (fraction * args.sun_cycles) % 1.0
        elevation = args.sun_floor + (args.sun_peak - args.sun_floor) * math.sin(math.pi * phase)
        azimuth = args.sun_azimuth_start + (args.sun_azimuth_end - args.sun_azimuth_start) * phase
        return elevation, azimuth

    for index, gdd in enumerate(gdds):
        if weather is not None:
            moment = weather[index]["moment"]
            elevation, azimuth = solar_position(moment)
            # Scale the beam by how much radiation actually reached the ground that
            # hour, so overcast days read dimmer than clear ones.
            clarity = min(1.0, weather[index]["radiation"] / max(args.clear_sky_radiation, 1e-6))
            if not evo.SetNishitaSky(azimuth, max(elevation, -6.0), 1.0, DEFAULT_PROFILE.gamma,
                                     args.sky_resolution, True, 3.0 * max(clarity, 0.0)):
                raise SystemExit("failed to build the Nishita sky")
        elif args.sun_arc:
            elevation, azimuth = place_sun(index / max(1, len(gdds) - 1))
            if not evo.SetNishitaSky(azimuth, elevation, 1.0, DEFAULT_PROFILE.gamma,
                                     args.sky_resolution, True, 3.0):
                raise SystemExit("failed to build the Nishita sky")
        if index and gdd > gdds[index - 1] + 1e-9:
            if int(evo.AdvanceSorghumLsPlantsToGdd(gdd, SEED, True)) != 3:
                raise SystemExit(f"failed to advance to {gdd:.0f} GDD")
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise SystemExit(f"geometry never became idle at {gdd:.0f} GDD")
        evo.LoopFrames(args.warmup_frames)
        if not evo.CaptureCurrentScene(args.width, args.height, str(scratch), args.warmup_frames):
            raise SystemExit(f"capture failed at {gdd:.0f} GDD")
        apply_photo_grade(scratch, scratch, DEFAULT_PROFILE)
        image = Image.open(scratch).convert("RGB")
        if panel_scale is not None:
            history.append(read_growth())
            if index == 0:
                for name in sorted(history[0]):
                    print(f"  opening {name}: culm tip {history[0][name]['tip']:.3f} m",
                          flush=True)
        if not args.no_overlay:
            draw = ImageDraw.Draw(image)
            pad = max(12, args.height // 40)
            if weather is not None:
                stamp = weather[index]["moment"].strftime("%Y-%m-%d   %H:%M")
            else:
                reached = [w for w, (_, g) in weeks.items() if g <= gdd]
                stamp = f"week {reached[-1]}" if reached else "pre-season"
            lines = [f"{stamp}      {gdd:.0f} GDD"]
            if args.scenario_label:
                lines.append(args.scenario_label)
            for offset, line in enumerate(lines):
                y = pad + int(caption_font.size * 1.25) * offset
                font = caption_font if offset == 0 else load_font(max(12, args.height // 40))
                draw.text((pad + 2, y + 2), line, font=font, fill=(0, 0, 0))
                draw.text((pad, y), line, font=font,
                          fill=VIZ_INK if offset == 0 else VIZ_MUTED)
            if panel_scale is not None:
                draw_growth_panel(draw, image.size, history, panel_scale,
                                  genotype_ink, len(gdds), caption_font, load_font,
                                  screen_order)
        array = np.asarray(image)
        if index == 0:
            first_frame_max = int(array.max())
        last_frame = array.copy()
        writer.append_data(array)
        written += 1
        if gif_frames is not None:
            gif_frames.append(Image.fromarray(last_frame))
        if (index + 1) % 20 == 0 or index + 1 == len(gdds):
            heights = [float(r.plant_height_m) for r in evo.GetSorghumLsPlantSceneMetadata(True)]  # noqa: E501
            print(f"  {index + 1}/{len(gdds)}  gdd={gdd:6.0f}  "
                  f"tallest={max(heights):.2f} m", flush=True)
    scratch.unlink(missing_ok=True)
    for _ in range(max(0, args.hold)):
        writer.append_data(last_frame)
        written += 1
        if gif_frames is not None:
            gif_frames.append(Image.fromarray(last_frame))
    writer.close()

    if first_frame_max == 0:
        raise SystemExit("frames came back black")

    print(f"wrote {args.output} ({written} frames, "
          f"{args.output.stat().st_size / 1e6:.1f} MB)", flush=True)

    if args.gif:
        gif = args.output.with_suffix(".gif")
        images = gif_frames
        palette = images[-1].convert("P", palette=Image.ADAPTIVE, colors=256)
        quantised = [im.quantize(palette=palette, dither=Image.FLOYDSTEINBERG) for im in images]
        quantised[0].save(gif, save_all=True, append_images=quantised[1:],
                          duration=int(round(1000.0 / max(args.fps, 1e-3))), loop=0, optimize=True)
        print(f"wrote {gif} ({gif.stat().st_size / 1e6:.1f} MB)", flush=True)

    evo.Terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
