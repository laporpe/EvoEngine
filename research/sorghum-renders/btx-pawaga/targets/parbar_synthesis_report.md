# PARbar ceptometer behaviour, Maricopa AZ 2021

Devices **A** and **B**, locations **X** and **Y**, 1 Hz, 2021-06-29 to 09-23.
13,540,750 records across 36 deployment segments. Calibrated at season start against an
Apogee SQ-521-SS quantum sensor. Independent reference: AZMET station az06 (2,160 h, no missing solar).

---

## Summary of answers

| Question | Answer |
|---|---|
| Is the top bar measuring unimpeded PAR? | **No.** Three separable failures: +25-35% absolute scale excess, a fixed afternoon obstruction past solar azimuth ~247 deg, and episodic above-channel collapses. |
| Precision of the device, in PAR units? | **Four tiers**, 0.088 / 0.74 / 32.9 / 86.0 umol m-2 s-1. The right one depends on the comparison. |
| Variation between devices A and B? | **B/A = 0.930** on the top bar (-6.7%), but transmittance B/A = 0.964 (CI 0.908-1.029, spans 1) - the device effect **cancels in ratios**. |
| Variance from location vs device? | **Location dominates**: 24.2% vs 0.04% of transmittance variance. |
| X-Y difference in below-canopy PAR? | **-35 umol m-2 s-1** (CI -118 to +52) after sun-angle adjustment. |
| Is it less than device precision? | **Yes** - below the 66 umol m-2 s-1 day-scale threshold. But state it as "not detectable at this precision". |
| Change in precision over time? | **No.** Stable on every tier at matched irradiance. |
| Top-bar drift at solar noon? | **Not estimable** this season (elevation-DOY collinear at r=-0.99). |
| Calibration drift across the season? | **Yes, relative: +2.0%/30 d**, attributable to **device A** losing sensitivity. |
| Can the devices tell Pawaga from BTx623? | **Precision yes, design no.** Genotype is perfectly aliased with device, and Pawaga's two plots differ by 1.9-3.5x the genotype contrast. A replication limit, not a sensor limit. Biomass rules out canopy density as the cause of that plot difference. |

---

## 1. Design: a swap, not a parallel deployment

The single most consequential structural fact. Reconstructing continuous recording blocks from
the timestamps gives 36 segments. Across the season the two bars are **co-located ~1,700 h** and at
**different locations for only 3.24 h** (2021-07-30 09:26-12:40).

![Deployment timeline]({{artifact:art_5fe83d46-f667-4918-9913-888d0e06a452}})

Consequences that shape every result below:

- **Device A vs B is cleanly estimable** - same time, same location, second-by-second pairing.
- **Location X vs Y is never measured simultaneously**, so it is confounded with time, sky and canopy.
- **No bar ever stays put as a reference**, which is why the AZMET station is load-bearing.
- When co-located, A and B sat in **different plots 5-10 m apart east-west**. Their top bars share the
  same sky (clean device contrast); their below bars sample different canopy (device bias + plot, entangled).

There are **17 X-Y transitions per device (34 in total)**, of which 30 are usable (gap <= 180 min;
the other 4 span multi-day weather outages).

The top bar was **raised at each move** (dates unrecorded), so *segment* is the analysis unit. Of the 34
transitions only 9 have >= 2 clear days either side and are testable; just 3 show significant steps and
all are <4%, so height resets did not produce large exposure changes.

---

## 2. The top bar is not measuring unimpeded PAR

### 2.1 Absolute scale: both bars read high

On clear high-sun hours the direct (no-intercept) ratio of top-bar PAR to solar radiation is
**2.76 (A)** and **2.56 (B)** umol J-1 against **~2.05 expected** for a quantum sensor: a **+35% / +25% excess**.

The excess is **shared** (B/A = 0.938), so it points at the common calibration procedure rather than one
bad bar. A single shared rescale of ~0.773 removes the common part.

> **A pure scale error cancels in every ratio.** Transmittance, A-vs-B contrasts, X-vs-Y contrasts,
> inversion rates and step changes are all unaffected. Only absolute PAR values and any energy-balance
> use require rescaling. Do **not** rescale before computing ratios.

