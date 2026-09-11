# Methods: diurnal PAR normalization and scan-date selection

## Data and preprocessing

One-Hz calibrated PAR from two PARbar ceptometers (device A, device B), Maricopa
Agricultural Center, 2021-06-29 to 09-23. Each device carries three bars: `above`
(top, above-canopy reference), `at` (mid-canopy), `below` (bottom). Device B's
second and third channels are transposed in the acquisition script; the
calibration coefficients are applied accordingly, so column `above` for B derives
from the b2 parameters and `at` from b3.

Device is perfectly aliased with genotype and with plot pair: **device A = Pawaga
(plots 7415/7416 at position Y), device B = BTx623 (plots 7411/7412 at position
Y)**. Any A-vs-B contrast is therefore simultaneously a genotype, plot, and
instrument contrast; the figure is descriptive, not a genotype test.

Records are grouped into 36 **deployment segments** — maximal runs of continuous
1 Hz recording, split wherever the inter-record gap exceeds 1 s. Segment is the
unit of installation: bar height was reset at each move, with dates unrecorded.

The 1 Hz stream is reduced to **per-minute medians** of each channel before any
further computation (median, not mean, to suppress single-sample dropouts).

## Solar geometry (external covariate)

Solar elevation and azimuth are **computed, not measured** — no sensor on the
instrument reports them, so they cannot be circular with the PAR values they are
used to screen:

    import pvlib
    LAT, LON, ALT, TZ = 33.0685, -111.9727, 356.0, 'Etc/GMT+7'
    loc = pvlib.location.Location(LAT, LON, tz=TZ, altitude=ALT)
    idx = pd.date_range('2021-06-28', '2021-09-26', freq='60s', tz=TZ)
    sp  = loc.get_solarposition(idx)          # apparent_elevation, azimuth
    cs  = loc.get_clearsky(idx, model='ineichen')   # ghi, dni, dhi

`apparent_elevation` (refraction-corrected) is joined to the per-minute PAR table
on timestamp. Timestamps are Arizona time (MST, no DST). The geometry was
validated against data that never entered it: computed sunrise versus first light
in the PARbar record over 87 days gives a median offset of 0 min (IQR -1 to +4);
the independent AZMET pyranometer tracks computed sin(elevation) at r2 = 0.751
over 1,107 daylight hours.

## Screening

Two screens are applied, and they serve different purposes.

**Validity screen (transmittance only).** A solar panel mounted on the same mast
occludes roughly 40% of the top bar's length once the sun passes solar azimuth
~246-254 deg, depressing the above-canopy reading by up to 35%. Because
transmittance divides by that reading, transmittance is computed **only** where

    solar_azimuth < 245 deg  AND  solar_elevation > 30 deg

The 245 deg cutoff is azimuthal, not clock-based, because the shading edge sits at
fixed azimuth (the elevation at which it occurs varies 37-62 deg across the
season). Applying it as a time-of-day rule would be wrong.

**Quality screen.** Excluded throughout: seven segments with a collapsed
above-canopy channel (`A_X_2, A_X_7, B_X_0, B_X_1, B_X_6, B_X_7, B_X_8`), two
whole-season fault days (2021-07-30, 2021-08-30), and any minute with
`above <= 50 umol m-2 s-1`. The last removes only 5 of 24,127 minutes because the
elevation screen already excludes low sun; it is retained for reproducibility, not
because it is load-bearing.

The **top-bar panels are NOT validity-screened** — they show the full day
deliberately, so the reader can see the afternoon shading rather than have it
silently removed. Only the transmittance panels are restricted.

## Normalization to daily peak

Each device is normalized by **its own** peak on **that day**:

    peak[date, device] = quantile(above[date, device], 0.99)
    above_norm         = above / peak[date, device]

Three properties of this choice matter.

1. **The 99th percentile, not the maximum.** The maximum is a single-minute
   statistic and is sensitive to cloud-edge enhancement, where forward scattering
   briefly pushes irradiance above the clear-sky value. The 0.99 quantile of
   ~700-760 daylight minutes per device-day discards roughly the top 7 minutes.

2. **Per-device, not pooled.** Device B reads 6-9% lower than A on the top bar
   (an irradiance-dependent gain difference, not a constant offset). Normalizing
   each device by its own peak removes that gain difference exactly, leaving only
   curve **shape** to be compared. This is why a date with a large A-vs-B offset
   is not disqualified — the offset cancels.

3. **Computed over all daylight minutes at the plotted position**, before the
   azimuth/elevation validity screen. On 2021-07-26 both bars were moved to
   position X at ~17:55; those trailing minutes are excluded from the date
   entirely (see below), and their removal changes the 99th percentile by
   <0.1% because they are all low evening values.

Normalized curves are then binned to **15-minute intervals** (median within bin),
and bins with fewer than 8 contributing minutes are dropped.

