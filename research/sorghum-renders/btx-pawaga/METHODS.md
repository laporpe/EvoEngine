# Materials & Methods — BTx623 / Pawaga canopy transmittance calibration in EvoEngine

> **Living document.** This is the current state of the art of the methods for this comparison.
> It must be updated whenever the pipeline, scene, screening rules, or parameter values change.
> Decision history and dead ends live in `EXPERIMENT_LOG.md`; this file describes only the
> *current* method, written so it can be lifted into a manuscript Materials & Methods section.
>
> Status legend: [EST] established · [PROV] provisional (in use, may change) · [TODO] not yet implemented

Last updated: 2026-09-10 (rev 2: field geometry, PARbar spec, status markers de-emojified)

---

## 1. Objective [EST]

Iteratively calibrate the simulated canopy geometry of two sorghum genotypes — **BTx623**
(erectophile) and **Pawaga** (planophile) — in EvoEngine so that simulated canopy transmittance
(τ) matches ceptometer (PARbar) transmittance measured in the field at Maricopa Agricultural
Center in 2021. Geometry priors for leaf dimensions, internode dynamics, and tillering are
transferred from three hand-measured genotypes (A, B, C) grown at the same site in 2026, since
no hand measurements exist for BTx623 or Pawaga in 2021.

## 2. Field experiment, 2021 [EST]

- **Site**: Maricopa Agricultural Center, AZ, "north gantry field" (33.0685 N, −111.9727 W, 356 m).
- **Planting date**: 2021-05-13.
- **Layout**: plots arranged in four-plot genotype blocks (…7402–7405 BTx623; 7406–7409 Pawaga;
  7410–7413 BTx623; 7414–7416 Pawaga…). The measured block is bordered by additional
  lower-density rows to the north and south (see aerial screenshot, 2021).
- **Plot/row geometry**: rows run **north–south** within plots; rows are ~3.5–4 m long at
  **1 m row spacing**. Per-plot stand (counted 2026, assumed similar 2021): ~30 stems including
  tiller stems, i.e. ~10–15 plants per plot (≈2–3 stems per plant). Exact planting density
  unrecorded; within-row spacing therefore [PROV] ~25–40 cm. Rows per plot: unconfirmed (§9).
- **Management**: plots were not thinned; all genotypes tillered in this environment.
  No 2021 tillering measurements exist.
- **Instrument**: two PARbar ceptometer stations (A, B), each with three bars —
  `above` (top, above-canopy reference), `at` (mid-canopy), `below` (bottom) — logging at 1 Hz,
  2021-06-29 → 2021-09-23. Calibrated at season start against an Apogee SQ-521-SS quantum sensor.
  PARbar design (Salter et al. 2019, JoVE 59447): **1 m bar with 50 PAR photodiodes**
  (Everlight EAALSDSY6444A) at **20 mm intervals**, first sensor 13.5 cm from one diffuser end;
  bar output is the mean of the 50 sensors. Bottom bar mounted near the ground (not touching);
  top bar above the canopy (raised as the canopy grew; heights unrecorded).
- **Mounting geometry** (from the field SOP, `Ceptometer Protocol.docx`): each bar is mounted in
  the furrow between two plots, diffuser coplanar to the ground, **long axis at 45° to the planted
  rows with the east end north of the west end**. Three poles per position, height increasing
  south→north; the north pole also carries a solar panel (the known afternoon occluder). Bars sit
  fully within the planted area.
- **Positions**: X = furrows 7407/7408 (Pawaga) and 7403/7404 (BTx623);
  Y = furrows 7415/7416 (Pawaga) and 7411/7412 (BTx623). Stations alternated X/Y on a
  Tue(X)/Wed(Y)/Thu(Y)/Fri(X) schedule. **Device is perfectly aliased with genotype**
  (A = Pawaga, B = BTx623 all season).

## 3. Field data quality constraints (inherited from the 2021 PARbar synthesis) [EST]