The ratio is **not flat in elevation** - it rises ~11% from the 40-55 deg band to >65 deg in both devices -
so a minor levelling error (~8 deg) sits on top of the scale error, and a single scalar will not fully
correct low-sun data.

### 2.2 A fixed afternoon obstruction

Initially this looked like a 29-minute clock offset. It is not. Separating the morning and evening
limbs of the daily curve is decisive:

| Crossing (50% of daily max) | Offset vs clear-sky model |
|---|---|
| Morning | **-0.3 min** (on time) |
| Evening | **-65.3 min** (early) |
| Day span | shortened by **58 min** |
| AZMET, same days | +3.4 / +3.2 min (on time) |

A clock error translates the whole curve leaving the span unchanged; this is **one-sided truncation**.
Cross-correlation lag against clear-sky GHI is ~0.0 min for all three channels, and within-segment
(weekly) drift of that lag is 0.02 min/day - **no sawtooth**, consistent with the reported weekly clock
correction and ~10 s observed accuracy.

![Shading diagnosis]({{artifact:art_5acc3b89-b276-4a50-a824-16caffda57ed}})

Three diagnostics identify the cause:

| Test | Result | Rules out |
|---|---|---|
| Edge position across months | fixed at azimuth **246-254 deg** (SD 4.3) while elevation at edge varies 37-62 deg (SD 11) | cosine/tilt error, canopy growth |
| Depth vs elevation at fixed azimuth | no trend with elevation: 0.53-0.71 across 10-60 deg, and the *shallowest* loss is at the *lowest* elevation | **a pole** - its shadow lengthens as 1/tan(elev), so depth would deepen monotonically at low sun |
| Occluded fraction required | **~40% of bar length** (diffuse fraction 0.17) | a few-cm pipe (max ~5-10%) |

All three channels break at the same azimuth (241-253 deg), the signature of one structure shading the
whole mast. Present in June already, so not canopy growth. Appears on **99% of device-days at both locations**.

Two caveats on the onset azimuth. The sharp *cliff* is at 246-254 deg, but it is preceded by a gentle sag
beginning near 200 deg (normalized signal 0.98 at 200, 0.91 by 244), so the onset value depends on the
threshold used: a strict 95%-of-plateau criterion places it at 203 deg (A) and 232 deg (B), while a
85%-of-baseline criterion on coarser monthly bins ranged 176-256 deg across device-months. The
**cliff position is the robust feature**; a single onset number is not. The conservative operational
cutoff below is chosen accordingly.

**The pole-self-shading hypothesis is not supported in its specific form.** A pole shading a bar on the
45/225 deg axis predicts a dip centred near 225 deg; the observed profile is *flat* there (within 5% of
baseline) and only breaks 22 deg further west. A broad planar occluder fits better (r2 0.52 vs 0.26 for
device B), consistent with the **solar panel** mounted on the same pole - but even that model leaves most
of device A's variance unexplained, so the exact geometry is not reconstructible from the data alone.
What *is* firm is the empirical envelope.

> **Usable window for unimpeded-PAR reference: solar azimuth < 245 deg** (hour angle < +1.6 h,
> roughly before 13:35 MST mid-season), which excludes ~35% of daylight minutes. Afternoon
> transmittance against the raw top bar is **biased by +13% (A) / -9% (B) at 1.5-2.5 h past noon,
> +47%/+15% at 2.5-3.5 h, and +50%/+40% at 3.5-4.5 h** - predominantly inflation, but note device B's
> near-band value is a small deflation, so the bias is not uniformly positive. It is unusable beyond
> ~1.5 h past solar noon. Propagate the *azimuth* cutoff, not a clock time - the azimuth is season-stable.

### 2.3 Episodic channel collapses

`at > above` occurs in 10.9% of A-X records and 12.9% of B-X versus 1.5-1.6% at Y. The rate does **not**
rise through the season (p=0.39; device B actually declines), so **canopy overtopping is not the cause**.

