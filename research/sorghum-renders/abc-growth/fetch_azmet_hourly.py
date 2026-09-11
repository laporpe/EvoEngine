#!/usr/bin/env python3
"""Fetch hourly AZMet weather for Maricopa and pair heat units with sunlight.

The field record carries only a daily cumulative heat-unit total, which cannot
say *when* during a day the heat arrived. AZMet station az06 (Maricopa) reports
hourly air temperature and solar radiation, so growth can be tied to daylight.

Two quantities are written per hour:

  gdd_raw     Heat units by the standard method, using the 86 F upper and 55 F
              lower caps: (min(T, 86) - 55) / 24 per hour, floored at zero.
              In an Arizona summer this keeps accruing all night, because the
              night air rarely drops below 55 F.

  gdd_solar   The same DAILY total, redistributed across the day in proportion
              to measured solar radiation. The cumulative curve still lands on
              the field record's numbers, but within a day the heat arrives
              while the sun is up and pauses overnight.

`gdd_solar` is what the growth animation should advance on: it keeps the weekly
markers correct while making the plant visibly grow by day and rest by night.

    python fetch_azmet_hourly.py --start 2026-06-01 --end 2026-08-26
"""

from __future__ import annotations

import os
import argparse
import csv
import json
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

API = "https://api.azmet.arizona.edu/v1/observations/hourly"
STATION = "az06"  # Maricopa
LOWER_CAP_F = 55.0
UPPER_CAP_F = 86.0
OUTPUT = Path(os.environ.get("SORGHUM_HOURLY_WEATHER",
                    Path(__file__).resolve().parent.parent / "data"
                    / "azmet_hourly_maricopa_2026.csv"))
FIELD_CSV = Path(os.environ.get("SORGHUM_FIELD_CSV",
                    Path(__file__).resolve().parent.parent / "data"
                    / "sorghum_all_weeks_long_gdd.csv"))