Full analysis: `targets/parbar_synthesis_report.md` and `targets/methods_normalization.md`.
Binding rules for this calibration:

1. **Use transmittance ratios only, never absolute PAR.** Both top bars read 25–35 % high
   against AZMET (shared calibration error); the error cancels in the same-device ratio
   τ = below/above.
2. **Validity screen**: τ is valid only where solar **azimuth < 245°** and **elevation > 30°**
   (a solar panel on the mast occludes ~40 % of the top bar past azimuth ~246–254°). Apply as an
   azimuth rule, never a clock-time rule.
3. **Do not use the `at` (mid-canopy) channel** for calibration: device A's `at` bar reads low
   season-wide (suspected hardware difference), and A = Pawaga, so it would bias one genotype.
4. **The genotype contrast is confounded** (genotype ⊻ device ⊻ plot pair; Pawaga's two plot
   pairs differ by 1.9–3.5× the genotype contrast). Therefore each genotype is calibrated to
   **its own plot-pair τ at position Y**; the small measured Pawaga−BTx623 difference
   (+0.019 to +0.035) is a soft check on ordering, not a hard target.
5. Excluded from targets: seven collapsed-channel segments, fault days 2021-07-30 and
   2021-08-30, minutes with above ≤ 50 µmol m⁻² s⁻¹.

## 4. Calibration targets [EST]

Three clear-sky scan dates, all at **position Y** (Pawaga 7415/7416 by device A; BTx623 7411/7412
by device B), selected by the objective funnel in `targets/methods_normalization.md`
(kt > 0.90, zero precip, single/same position, full-day coverage, no fault segments; July
tie-break by B/A top-bar excursion rate). 15-min binned diurnal profiles:
`targets/three_scan_dates_profiles.csv`.

| Date | DAP (2021) | kt | Valid window (h, MST) | median τ Pawaga | median τ BTx623 |
|---|---|---|---|---|---|
| 2021-07-26 | 74 | 0.939 | 8.25–14.25 | 0.265 | 0.247 |
| 2021-08-22 | 101 | 0.978 | 8.50–14.75 | 0.283 | 0.248 |
| 2021-09-21 | 131 | 0.985 | 9.00–15.50 | 0.208 | 0.179 |

**Secondary target — drone canopy height** [PROV]: drone-derived canopy heights per genotype on
PARbar-season dates (`targets/height_at_parbar_days.csv`). The three scan dates are absent from
the flights; nearest flights bracket them (07-23/07-28 → BTx623 ≈ 0.66–0.68 m, Pawaga ≈
0.62–0.63 m). Heights are near-equal between genotypes, BTx623 marginally taller mid-season —
consistent with erect leaves raising the apparent canopy surface while planophile leaves lower
it. Used as a relative constraint on simulated canopy-surface height (CHM-like envelope, not
stem height; drone CHM likely underestimates absolute height). The drone fIPAR columns in the
same file flip sign between genotypes across days and are NOT used for calibration.

**Fit metric** [PROV]: per date × genotype, compare simulated vs measured τ on the 15-min bins inside
the valid window. Primary statistic: bias (Δ median τ) and RMSE across bins; the *diurnal shape*
(τ vs solar elevation) must also match, since the erectophile/planophile contrast expresses as
elevation-dependence of τ. Provisional success criterion: |Δτ| ≤ 0.03 absolute and correct
elevation trend on 2021-07-26; the same descriptors (aged along the growth trajectory) should then
track 08-22 and 09-21 without re-tuning.

## 5. Growth-stage matching, 2021 targets ↔ 2026 hand measurements [PROV]

The A/B/C geometry source is the 2026 north-gantry experiment (planted **2026-06-09**; weekly
hand measurements, **week 1 = 2026-07-09 through week 8 = 2026-08-25** per
`sorghum_all_weeks_long_gdd.csv`; the tuned descriptors `Genotype*_week{6,7}.sorghumls`
correspond to 2026-08-11 and 2026-08-18).