The faults are **day-scale and episodic**, not gradual: 79.7% of segment-days have <1% of midday minutes
inverted, while 5.1% exceed 50%. (Those percentages are over the **158** segment-days with >60 midday
minutes; `inversion_segment_days.csv` holds all 169 rows, with `n_mid` present to reproduce the filter.) The mechanism is the **above channel collapsing**, not `at` rising -
in A_X_7 the above/GHI ratio drops 68% while `at` changes 25%. That segment flips abruptly on
**2021-08-30** (2.70 -> 0.72 with `at` unchanged), which looks like an occluded or disconnected bar.
Affected: A_X_2, A_X_7, B_X_0, B_X_1, B_X_6, B_X_7, B_X_8. A further collapse day, **2021-07-30 (A_Y_4)**,
reads 1.34 against ~2.9 on neighbouring days.

![Top bar validation]({{artifact:art_eff7dec6-6361-406d-a1d5-28c51b13f4a3}})

### 2.4 A hardware finding worth checking

**Device A's `at` channel reads low season-wide at both locations** (at/above 0.601 at X, 0.605 at Y vs
B's 0.822/0.806; p=0.0014, no seasonal trend). Its night offset is **2.541** against 4.86-5.41 for all
five other channels. That pattern is consistent with a different sensor, gain, or wiring on that specific
bar. The raw data cannot resolve it - **recommend inspecting the physical bar and its calibration record.**

---

## 3. Precision: four tiers, not one

![Precision summary]({{artifact:art_16ca7fe0-f612-4584-9ac0-7a13687daa09}})

At a midday reference of 2,353 umol m-2 s-1:

| Tier | Quantity | PAR units | % | Correct benchmark for |
|---|---|---|---|---|
| 1 | Night electronic noise (SD) | **0.088** | 0.004% | Detection limit only |
| 2a | 1 Hz repeatability, top bar | **0.737** | 0.031% | Whether a short-term fluctuation is real |
| 2b | Same-device day-to-day stability | **32.9** | 1.40% | **X-vs-Y move brackets** |
| 3 | Cross-device top-bar bias | **86.0** | 3.65% | Any across-device comparison |

**Choosing the wrong tier is the main analytical trap here.** A move bracket spans a gap of tens of
minutes but is judged against day-scale instability, so a same-device difference must exceed roughly
**2 x 32.9 = 66 umol m-2 s-1 (2.8%)** to be distinguishable. Using the 1 Hz figure would understate the
required threshold by ~45x.

Four refinements that matter in practice:

1. **Noise is proportional, not additive** - sigma ~ 0.033% of reading (proportional model r2 0.37-0.93;
   additive-only r2 0.00). Thresholds must scale with irradiance.
2. **Cross-device bias is irradiance-dependent** - B-A is ~0 below 500, -89 at 1250, -185 at 2600
   umol m-2 s-1. Any device correction must be **multiplicative** (B/A = 0.9572, CI 0.9448-0.9611),
   never a subtraction.
3. **Day-scale stability varies 7.5-270** across the 18 segment-device units; 32.9 is the *median*.
   Use the per-segment value where available.
4. **Below-canopy variability is ~20x the top bar's** but is **real sunfleck flicker the ceptometer
   resolves correctly** - signal, not an instrument precision limit.

Two measurement caveats from the same analysis: MAD-based sigma is **degenerate** on this data
(quantization makes 38-53% of residuals exactly zero in the relevant bins), so a scaled mean absolute
deviation was used; and the digitization step is **dual-range**, coarsening by a factor of exactly 10
above a channel-specific reading of 355-434, with the precise trigger not identifiable from the
delivered CSVs.

---

## 4. Device vs location variance

![Variance decomposition]({{artifact:art_b748c2d9-0fd1-4f21-95ce-004d3e261d92}})

As % of observed variance:

| Component | Transmittance | Below-canopy PAR | Status |
|---|---|---|---|
| Residual | 54.1% | 46.7% | separable |
| Segment | 33.5% | 24.0% | entangled with location and bar height |
| **Location (X vs Y)** | **24.2%** | 15.0% | entangled with plot canopy |
| Overlap / non-orthogonality | 20.7% | 25.8% | entangled by construction |
| Sky | 3.4% | 22.2% | separable |
| Season | 5.5% | 14.4% | separable from location |
| Day | 0.05% | 1.8% | separable |
| **Device (A vs B)** | **0.04%** | 1.7% | separable |