Canopy transmittance is the simple ratio of simultaneous readings on the same
device, computed per minute before binning:

    tau = below / above          (retained only where 0.001 < tau < 1.5)

Because numerator and denominator are read by the same instrument at the same
instant, tau is insensitive to both device gain and incident irradiance — no
normalization is applied to it.

## Scan-date selection

Three dates were selected: **2021-07-26, 2021-08-22, 2021-09-21 — all at position
Y** (Pawaga plots 7415/7416, BTx623 plots 7411/7412).

Selection was **not** by eye. Starting from the 87 season dates, a date was
eligible if, on that date, both devices (i) recorded at a **single** position for
the whole day, (ii) were at the **same** position as each other, (iii) had AZMET
daily clearness index kt > 0.90 with zero precipitation and a `clear` daily sky
class, (iv) had full-day coverage (first record before 07:30, last after 17:30),
and (v) used no segment on the fault list. Sky class comes from the AZMET station,
never from the PARbars, so the selection is independent of the instrument under
test. **21 dates** met these criteria — 19 at position Y and only 2 at position X,
which is why the comparison is at Y: holding position constant across all three
dates is possible only there.

From those 21, one date was taken per month to span the season. August and
September were unambiguous (2021-08-22, kt = 0.978; 2021-09-21, kt = 0.985 — the
highest clearness in their respective months). July required a tie-break.

**The July tie-break, and a correction.** 2021-07-08 was selected first and then
rejected. Its normalized top-bar curve showed two sharp dips confined to device B;
at 12:25 device B's top bar read 944 umol m-2 s-1 while device A read 2853 at the
same minute, with AZMET reporting kt = 0.947 (clear) and device B's below-canopy
channel essentially unchanged. A sky event would move both devices; this moved
one, so it is a transient instrument fault, and it propagated into spurious
transmittance spikes reaching 0.58.

July dates were therefore ranked by an explicit agreement statistic — the fraction
of valid-window minutes where the B/A top-bar ratio departs by more than 20% from
its own daily median:

| Date | Position | B/A excursions |
|---|---|---|
| **2021-07-26** | **Y** | **0.00%** |
| 2021-07-27 | X | 1.09% |
| 2021-07-17 | X | 1.11% |
| 2021-07-01 | Y | 1.14% |
| 2021-07-08 | Y | 10.99% |

2021-07-08 is an order of magnitude worse than any other candidate. 2021-07-26 is
the only date with zero excursions and is at position Y. Note the criterion is
**agreement in shape**, not agreement in level: 2021-07-26 has the largest B/A
offset of the five (0.906) yet still wins, because per-device peak normalization
removes level differences.

**Position purity.** On 2021-07-26 both bars were moved from Y to X at ~17:55.
Those 82-83 trailing minutes per device (peak 495 umol m-2 s-1) are **excluded**;
all plotted values for all three dates come from position Y only. The other two
dates have no such tail.

## Selected dates

| Date | kt | Precip | Peak PAR, Pawaga | Peak PAR, BTx623 | Valid window | tau Pawaga | tau BTx623 |
|---|---|---|---|---|---|---|---|
| 2021-07-26 | 0.939 | 0 mm | 2682.6 | 2460.5 | 8.25-14.25 h | 0.265 | 0.247 |
| 2021-08-22 | 0.978 | 0 mm | 2588.4 | 2484.4 | 8.50-14.75 h | 0.283 | 0.248 |
| 2021-09-21 | 0.985 | 0 mm | 2345.4 | 2200.3 | 9.00-15.50 h | 0.208 | 0.179 |

Peak PAR in umol m-2 s-1; tau is the median over the valid window. The valid
window lengthens by 30 min from July to September and shifts later at both ends:
the azimuth cutoff is reached later in the day as the season progresses, gaining
more than the later morning elevation crossing loses.

![Normalized diurnal profiles on the three scan dates]({{artifact:art_935ad85c-1c1c-433b-857e-514cc00f001e}})

After normalization the two devices' top-bar curves agree to a median absolute
difference of 0.010-0.018 across the day, confirming that both bars see the same
sky once gain is removed. Transmittance separates on all three dates, with Pawaga
above BTx623 by +0.019 to +0.035. The transmittance traces are visibly noisier
than the top-bar traces; this is sunfleck variation in the below-canopy signal,
which is real canopy structure rather than instrument noise.

## Reproducibility

Environment: Python 3.13, pandas, numpy, scipy, pvlib (Ineichen clear-sky model).
Inputs: `par_1hz_long.parquet` (13,540,750 rows, segment-indexed),
`solar_geometry_1min.parquet`, `sky_daily.parquet` (AZMET-derived), and
`azmet_enriched.parquet` (station az06). Outputs:
`three_scan_dates_profiles.csv` (15-min binned values for all six curves, with
elevation, azimuth, bin count and validity flag) and
`three_scan_dates_summary.csv` (the selection table above).