Matching is by **cumulative GDD, °F with 86/55 caps, hourly formula
(clamp(T_F,55,86)−55)/24** — the same method as the 2026 field record's
`gdd_cumulative_F_8655`. 2021 thermal time computed from AZMET az06 hourly data (API,
start 2021-05-13 = planting): `targets/azmet_az06_2021_daily_gdd.csv`.

| 2021 scan date | cum GDD from planting | Position on 2026 week axis (field CSV GDD) | Status |
|---|---|---|---|
| 2021-07-26 | 2036 | **between week 6 (1948) and week 7 (2134), α ≈ 0.48** | [EST] direct anchor, w6/w7 blend |
| 2021-08-22 | 2810 | week 8 (2320) + 489 GDD (~1.9 weeks past end) | [TODO] extrapolation |
| 2021-09-21 | 3649 | week 8 + 1329 GDD | [TODO] validation only; senescence relevant |

Notes:
- The field CSV's `days_after_planting` column (38 on 2026-07-09) is inconsistent with the
  June 9 planting (30 d) — but its GDD column matches an AZMET June-9-origin computation to
  within ~1.5 %, so the GDD axis is trusted and the DAP column is not used.
- Because 07-26 sits almost exactly midway between measured weeks 6 and 7, the ideal geometry
  is a w6/w7 interpolation; the existing GDD-keyed `SorghumGrowthStages` machinery
  (`build_gdd_growth_stages.py`, `Apply(descriptor, time)`) can do this natively. For now the
  v-draft descriptors use week-6-anchored dimensions — the w6→w7 deltas are a few percent,
  within calibration slop.
- **Phenology**: 2036 GDD(F, 86/55) at scan 1 is at/past typical BTx623 anthesis thermal time,
  so panicles were very likely present on 2021-07-26 — the render default (panicle on) is
  therefore kept for the τ pipeline. Pawaga (photoperiod-sensitive landrace) may have flowered
  later; its panicle presence at scan 1 is less certain [PROV]. Consequence: 2021-07-26 is the **primary calibration date**; 08-22 is secondary;
09-21 is a validation/qualitative date.

## 6. Geometry priors [PROV]

- Baseline descriptor schema: `.sorghumls` (tiller_model_version: 4). Two schema variants exist:
  the HandoffTuned/A-B-C variant (extra fields: `enable_panicle`+sizes,
  `tiller_base_radial_offset`, `tiller_emergent_height`, `tiller_initiation_delay_gdd`,
  `tiller_leaf_count_ratio_quantiles`) and the GeneratedAssets/BTX-Pawaga variant (extra fields:
  `leaf_width_scale` — multiplies blade width — and `tiller_leaf_area_ratio_by_origin`). Tiller
  topology (`tiller_origin_rank_order`, `tiller_emergence_main_leaf_stages`) is identical across
  all files and transfers directly. When transferring internode_thickness, copy min AND max
  (BTX schema keeps a nonzero min; A/B/C keep min 0 with taper in the curve).
- The existing BTX/Pawaga descriptors (`GeneratedAssets/Descriptors/GrowthStage01–05/`) already
  form a **2021-dated trajectory**: GS01=2021-07-01, 02=07-14, 03=08-18, 04=08-30, 05=09-02
  (from `sorghum_asset_layout.py` DATE_ORDER). The 07-26 target falls between GS02 and GS03;
  a new stage will be authored for it.
- **E0 finding (2026-09-10)**: current BTX/Pawaga dimensional values look default-like and
  disagree with the field-tuned A/B/C week-6 values from the same site — leaf width 0.1575 m
  (identical for both genotypes; ~1.8× the A/B/C 0.082–0.094 m), ~18 phytomers (A/B/C: 13–14),
  blade length 1.09–1.28 m (A/B/C: 0.66–1.01 m), tiller floor 3 (A/B/C: 0–1, and 2026 stand
  counts imply ~1–2 tillers/plant). Dimensions are therefore re-anchored on A/B/C week 6; the
  current BTX/Pawaga **angle families are retained** as the genotype-contrast starting point
  (BTX insertion max 42° declining to 0° at top = erect; Pawaga 70° = planophile), consistent
  with the PMC8710048 phenotypic-extremes characterization.