**Location outweighs device by roughly 600x in transmittance.** The device effect is substantial in
absolute PAR (B-A = -144.5 umol m-2 s-1, -6.7%) but transmittance B/A = 0.964 with **CI 0.908-1.029
spanning 1** - it cancels in the ratio.

Two notes on reading this table. The **seven substantive components** sum to **120.7%** (transmittance) and
**125.8%** (below-canopy PAR) - deliberately >100%, because correlated regressors cannot partition variance
additively. The overlap row (20.7% / 25.8%) *quantifies* that excess and must **not** be added to the other
seven: doing so double-counts and gives ~141%/~152%. And the seasonal confound proved **small and measured, not assumed**: adding a day-of-year
spline moves the location coefficient only from 0.0527 to 0.0560 (+6.3%), because the bars alternated
X-Y 18 times over 87 days, leaving location nearly orthogonal to calendar time.

Location effect: **Y - X = +0.056 transmittance** (CI 0.028-0.084, p=7.3e-5), i.e. +28% relative to the X
baseline of 0.199; below-canopy **+146 umol m-2 s-1** (CI 66-226, p=3.3e-4).

Validated two ways: a **placebo test** applying the same estimator to the sky-normalised *top* bar - which
sees the same sky at both locations, so the true effect must be zero - returns +0.61% (CI -2.80 to +4.21),
bounding residual artifact at ~4% relative; and a design-based estimate from the 30 move brackets gives
+0.0665 (CI 0.039-0.088), agreeing with the model.

> **What location is still confounded with:** X and Y are different field plots, so this term is
> site + canopy + genotype + planting in unknown proportion. The bars never revisited a location with a
> different canopy, so nothing separates site micrometeorology from the standing canopy. Location is
> therefore a **bound, not a point estimate: 17.6-50.0%** of transmittance variance (11.5-27.7% for
> below-canopy PAR).

---

## 5. The move-bracket comparison

![Move brackets]({{artifact:art_36b2edf1-55c4-4eb9-b693-7bffeb50c079}})

**The bracket design is less clean than it appears.** AZMET incident radiation changes by a median
**29.8%** across the 30 usable gaps (range 0.6-86.4%; only 1 of 30 stable within 5%), and sky class
differs between sides in 10 of 30. Moves were done in the morning while the sun climbed fastest.

**Balancing directions does not cancel the trend.** With 16 X->Y and 14 Y->X the direction-contrast
component is -167 umol m-2 s-1, *larger* than the pooled estimate itself (-133), so naive pooling leaves
a bias about the size of the effect.

| Endpoint | Unadjusted | Sun-angle adjusted |
|---|---|---|
| Below-canopy PAR | -133 (CI -228, -40), p=0.005 | **-35 (CI -118, +52), p=0.40** |
| Transmittance | - | **-0.028 (CI -0.094, +0.039)** |
| AZMET-normalized | - | -0.039 umol J-1 (CI -0.140, +0.066) |

The nuisance slope is strongly determined: **-15.9 umol m-2 s-1 per degree** of solar elevation
(CI -21.3 to -10.5).

**Answer: the X-Y difference (35 umol m-2 s-1) is smaller than the day-scale precision threshold
(66 umol m-2 s-1).** But the CI (-118 to +52) is *wider* than the precision band, so the honest
statement is **"no difference detectable at this precision"**, not "the locations are equal".

Four checks support the null:

1. **Independent cross-check** - the transmittance-vs-elevation slope fitted inside the bracket
   regression (-0.0048/deg) matches the separately measured within-segment geometric sensitivity
   (+0.0034/deg) in magnitude, from two unrelated calculations.
2. **Window sensitivity is diagnostic** - adjusted estimates are stable at 15/30/60 min (-40, -35, -37)
   while unadjusted ones grow monotonically (-116, -133, -161), as expected if the sun is the driver.
3. **Clear-sky-only brackets give -2.0** (CI -104, +101); brackets with incident radiation stable
   within 15% give -13 (CI -171, +156).
4. **The two devices disagree in sign** (A -72, B +2.8). A real location difference should appear in
   both, since both made the same moves on the same days.