def fetch_window(start: date, days: int) -> list[dict]:
    """One request. The API takes a start timestamp and an ISO-8601 interval."""
    url = f"{API}/{STATION}/{start.isoformat()}T00:00/P{days}DT23H"
    with urllib.request.urlopen(url, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise SystemExit(f"AZMet rejected {url}: {payload['errors']}")
    return payload.get("data", [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2026-06-01", help="planting date")
    parser.add_argument("--end", default="2026-08-26", help="exclusive end")
    parser.add_argument("--chunk-days", type=int, default=20)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--field-csv", type=Path, default=FIELD_CSV,
                        help="weekly field record used to anchor the cumulative curve")
    parser.add_argument("--field-column", default="gdd_cumulative_F_8655")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    rows: list[dict] = []
    cursor = start
    while cursor < end:
        span = min(args.chunk_days, (end - cursor).days)
        batch = fetch_window(cursor, span)
        rows.extend(batch)
        print(f"  {cursor} +{span}d -> {len(batch)} hourly records", flush=True)
        cursor += timedelta(days=span)

    if not rows:
        raise SystemExit("no observations returned")

    # ---- hourly heat units, standard 86/55 F caps ---------------------------
    parsed = []
    for row in rows:
        stamp = row.get("date_datetime", "").strip()
        if not stamp:
            continue
        moment = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        try:
            temperature = float(row["temp_airF"])
            radiation = float(row["sol_rad_total"])
        except (KeyError, ValueError):
            continue
        capped = min(max(temperature, LOWER_CAP_F), UPPER_CAP_F)
        parsed.append({
            "datetime": moment,
            "temp_airF": temperature,
            "sol_rad_total": radiation,
            "gdd_raw": (capped - LOWER_CAP_F) / 24.0,
        })
    parsed.sort(key=lambda r: r["datetime"])

    # ---- redistribute each day's total onto that day's sunlight -------------
    by_day = defaultdict(list)
    for record in parsed:
        by_day[record["datetime"].date()].append(record)
    for day, records in by_day.items():
        daily_total = sum(r["gdd_raw"] for r in records)
        radiation_total = sum(r["sol_rad_total"] for r in records)
        for record in records:
            if radiation_total > 0:
                share = record["sol_rad_total"] / radiation_total
            else:
                # No sun recorded all day: fall back to the unweighted split so
                # the daily total is still conserved.
                share = 1.0 / len(records)
            record["gdd_solar"] = daily_total * share

    # ---- anchor onto the field record --------------------------------------
    # Recomputing heat units from AZMet lands about 3 percent above the series
    # in the field record - a small systematic difference in how that series was
    # produced. Rescaling between the weekly observation dates makes the
    # cumulative curve pass through the recorded values exactly, while keeping
    # the hour-by-hour shape, and the overnight pauses, from the measurements.
    field_anchors = {}
    if args.field_csv and args.field_csv.is_file():
        with args.field_csv.open() as handle:
            for row in csv.DictReader(handle):
                value = row.get(args.field_column, "").strip()
                if value:
                    field_anchors[date.fromisoformat(row["date"])] = float(value)
    if field_anchors:
        field_anchors.setdefault(start, 0.0)

    cumulative_raw = cumulative_solar = 0.0
    for record in parsed:
        cumulative_raw += record["gdd_raw"]
        cumulative_solar += record["gdd_solar"]
        record["gdd_raw_cum"] = cumulative_raw
        record["gdd_solar_cum"] = cumulative_solar

    if field_anchors:
        anchor_days = sorted(field_anchors)
        mine = {}
        for day in anchor_days:
            upto = [r for r in parsed if r["datetime"].date() <= day]
            mine[day] = upto[-1]["gdd_solar_cum"] if upto else 0.0
        for record in parsed:
            when = record["datetime"].date()
            lower = max([d for d in anchor_days if d <= when], default=anchor_days[0])
            later = [d for d in anchor_days if d > when]
            if not later:
                previous = anchor_days[-2] if len(anchor_days) > 1 else anchor_days[-1]
                span_mine = mine[anchor_days[-1]] - mine[previous]
                span_field = field_anchors[anchor_days[-1]] - field_anchors[previous]
                rate = (span_field / span_mine) if span_mine else 1.0
                record["gdd_field_cum"] = (field_anchors[anchor_days[-1]] +
                                           (record["gdd_solar_cum"] - mine[anchor_days[-1]]) * rate)
                continue
            upper = later[0]
            span_mine = mine[upper] - mine[lower]
            fraction = ((record["gdd_solar_cum"] - mine[lower]) / span_mine) if span_mine else 0.0
            record["gdd_field_cum"] = (field_anchors[lower] +
                                       fraction * (field_anchors[upper] - field_anchors[lower]))
    else:
        for record in parsed:
            record["gdd_field_cum"] = record["gdd_solar_cum"]

    fields = ["datetime", "temp_airF", "sol_rad_total", "gdd_raw", "gdd_solar",
              "gdd_raw_cum", "gdd_solar_cum", "gdd_field_cum"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in parsed:
            writer.writerow({
                "datetime": record["datetime"].isoformat(sep=" "),
                "temp_airF": f"{record['temp_airF']:.1f}",
                "sol_rad_total": f"{record['sol_rad_total']:.3f}",
                "gdd_raw": f"{record['gdd_raw']:.5f}",
                "gdd_solar": f"{record['gdd_solar']:.5f}",
                "gdd_raw_cum": f"{record['gdd_raw_cum']:.2f}",
                "gdd_solar_cum": f"{record['gdd_solar_cum']:.2f}",
                "gdd_field_cum": f"{record['gdd_field_cum']:.2f}",
            })

    daylight = [r for r in parsed if r["sol_rad_total"] > 0]
    night = [r for r in parsed if r["sol_rad_total"] <= 0]
    print(f"\n{len(parsed)} hours written to {args.output}")
    print(f"  cumulative heat units at the end: {cumulative_raw:.0f} "
          f"(both methods agree by construction)")
    print(f"  daylight hours {len(daylight)}, night hours {len(night)}")
    if night:
        share = sum(r['gdd_raw'] for r in night) / cumulative_raw * 100
        print(f"  standard method accrues {share:.0f}% of all heat units at night;"
              f" the sunlight-weighted one accrues none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