- Of A/B/C: **A is most erect** (insertion ≈59° base → 8° top), **C is most planophile** (only
  genotype whose insertion *increases* with rank, ≈61°→79°; also the only one with panicle
  enabled at week 6); B is intermediate with very high plant-to-plant angle variance
  (dev max 49.5°). C's rank-increasing insertion curve is adopted as the Pawaga upper-canopy
  template.
- Differentiate by architecture: BTx623 ← erect leaf angles, less leaf bend; Pawaga ← planophile
  angles, more droop. Angle-family parameters remain the primary free parameters of the
  calibration (unconstrained by hand measurements).
- **Stature prior** [PROV]: drone heights (§4) show the two genotypes near-equal in canopy
  height (BTx623 marginally taller mid-season), overturning an earlier "Pawaga taller"
  assumption. v0 therefore gives both genotypes near-equal internode structure (BTx623 0.212 m
  max, Pawaga 0.207 m, GS03 curves retained, scaled ~0.95 for 07-26 vs the GS03/08-18 stage) and
  a modest blade-length split (BTx623 0.85 m, Pawaga 0.95 m). Any apparent-height difference
  should emerge from the angle families, matching the drone-observation mechanism.
- Current draft descriptor values (v0 onward) are tracked in `EXPERIMENT_LOG.md`; authored files
  live in `btx-pawaga-illumination/descriptors/` (derived from GrowthStage03 templates by
  block-scoped text edits — native formatting preserved).