Per-bracket differences range -721 to +467 umol m-2 s-1 and 24 of 30 exceed the 66 threshold
individually - but they are ordered almost perfectly by change in solar elevation, so the per-bracket
table **must not** be read as 30 independent location estimates.

An early/late season split gives -110 (CI -205, -1) versus +22 (CI -84, +140). That barely excludes
zero, and the season split is also a solar-declination split, so it **cannot** be attributed to canopy
development. **A hypothesis, not a finding.**

Note the bracket and model estimates are not in conflict: the brackets spend most of their power
correcting a large nuisance and have n=30; the model uses 158 segment-days with sky and season controls.

---

## 6. Drift and stability over the season

![Drift panels]({{artifact:art_9325a03f-f96d-46ba-a84e-fa5b6bd2a668}})

### 6.1 Zero offset: no meaningful drift

Night offsets reproduce the calibration intercepts to within 0.0002 umol m-2 s-1 on all six channels.
Drift is -0.0012 to +0.0004 per 30 d, significant on 3 of 6 channels but **~40x below the 0.049
quantization step** - statistically detectable, physically negligible. **Electronics/dark-current drift
is ruled out** as a source of daytime error.

Night *dispersion* is **temperature-coupled, not season-coupled**: night air temperature falls 1.3 degC
per 30 d, sigma responds to temperature on 4 of 6 channels, and once temperature is in the model the
apparent seasonal trends mostly vanish.

### 6.2 Gain drift at solar noon: not estimable

**This supersedes the question as posed.** Noon solar elevation and day-of-year are collinear at
**r = -0.99** (noon elevation falls 80.1 to 56.6 deg over 87 days), so the noon window cannot separate
gain drift from the known levelling error. Iso-elevation morning bands do not rescue it - the azimuth at
which a fixed elevation occurs migrates 91 -> 136 deg across the season.

Under the one specification that breaks the degeneracy (a tilt-plus-drift model whose tilt terms are
constrained by within-day shape carrying no date information), neither device shows drift:
**A -1.5%/30 d** (CI -8.8 to +6.4, p=0.70), **B -0.5%/30 d** (CI -6.4 to +5.8, p=0.88).

Segment fixed effects **cannot** be used to control height steps here: with 11 segments over 87 days they
absorb nearly all seasonal variation (r2 -> 0.99) and the slope sign-flips.

### 6.3 Relative calibration drift: real, and attributable

The **B/A top-bar ratio rises +2.03%/30 d** (CI +0.40 to +3.66, p=0.016; robust regression +1.86%,
p=0.043) on 31 clear device-days, paired second-by-second on identical minutes inside the unshaded window.
This ratio **cancels solar geometry exactly**, which is why it survives where the absolute tests fail.

**The location dependence I flagged in reconnaissance was an artefact** - and in the opposite direction to
my initial reading. Unscreened means were X=0.9335, Y=0.9681 (X *lower*, not higher), with Y's spread
inflated by outliers (2021-07-30 at 1.87; a 4-day block near 0.88). After restricting the ratio to
0.8-1.15 the locations agree (0.9335 vs 0.9348, p=0.52) and the slope is unchanged (+2.18%). **This
removes the objection that would have undermined the drift claim.**

**Attribution: device A.** Each device's own clear-sky-referenced ratio gives A **-3.56%/30 d**
(CI -5.28 to -1.84, p=0.0002) versus B -1.18%/30 d (CI -2.70 to +0.34, p=0.12); against AZMET,
A -4.75% (p<0.0001) and B -2.25% (p=0.0013). Device A's top bar is losing sensitivity relative to B.
The ~2%/30 d **difference** is the defensible quantity; single-device magnitudes retain the geometry
confound and are upper bounds.

### 6.4 Precision does not degrade

![Precision over time]({{artifact:art_3b543271-f8e2-4427-b1f2-31162f2305ce}})

Stable on every tier once irradiance is matched:

- **Night noise**: 2 of 6 channels show a significant trend and **both decrease**; other four null.
- **1 Hz repeatability** at matched irradiance: 0.025-0.032% of reading throughout;
  A -0.037 %pt/30 d (p=0.26), B +0.001 (p=0.38).
- **Day-to-day stability**: non-monotonic (A 2.3/5.6/4.0%, B 3.4/1.1/3.1% Jul/Aug/Sep), no trend
  (p=0.67, 0.92).

Stratifying by irradiance is **essential**: device B's 2500-3000 bin holds 38.6k seconds in July but
only 211 in September, so an unstratified monthly sigma would move purely from changing radiation.

---

## 7. Can the devices distinguish Pawaga from BTx623?

**Short answer: the precision is sufficient; the DESIGN is not.** The limit is replication, not the sensor.

### 7.1 Genotype is perfectly aliased with device

Plot-genotype key (`data/naming-key.xlsx`), with each bar sited between two plots:

| File | Station | Position | Plots | Genotype |
|---|---|---|---|---|
| taX_cal | A | X | 7407 / 7408 | Pawaga |
| taY_cal | A | Y | 7415 / 7416 | Pawaga |
| tbX_cal | B | X | 7403 / 7404 | BTx623 |
| tbY_cal | B | Y | 7411 / 7412 | BTx623 |

Both flanking plots agree in **all four** cases, so what each bar measured is unambiguous. But
**Station A only ever measured Pawaga and Station B only ever measured BTx623.**

This follows from the field layout rather than any labelling error. Plots run in **four-plot genotype
blocks** (7401 BTx642; 7402-7405 BTx623; 7406-7409 Pawaga; 7410-7413 BTx623; 7414-7416 Pawaga), and every
bar sat in a block *interior* - sound practice, since it avoids straddling a genotype boundary. However
positions X and Y are **8 plots apart, exactly the block period**, so any station holding a fixed offset
remains inside one genotype for the whole season. The choice that made each individual placement clean is
what produced the aliasing.

Consequence: every A-vs-B difference is simultaneously a genotype difference and an instrument difference,
and **no data anywhere in the season separates them.**

### 7.2 The apparent genotype contrast flips sign between positions

Pairing the two genotypes on the same date and position (screened window: azimuth < 245 deg, elevation
> 30 deg, clear sky, collapsed segments and known fault days excluded):

| Subset | n paired days | Pawaga - BTx623 transmittance | 95% CI |
|---|---|---|---|
| Pooled | 31 | **+0.034** | 0.016 to 0.046 |
| At position X | 4 | **-0.042** | -0.095 to -0.018 |
| At position Y | 27 | **+0.039** | 0.026 to 0.054 |

The position x genotype **interaction (0.081) is 2.4x the main effect (0.034)**, and the sign flip persists
across all four screening specifications tried (clear only; clear+variable; azimuth < 220; elevation > 45).
A contrast that reverses depending on where it is measured is not a genotype effect.

### 7.3 Three candidate explanations, all testable - and all three fail

![Genotype confounding]({{artifact:art_c8c078e8-a9ea-4422-afec-400c2a569483}})

**Not the device.** Within each genotype, *both* plots were measured by the *same* device (Pawaga X and Y
both by station A; BTx623 X and Y both by station B), so a within-genotype position difference **cannot**
be an instrument effect:

| Genotype | Device | tau at X | tau at Y | Difference |
|---|---|---|---|---|
| Pawaga | A | 0.157 | 0.274 | **+0.117** (bootstrap CIs disjoint) |
| BTx623 | B | 0.230 | 0.234 | +0.004 (CIs overlap) |

**Not an east-west field gradient.** Station A sits **+4 plots from station B in the same direction at
both positions**, so a monotonic spatial gradient must yield a consistent sign for A-B. Observed: A-B is
negative at X (0 of 4 days positive) and positive at Y (89% of 27 days). A gradient cannot reverse when the
offset direction never changes.

**Not wind.** Regressing within-day hourly transmittance deviations on AZMET wind speed gives no
significant effect at any bar (largest |slope| 0.029 per m/s, p=0.18; all r2 < 0.03). Daytime wind is also
modest (median 1.8 m/s) and broadly distributed in direction, not dominantly easterly in this record.

**Not a date artefact.** Y-days adjacent to the four X-days (doy 200-224) give +0.014 versus -0.042 at X,
so the flip is positional, not temporal.

### 7.4 The effect is real and reproducible, but biomass does NOT explain it