- **Calibrated pair for 2021-07-26 (ensemble-validated)** [EST]:
  `BTX623_20210726_v6.sorghumls` + `Pawaga_20210726_v8.sorghumls` (aliased as `*_cal1`).
  Full-context layout, seed-ensemble statistics:
  BTx623 0.258±0.072 (n=12, 95 % CI 0.212–0.303) vs field 0.247, p=0.61;
  Pawaga 0.271±0.058 (n=31, CI 0.250–0.292) vs 0.265, p=0.58 — both statistically
  indistinguishable from the field. Ensemble-mean diurnal shape r ≈ 0.9 for both.
  NOTE: small-n (≤5 seed) medians are unreliable — midday τ is governed by the few plants
  flanking the bar; v4's apparent 3-seed convergence and the large small-n "context effects"
  did not survive n≈30 replication (layout effect on medians: Welch p=0.40/0.16; the real
  context effect is Pawaga's ensemble-mean shape, r 0.80→0.92). All reported τ use ≥8-seed
  ensembles on the full-context layout.
- Literature constraints [PROV]: PMC8710048 (3D leaf-angle GWAS, Univ. Nebraska greenhouse)
  confirms the architectural contrast — BTx623 = "reference genotype … erect leaves",
  AS 4601 Pawaga = "non-erect leaves", the two phenotypic extremes of the sorghum association
  panel — but reports no numeric trait values for either genotype (angles shown only in
  figures). Its angle convention: polar angle between leaf midrib and stem axis (≈ from
  vertical), measured in the vertical plane; panel-wide, upper leaves trend more erect than
  lower leaves. Elsewhere: BTx623 plant height ≈ 113 cm (Lubbock TX) to 155 cm (Puerto Rico);
  BTx623 is dw3-nonfunctional with small leaf angle. No published Pawaga dimensions found so
  far; Pawaga is an association-panel landrace (AS 4601).
- Tillering: present in all genotypes at this site, magnitude unknown for 2021 → tiller count is
  a bounded nuisance parameter (range from A/B/C observations), explored in sensitivity analysis
  rather than freely fit.

## 7. Simulation [TODO]

- **Engine**: EvoEngine ray-traced illumination (local build, `C:\Users\Brenda\code\EvoEngine`),
  driven through the Python binding. Starting point:
  `PythonBinding/sorghum_4x10_parbar_sensor_illumination_handoff.py` (virtual PAR-bar sensors at
  three heights, replicated seeds) — treated as work-in-progress, to be improved.
- **Pipeline architecture decisions** [EST] (from the 2026-09-10 API scoping, see log):
  - Simulated sensor output (`illumination_total_simulated`) is a *relative* luminance-weighted
    irradiance, not calibrated µmol — acceptable because the target is the ratio
    τ = below/above, which cancels units, exactly as the field methodology cancels the PARbar
    calibration error. Absolute PAR conversion is never needed.
  - The shared `sorghum_asset_layout.py` `DATE_ORDER` is **not** edited (stage numbering is
    positional — inserting a date renumbers every later GrowthStage folder and invalidates the
    existing pipeline's checkpoints/manifest). This experiment uses an **experiment-local
    layout module** and its own scene/manifest under `btx-pawaga-illumination/`.
  - Plot layout via `ConfigureSorghumLsPlantingGrid(row_genotypes, columns, column_spacing_m,
    row_spacing_m, center)` — supports 1 m rows, per-row genotype labels, arbitrary
    plants/row; the 2026 6x10 scene-builder scripts are the template for the custom
    position-Y block with neighbor plots (E1).
  - Virtual PAR bars: sensor probes are generated on the top faces of scene mesh entities
    named per the `kParbarPanels` convention (`PARBAR_{cultivar}` roots,
    `{Top,Middle,Bottom}SensorBarMesh`), probes evenly spaced along the panel's longest
    in-plane axis (count parameterized — set to **50** to match the physical PARbar). A 1 m
    bar mesh rotated 45° in the scene therefore yields the correct 45° 50-point line sampler
    with no engine changes; fallback option is a new C++ `CreateLineSensorGroup` binding
    during the planned rebuild. `EstimatePARSensors(handle, samples, bounces, ...)` runs the
    OptiX estimate.
  - **Top-bar height rule** [EST]: the above-canopy reference bars are held at world
    y = 2.30 m — well above the tallest simulated plants (≤1.7 m) — mirroring the field
    practice of raising the top bar as the crop grew. (A 2026-09-10 artifact where shrunken
    top bars sat at canopy height inflated all τ values by ~15 % rel.; see log.) If future
    descriptors grow taller than ~2 m, raise the bars again via builder pass 3.
  - The existing scientific loop never moves the sun (fixed overhead reference). The diurnal
    sweep is **new driver code**: per 15-min bin of the valid window, set the sun to the
    2021 solar position, run `EstimatePARSensors`, record per-bar scalars, τ_sim =
    below/above. NOTE: this code path's `SetSunDirection` takes a single vec3 of
    **(pitch, yaw, roll) degrees rotating (0,0,−1)** — different from the two-arg
    (azimuth, elevation) overload used elsewhere; verify angle convention against a
    solar-noon sanity check before production runs.
  - Diffuse sky is currently ambient_light_intensity 0.8 + directional light in the template
    scene — adequacy for clear-sky τ is an E3 sensitivity item (diffuse fraction ~0.15–0.2 in
    Arizona clear sky). Candidate upgrade: the locally-added `SetNishitaSky(azimuth_deg,
    elevation_deg, …)` binding (physically-based atmosphere as EnvironmentalMap + skybox,
    aims the directional light at the sun) — verify whether `EstimatePARSensors`' OptiX path
    samples the environment map for diffuse before adopting it for τ runs.
- **Scene** [PROV]: replicate the position-Y neighborhood, not an isolated plot: the flanking plot
  pair for each genotype plus the correct neighboring genotype blocks along the row axis and the
  lower-density border rows visible in the 2021 aerial image (east–west extent), so that
  neighboring-plot shading reaching the sensor is represented. The required neighborhood radius
  will be established by a scene-extent sensitivity experiment (E1 in `EXPERIMENT_LOG.md`).
- **Virtual sensor** [PROV]: a 1 m line sampler with 50 sample points at 20 mm spacing
  (matching the physical PARbar), placed in the inter-plot furrow at 45° to the rows (east end
  north of west end), horizontal, near ground level, per SOP geometry. Simulated
  τ = (mean PAR over the 50 points at below height) / (unoccluded above-canopy PAR). The
  solar-panel obstruction is **not** modeled; instead the same azimuth < 245° screen is applied
  to simulated output.
- **Sun**: `pda.SetSunDirection(azimuth_deg, elevation_deg)` per 15-min bin timestamp, solar
  position from pvlib for 2021 dates at the site coordinates. Direct + diffuse (sky dome) as per
  ray-tracer settings; ray samples ≥ 128.
- **Row geometry** [PROV]: N–S rows, 1 m row spacing, rows 3.5–4 m long, ~10–15 plants per plot
  at ~25–40 cm within-row spacing with ~2–3 stems per plant (tillers). Supersedes the old 76 cm
  placeholder from the prior genotype experiment config.

## 8. Calibration procedure [PROV]

1. **Baseline**: run current BTx623/Pawaga descriptors in the replicated scene on 2021-07-26
   bins; record τ error per bin.
2. **Sensitivity**: one-at-a-time perturbation of leaf bending/roll angle, leaf length, leaf
   width, internode length, tiller count → dτ/dparameter by solar-elevation band.
3. **Iterate**: adjust angle-family parameters first (the genotype-contrast axis), holding
   area/height near A/B/C-derived priors; re-run; compare. Manual/coordinate-descent loop with
   every iteration logged in `EXPERIMENT_LOG.md`.
4. **Validate**: apply the calibrated descriptors, aged along the growth trajectory, to
   2021-08-22 and 2021-09-21 without re-tuning; render side/top views for visual sanity against
   the aerial image.
5. Replicate stochastic seeds (plant-to-plant variation) and report simulated τ as
   mean ± SD across seeds; seed count set so the seed-SD is well below the 0.03 fit criterion.

## 9. Open questions / unconfirmed inputs

- Rows per plot (aerial image suggests plots are narrow along the E–W axis; if a plot is a
  single 1-m-wide row, the plot pair flanking each bar is two rows). Confirm from plot map or
  aerial measurement.
- Heights of the three bars above ground at position Y (top bar raised at each move,
  unrecorded). Below bar taken as near-ground [PROV]; simulated τ at ground level should be
  checked for sensitivity to ±10 cm of below-bar height.
- Which of genotypes A/B/C is architecturally closest to BTx623 / Pawaga (E0, in progress).
- GDD alignment between 2021 and 2026 seasons via AZMET API (replace DAP matching, §5).
- Phenology on the scan dates: with a May 13 planting, BTx623 may be near/post anthesis by
  07-26 (74 DAP) and certainly by 08-22; Pawaga (landrace) may flower later. Panicle
  presence/geometry affects top-of-canopy interception — needs a phenology estimate (GDD to
  anthesis) or field notes/photos.
- No published quantitative geometry for Pawaga found; its dimensions rest entirely on the
  A/B/C transfer + calibration.

## 10. Key external references

- Salter et al. 2019, JoVE 59447 — PARbar construction/specs (1 m, 50 photodiodes @ 20 mm).
- PMC8710048 — BTx623 (erect) vs AS 4601 Pawaga (non-erect) leaf-angle extremes; angle
  convention from stem axis.
- AZMET programmatic access guide (azmet.arizona.edu, Feb 2024 PDF) — hourly/daily weather for
  GDD matching.
- `targets/parbar_synthesis_report.md`, `targets/methods_normalization.md` — 2021 data quality
  and target derivation.