Decomposing the transmittance ratio into its numerator and denominator (both normalised by clear-sky GHI)
locates the cause below the canopy rather than in the reference channel:

| Genotype | above-canopy X -> Y | below-canopy X -> Y |
|---|---|---|
| Pawaga | +4.6% | **+71.0%** |
| BTx623 | -1.1% | -4.4% |

**The effect is reproducible across re-installations.** At segment level - each segment being an independent
re-mounting of the bar - all four Pawaga X installations (tau 0.096, 0.140, 0.118, 0.158) fall below all
seven Pawaga Y installations (0.206-0.316), Mann-Whitney p=0.0061, spanning July to September. BTx623 shows
no such separation (p=0.78). So this is not a one-off mounting artefact.

**Part of the raw gap is solar-elevation mix.** X and Y segments fall on different dates with different sun
angles. Comparing within matched 2-degree elevation bins reduces the Pawaga Y/X transmittance ratio from
**1.683 pooled to 1.410** - so ~40% of the apparent difference was geometry. The 1.410 figure is robust
(identical at bin-sampling thresholds of n>=25 and n>=100).

**Biomass falsifies the canopy-density explanation.** Destructive harvest (uniform 3.3 m2 sample area;
arithmetic verified internally consistent) gives:

| Genotype | Biomass X | Biomass Y | Biomass Y vs X | Transmittance Y vs X (matched elev.) |
|---|---|---|---|---|
| Pawaga | 1182.7 g m-2 (7407/8) | 1198.4 g m-2 (7415/6) | **+1.3%** | **+41.0%** |
| BTx623 | 1308.3 g m-2 (7403/4) | 1206.2 g m-2 (7411/2) | -7.8% | -9.8% |

For **BTx623 the two agree closely** (-7.8% biomass, -9.8% transmittance) - light transmission tracks
standing biomass as expected. For **Pawaga they disagree completely**: a 1.3% biomass difference accompanies
a 41% transmittance difference. Under Beer-Lambert (tau = exp(-k x LAI)), a 1.41x transmittance ratio
requires a LAI difference of ~0.6-0.9 units (k = 0.4-0.6), which a 1.3% biomass difference cannot supply.

Pawaga's biomass is in fact remarkably uniform across all four plots (1175-1199 g m-2, CV **0.9%**), while
BTx623's is far more variable (1069-1548 g m-2, CV **16.4%**) - yet it is Pawaga that shows the large
transmittance split. The relationship runs opposite to a density explanation.

**So the mechanism is unresolved.** What is established: the Pawaga X-vs-Y difference is real (~41% after
elevation matching), reproducible across four independent installations, located in the below-canopy
channel, and **not** attributable to standing biomass. Candidates the light and biomass data cannot
separate: canopy architecture at equal mass (leaf angle, height, tillering, row closure), bar placement
within the inter-row alley, or a persistent local obstruction at the X mounting. Distinguishing these needs
LAI or canopy-architecture measurements, or a photograph of the bar in position - biomass alone cannot.

> This subsection previously attributed the difference to canopy density. The biomass data refutes that,
> and the conclusion has been revised. The **design** verdict in 7.5 is unchanged and does not depend on
> the mechanism: a within-genotype plot difference this large with n=2 plots per genotype blocks the
> genotype inference either way.

![Biomass vs transmittance]({{artifact:art_d9fda9f9-d4f6-479d-a99e-753c80e2fa54}})

### 7.5 Why the answer is "no"

| Quantity | Transmittance units |
|---|---|
| Device-bias uncertainty (transmittance ratio CI +/-6%) | 0.014 |
| Apparent genotype contrast | 0.034 |
| **Pawaga between-plot difference (same device)** | **0.117** raw; **~0.065** after elevation matching (1.41x on tau 0.157) |

Instrumentally the genotype signal is ~2.4x the device-bias uncertainty, so **the sensor is precise enough**.
But with **n = 2 plots per genotype** and a within-genotype plot difference of 0.065-0.117 - **1.9x to 3.5x**
the between-genotype contrast, depending on whether solar elevation is matched - the genotype effect is not
estimable. The plot is the experimental unit, and two of them cannot support the inference. This is a
replication limit, not a precision limit, and it holds under either figure.

**What would fix it:** rotate the stations across genotypes, so each device spends time in both Pawaga and
BTx623 blocks. Genotype would then be *crossed* with device rather than aliased, and these same instruments
would resolve a 0.034 difference comfortably. Four or more plots per genotype would additionally let
plot-to-plot variation be averaged rather than mistaken for a genotype effect.

**Open question, narrowed by the biomass data (7.4):** standing biomass is now ruled out as the cause of
the Pawaga plot difference. What remains untested is canopy architecture at equal mass (leaf angle, height,
tillering, row closure), bar placement within the alley, and a possible local obstruction at the X mount.
LAI, a canopy photograph, or an installation photo of the X bar would discriminate.

---

## 8. Assumptions

1. **Timestamps are Arizona MST (UTC-7, no DST).** Verified by lag scan against AZMET (agreement peaks
   at lag 0, r2 0.877, falling to 0.53 at +1 h).
2. **Calibration coefficients as supplied**, including the documented B2/B3 field transposition - so
   device B's delivered *Above* column carries the b2 parameters and *At* carries b3. Confirmed by night
   offsets matching -intercept/slope on all six channels.
3. **AZMET az06 represents incident radiation at the plots.** It is a pyranometer several km away, so it
   constrains sky state and incident radiation, **not** plot-level canopy conditions.
4. **~2.05 umol J-1** taken as the expected quantum PAR-to-shortwave ratio for daylight.
5. **The top bar was raised at each move**, dates unrecorded, so segment is the analysis unit.
6. **1 Hz data is massively pseudo-replicated.** All inference is at segment-day or hour level with
   bootstrapping over days; no CI or p-value is computed over raw seconds.
7. **Plot-genotype assignments** are taken from `data/naming-key.xlsx` as supplied. Each bar is treated as
   measuring the genotype of its two flanking plots, which agree in all four cases. Bars sample the alley
   between two plots, so a bar represents that plot pair rather than a single plot.
8. **Biomass** from `field_biomass_2021.csv` (destructive harvest, uniform 3.3 m2 sample area inferred from
   the g and g/m2 columns; bag-subtraction arithmetic verified). One harvest per plot, so there is no
   within-plot replicate and no season-long time course - it constrains end-of-season standing mass only,
   not canopy development or architecture.
9. **Clear-sky modelling** via pvlib Ineichen. AZMET's own clearness index (median 0.94 at high sun,
   max 1.08) confirms the model is well calibrated.

---

## 9. Recommendations for the next season

**Fix the afternoon obstruction (highest priority).** Move the solar panel north of the bar or onto a
separate stake, and photograph each mast from the west at installation. This alone recovers ~35% of
daylight hours currently unusable as an unimpeded reference.

**Rotate the stations across genotypes.** Because X and Y sit 8 plots apart and the genotype blocks are
4 plots wide, a fixed station offset never leaves its genotype - so genotype and device are perfectly
aliased and neither effect is estimable. Assign positions that put each device in both genotypes, and use
at least four plots per genotype so plot-to-plot variation can be averaged rather than mistaken for a
genotype effect.

**Add a stationary reference bar** that never moves. The deepest limitation here is that no instrument
stayed put, so location is permanently entangled with time and canopy. One fixed bar would make every
X-vs-Y contrast direct.

**Resolve the absolute calibration.** Both bars read 25-35% high against an independent pyranometer.
Re-check the Apogee SQ-521-SS procedure and units, and re-calibrate mid-season as well as at the start
so drift is measurable rather than inferred.

**Record height-adjustment dates and move times.** Undated resets forced segment-level analysis
throughout and made absolute gain drift inestimable.

**Inspect device A's at-canopy bar** (anomalous night offset 2.541, reads low season-wide) and
**device A's top bar** (losing ~2%/30 d relative to B).

**Log a level reading at each installation.** A residual ~8 deg tilt produces an 11% elevation-dependent
error that no scalar correction removes.

**If move brackets are used again**, do them near solar noon when elevation changes slowest, and record
a synchronized incident-radiation reference. Morning moves cost most of the design's power to nuisance
correction.
