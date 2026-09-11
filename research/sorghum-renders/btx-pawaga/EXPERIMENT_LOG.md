# Experiment Log — BTx623 / Pawaga transmittance calibration

Chronological record of progress, decisions, directions, and dead ends. Newest entries at the
bottom. The current-state method lives in `METHODS.md`; this file explains *how we got there*.

Planned experiment IDs are assigned here (E1, E2, …) and referenced from `METHODS.md`.

---

## 2026-09-10 — Project kickoff: targets defined, plan drafted

**Inputs assembled**
- 2021 PARbar synthesis report + normalization methods + scan-date selection
  (from `parbar_2021_scan_dates.zip`, copied to `targets/`).
- Field SOP `Ceptometer Protocol.docx` (Downloads): bar in inter-plot furrow, 45° to rows,
  diffuser horizontal, east end north; positions = plot pairs; A=Pawaga / B=BTx623 aliasing.
- 2021 aerial screenshot of the PARbar field: measured block flanked by lower-density
  border rows; user proposal to extend the simulated field east–west for realism → adopted as
  experiment E1.
- Existing infra: `sorghum_4x10_parbar_sensor_illumination_handoff.py` (virtual PAR bars,
  BTX/Pawaga cultivars) — declared work-in-progress by user, to be improved.
- Field-tuned genotype A/B/C descriptors (`HandoffTuned/`, `WeeklyTuned/` w1–w8) as geometry
  priors; no hand measurements exist for BTx623/Pawaga.

**Key decisions**
1. **Target = τ = below/above** (same device, same minute), 15-min bins, position Y only,
   screened to azimuth < 245° and elevation > 30°. NOT absolute PAR (top bars read 25–35 % high);
   NOT the `at` channel (device A `at` reads low; A aliased with Pawaga).
   Supersedes the earlier `ceptometer/ceptometer_targets.csv` fIPAR file, which used the `at`
   channel and no azimuth screen — that file is retired for calibration purposes.
2. **Three scan dates** (2021-07-26, 2021-08-22, 2021-09-21, all position Y) from the objective
   selection funnel. 07-26 = primary calibration date; 08-22 secondary; 09-21 validation.
3. **Per-genotype calibration to own plot pair**, not to the genotype *difference* — the 2021
   design aliases genotype with device and plot; Pawaga's between-plot spread (0.065–0.117 τ)
   exceeds the genotype contrast (0.034). Ordering (τ_Pawaga > τ_BTx623 at Y) kept as a soft check.
4. **Stage matching**: 2021 planting 2026-05-13 → scan dates at 74/101/131 DAP. 2026 A/B/C
   planting 2026-06-09, week 0 = 2026-07-09 (30 DAP), weekly through ~92 DAP. Week 6 (72 DAP)
   ≈ 07-26 (74 DAP) — near-perfect anchor by DAP. Later dates need trajectory extrapolation;
   plan to upgrade DAP→GDD matching using AZMET weather for both seasons.
5. Angle-family parameters (leaf bending/roll, insertion angles) = primary free parameters;
   dimensions/height held near A/B/C priors; tillering = bounded nuisance (no 2021 data, plots
   unthinned, all genotypes tiller here).
6. Two living documents created (this file + `METHODS.md`) per user requirement that the methods
   documentation never go stale and that history is kept separately.

**Planned experiments**
- **E1 — Scene extent sensitivity**: how large must the simulated neighborhood be (rows east–west,
  plots along-row, border rows) before simulated τ at the sensor stabilizes? Establishes the
  production scene. Motivated by user observation that neighboring plots affect measured
  transmittance.
- **E2 — Baseline error**: current BTx623/Pawaga descriptors, production scene, 2021-07-26 bins.
- **E3 — Parameter sensitivity**: one-at-a-time sweep (leaf bend/roll, leaf length, leaf width,
  internode length, tiller count) → dτ by elevation band.
- **E4 — Iterative calibration** on 07-26; **E5 — validation** on 08-22 / 09-21.
- **E0 (parallel) — Priors**: tabulate A/B/C week-6 descriptors vs current BTx623/Pawaga;
  extract BTx623/Pawaga traits from PMC8710048; decide the A/B/C→BTx/Pawaga transfer rule.

**Open questions sent to user** — see `METHODS.md` §9 (row spacing/azimuth, plot dims, density,
bar length/heights, GDD data for 2021).

---

## 2026-09-10 (later) — Field geometry answered; E0 complete; v0 descriptor proposal

**User answers folded into METHODS.md rev 2–3**
- N–S rows within plots, rows ~3.5–4 m long, 1 m row spacing; ~30 stems/plot incl. tillers
  → ~10–15 plants/plot (≈2–3 stems/plant, i.e. ~1–2 tillers/plant), exact density unrecorded.
- Bottom bar near ground (not touching); top bar above canopy. PARbar spec from Salter et al.
  2019 (JoVE 59447): 1 m bar, 50 photodiodes @ 20 mm, Everlight EAALSDSY6444A.
- AZMET hourly/daily via web API (guide PDF) for GDD matching.
- Emojis removed from docs (illegible on this machine) → [EST]/[PROV]/[TODO] markers.

**Literature (E0a)**
- PMC8710048 (+bioRxiv full text): BTx623 = erect reference, AS 4601 Pawaga = non-erect
  extreme; **no numeric trait values published for either**; angle convention = midrib vs stem
  axis; panel-wide, upper leaves trend more erect. BTx623 height elsewhere: ~113 cm (Lubbock)
  to 155 cm (Puerto Rico). No published Pawaga dimensions found.

**Descriptor comparison (E0b, subagent over 8 .sorghumls files + sorghum_asset_layout.py)**
- Existing BTX/Pawaga GrowthStage01–05 = a 2021-dated trajectory (07-01, 07-14, 08-18, 08-30,
  09-02). 07-26 target needs a new stage between GS02 and GS03; adding one requires touching
  DATE_ORDER in `sorghum_asset_layout.py` (pipeline validates against it).
- Current BTX/Pawaga dimensions look default-like: identical 0.1575 m leaf width (~1.8× A/B/C),
  ~18 phytomers (A/B/C 13–14), tiller floor 3, blades 1.09–1.28 m. Angles are the only real
  genotype differentiation: BTX insertion max 42° (declining to 0 at top), bending 150 max;
  Pawaga insertion 70°, bending 100.
- A/B/C week 6: A most erect (59°→8°), C most planophile (61°→79°, rank-increasing — unique)
  and only one with panicle on; B intermediate, huge angle dev (49.5°).
- Schema deltas and transfer traps recorded in METHODS §6 (leaf_width_scale multiplier,
  internode_thickness min, HandoffTuned-only fields).

**Decision — v0 draft descriptors** (dimensions ← A/B/C week 6 + stand counts; angle families ←
existing BTX/Pawaga, Pawaga upper-canopy curve ← GenotypeC template):

| Parameter | BTx623 v0 | Pawaga v0 | Source/rationale |
|---|---|---|---|
| total_phytomer_count | 14 ± 1 | 14.5 ± 1 | A/B/C week6 (13.2–14.2); PROV pending GDD check |
| leaf_blade_length max | 0.85 m | 1.05 m | A/B/C range 0.66–1.01; BTx623 compact, Pawaga tall landrace |
| leaf_blade_max_width max | 0.085 m | 0.085 m | A/B/C 0.082–0.091 (leaf_width_scale = 1) |
| internode_length max | 0.27 m | 0.32 m | height ≈1.1–1.3 m BTx623 (lit.), Pawaga taller |
| internode_thickness | min 0.013 / max 0.022 | same | A/B/C B/C ≈0.022 |
| leaf_insertion_angle | max 42°, declining curve (≈27°→0°) | max 78°, rank-increasing curve (≈60°→78°) | BTX = keep current; Pawaga = GenC template |
| leaf_bending | max 130°, curve 0.75→0 | max 110°, curve 0.8→0.4 | erect vs persistent droop in upper canopy |
| tiller_count | 2 ± 1, min 0, max 4 | 2 ± 1, min 0, max 4 | 2026 stand counts (~1–2 tillers/plant); A/B/C 2.25–2.8 |
| tiller_insertion_angle | 15° ± 3 | 30° ± 5 | erect vs spreading; A/B/C range 5–17 |
| panicle | off | off | phenology at 74 DAP unresolved (§9); BTX schema lacks fields |
| all other fields | inherit current BTX/Pawaga GS02/GS03 | inherit | waviness/roll/curling identical everywhere anyway |

Free parameters for calibration (E3/E4): insertion max + curve shape, bending max + curve,
tiller_count mean, blade length (±15 % around prior). Held fixed: widths, thickness, phytomer
count, topology.

**Next**: author v0 `.sorghumls` files, add a 2021-07-26 stage to the pipeline, GDD check of
the week6↔74-DAP anchor, then E1 scene-extent sensitivity.

---

## 2026-09-10 (evening) — Drone heights; v0 revised (equal stature) and authored

**New data**: `targets/height_at_parbar_days.csv` (drone canopy heights + fIPAR, 15 PARbar-season
dates; user may reprocess). Findings:
- Genotype heights near-equal; BTx623 marginally taller most of mid-season (e.g. 07-23:
  0.659 vs 0.619 m; 07-28: 0.678 vs 0.628 m), converging/reversing slightly by September.
  User hypothesis (adopted as interpretation): erect BTx623 leaves raise the apparent canopy
  surface; drooping/curved Pawaga leaves lower it. → **v0 revision: equal stem stature for both
  genotypes**; the earlier "Pawaga taller" assumption is dropped. Height differences must
  emerge from angles, which is itself a useful qualitative check.
- The three scan dates are not flight dates; bracketing flights used (07-23/07-28 for 07-26).
- Drone fIPAR columns flip sign across days (Cohen's d swings −2.3…+3.8) → excluded from
  calibration; drone *height* kept as a relative secondary constraint.
- Caveat: CHM heights (~0.66 m at 74 DAP) are well below literature BTx623 heights (~1.1 m+);
  treated as envelope underestimates — relative use only.

**User guidance**: GenotypeC insertion-curve template for Pawaga is "a guess among many" —
keep, but treat the curve *shape* as a first-class free parameter in E3/E4 (test flat-high
alternative). Panicles in late July 2021: possible, unrecorded → panicle on/off becomes an E3
sensitivity case rather than an assumption.

**v0 descriptors authored**: `descriptors/BTX623_20210726_v0.sorghumls`,
`descriptors/Pawaga_20210726_v0.sorghumls`. Method: copied GrowthStage03 (2021-08-18) BTX/Pawaga
templates; block-scoped text replacement (formatting preserved; every replacement asserted
unique within its block); diff-verified — only intended lines changed. Deltas vs GS03:
- Both: phytomer 17.4→14±1; leaf width max 0.1375→0.085 m (dev 0.0248→0.0153);
  internode_thickness 0.012–0.015→0.013–0.022 m; tiller_count 4±1 (3–5)→2±1 (0–4);
  internode max scaled ×0.95 (BTX 0.2226→0.212, Pawaga 0.2172→0.207) for 07-26 vs 08-18 stage.
- BTX623: blade length max 1.0872→0.85 m; bending max 150→130; tiller insertion 26.25±3.75→15±3.
  Insertion-angle family unchanged (max 42°, declining curve).
- Pawaga: blade length max 1.1111→0.95 m; insertion max 70→78 with **rank-increasing GenC-style
  curve** ([0,0.77]…[1,1.0] ≈ 60° base → 78° flag) and dev 8→18; bending max 100→110 with
  persistent-droop curve (tail 0→0.4, ≈44° at top); tiller insertion 35→30.

**Next**: install v0 as a new growth stage + DATE_ORDER entry for 2021-07-26; render side-by-side
v0 verification images (visual check vs erect/planophile expectation and drone height ordering);
GDD anchor check; then E1.

---

## 2026-09-10 (night) — v0 verification renders: architecture contrast confirmed

**Method**: `render_v0_comparison.py` (adapted from `render_genotype_weeks.py`; stages the v0
descriptors into `Assets/BtxPawagaDrafts/`, plants one row per genotype in the 2026 6x10
template scene, parbar context removed). Engine loads the v0 files cleanly ("Load legacy
SorghumLSDescriptor", no errors). Note: conda is at `C:\Users\Brenda\.miniconda3` and NOT on
PATH in Claude's shells — invoke as
`& C:\Users\Brenda\.miniconda3\Scripts\conda.exe run -n evoengine --no-capture-output python ...`
(PowerShell).

**Outputs** (`renders/`): `btx_vs_pawaga_v0.png` (single pair, side),
`btx_vs_pawaga_v0_plot_2x10.png` (10 plants/row, 0.30 m spacing, 1.0 m rows),
`btx_vs_pawaga_v0_plot_2x10_topdown.png`.

**Visual verdict — v0 accepted as starting point**
- Contrast expresses correctly: BTX623 erect/compact with upright leaves; Pawaga arching
  planophile leaves drooping toward the ground, visibly larger footprint in top-down.
- Height ordering matches drone data: single pair 1.26 vs 1.22 m; plot means ≈1.39 (BTX)
  vs ≈1.34 m (Pawaga), wide per-seed spread (BTX 1.18–1.66, Pawaga 0.98–1.67) with overlap —
  plausible.
- Rows do not close canopy at 1 m spacing (bare furrow visible top-down) — qualitatively
  consistent with the measured τ ≈ 0.25 order of magnitude.
- **Panicles render on both genotypes** although v0 files carry no panicle fields — the legacy
  loader's inline defaults enable them ("SorghumLSDescriptor defaults file not found. Using
  inline member defaults"). Kept for now (panicles plausible at 74 DAP); explicit on/off is an
  E3 sensitivity case, and the τ pipeline must use the same default knowingly.

**Next**: GDD anchor check (AZMET 2021 vs 2026); install v0 into the illumination pipeline
(new growth stage + DATE_ORDER entry for 2021-07-26); E1 scene-extent sensitivity.

---

## 2026-09-10 — Greenhouse photo analysis (PeerJ supp. S1) → v1 proposal

**Source**: peerj-09-12628-s001.pdf (supplement of PMC8710048), panel A = BTx623,
panel B = Pawaga, greenhouse-grown, vegetative. Retrieved through the browser (PMC blocks
scripted downloads); crops archived as `targets/photo_greenhouse_BTX623_peerj_s001.png` and
`targets/photo_greenhouse_Pawaga_peerj_s001.png`. Caveat: greenhouse pot plants (no wind
hardening, well-watered) are droopier than field plants — direction taken from the photos,
magnitude to be settled by field renders + τ calibration.

**What the photos show**
- BTx623: whorl + youngest leaves erect; every expanded leaf rises at ~30–45°, arcs with the
  apex near mid-blade, and the distal third HANGS (tips pointing down). "Erect" is relative —
  not straight leaves.
- Pawaga: leaves bend almost immediately after insertion — arc apex close to the stem, distal
  half hangs near-vertical, lowest tips reach pot-rim level (below their own insertion).
  Fountain/umbrella silhouette. Top whorl erect, like BTx623.
- **Key structural insight**: the erectophile/planophile contrast lives mainly in WHERE the
  bend starts along the blade and how much of the blade hangs — much less in collar insertion
  angle. This contradicts v0's Pawaga rank-increasing insertion curve (GenC template): Pawaga's
  upper leaves insert erect too; the droop is bending. GenC template dropped for Pawaga.

**Why v0 renders too stiff — three multiplicative gates on realized bend**
1. `leaf_bending` rank-curve tails (BTX 0.86→0.18, 1→0; Pawaga v0 1→0.4) kill bend on upper
   ranks, and with 14 phytomers most visible leaves are upper ranks.
2. `leaf_bending_development_curve` ([0.45→0.05, 0.7→0.35, 0.88→0.75]) delays bend until a
   leaf is old — most leaves are young → realized bend ≪ nominal max.
3. `bending_along_leaf` concentrates curvature in the distal 30 % — right for BTx623, wrong
   for Pawaga whose arc apex sits near the stem.

**v1 proposed deltas (angle family only — the designated free parameters)**

| Parameter | BTx623 v1 | Pawaga v1 |
|---|---|---|
| leaf_bending max | 130 → **150** | 110 → **150** |
| leaf_bending rank curve | [0,.9][.2,.85][.45,.75][.68,.6][.86,.4][1,.25] | [0,1][.2,.95][.45,.85][.68,.7][.86,.55][1,.4] |
| bending_along_leaf | [0,0][.25,.03][.5,.18][.7,.5][.88,.9][1,1] (slightly earlier) | [0,0][.15,.1][.35,.35][.6,.7][.85,.95][1,1] (apex near stem) |
| leaf_bending_development_curve | [0,0][.3,.2][.55,.55][.8,.9][1,1] (faster; both) | same |
| leaf_insertion_angle | max 42 → **46**, base 0.65 → 0.75 (≈34° base), still →0 at flag | **revert to stock Pawaga declining curve** (max 70, [0,.82]→[1,0]), keep dev 18 |
| (reserve knob, unchanged) | leaf_gravity_droop_compliance 0.02 | same |

Expected outcome: both genotypes gain hanging distal blades; BTx623 keeps a taller, narrower
silhouette (bend apex mid-blade, tips landing high); Pawaga's early-bend arc lowers its canopy
surface and widens its footprint — which should also reproduce the drone height gap mechanism.

**v1 authored and rendered (same day)** — `descriptors/*_v1.sorghumls`, diff-verified (note:
Pawaga's stock `bending_along_leaf` differs slightly from BTX's: [0.5,0.039]/[0.88,0.93] vs
[0.5,0.0225]/[0.88,0.9] — per-genotype old-values needed in edit scripts). Renders
`renders/btx_vs_pawaga_v1*.png`:
- Pawaga now a fountain — arc apex near stem, distal halves hanging, lowest tips near ground;
  good match to greenhouse panel B. BTX623 erect with arching/hanging distal blades, apex
  higher — matches panel A direction; could take slightly more mid-blade arch in v2 if field
  comparisons agree.
- Heights: pair 1.20 (BTX) vs 1.22 m (Paw); plot means ≈1.33 vs ≈1.34 m — droop pulled BTX's
  envelope down ~0.06 m so the genotypes are now dead even; drone says BTX marginally taller,
  a point to watch in calibration, not worth chasing pre-τ.
- Top-down: leaves now bridge more of the inter-row furrow than v0 → expect lower simulated τ.

## 2026-09-10 — GDD anchor check: DAP anchor corrected, GDD anchor established

- v1 approved by user. Engine rebuild (panicle albedo patch + ray tracer) deferred to the
  illumination-estimation step, per user.
- **Week-numbering correction**: the 2026 field CSV numbers weeks 1–8 (week 1 = 2026-07-09,
  week 6 = 2026-08-11, week 7 = 2026-08-18, week 8 = 2026-08-25). The earlier kickoff entry's
  "week 0 = July 9, week6 = Aug 20 = 72 DAP" reading was wrong → the DAP-based anchor claim
  (week6 ≈ 74 DAP) is retracted and replaced by the GDD anchor below.
- Method: cumulative GDD °F 86/55, hourly clamp formula — identical to the field record's
  `gdd_cumulative_F_8655`. 2021 series computed from AZMET az06 hourly API data (planting
  2021-05-13); saved to `targets/azmet_az06_2021_daily_gdd.csv`. Field CSV GDD column verified
  ≈ June-9-origin AZMET computation (within ~1.5 %); its DAP column is inconsistent (says 38 d
  on 2026-07-09 vs 30 d actual) and is not used.
- **Anchor result**: 2021-07-26 = 2036 GDD ≈ midway between measured week 6 (1948) and week 7
  (2134), α ≈ 0.48 — both weeks have tuned A/B/C descriptors, so interpolation (or the
  GDD-keyed .sgs machinery) covers scan 1 with no extrapolation. 2021-08-22 = 2810 (week 8
  + 489); 2021-09-21 = 3649 (week 8 + 1329, validation only).
- **Phenology bonus**: scan 1 sits at/past typical BTx623 anthesis thermal time → panicles
  very likely present on 07-26; the loader's panicle-on default is now justified rather than
  accidental. Pawaga's flowering (photoperiod-sensitive landrace) less certain.

## 2026-09-10 — Illumination pipeline scoped (subagent over PythonBinding sources)

Full API map delivered (driver 1991 lines + scene/layout/video modules + C++ bindings).
Load-bearing findings, now baked into METHODS §7:
- Sensor output is relative units → fine, τ cancels units (mirrors field methodology).
- DO NOT edit shared `DATE_ORDER` (positional stage numbering; renumbering breaks manifest +
  checkpoints of the existing pipeline; several scripts also hardcode GrowthStageNN). Use an
  experiment-local layout module instead.
- Existing 4x10 manual scene geometry: 0.76 m in-row × 1.10 m rows, cultivar blocks 2.2 m
  apart — NOT our field (1 m rows, ~0.3 m in-row) → new manual scene needed anyway (also
  wanted for E1 neighbors). `ConfigureSorghumLsPlantingGrid` supports the correct layout.
- Sensor probes are auto-generated along the longest in-plane axis of named scene meshes
  (`PARBAR_*_{Top,Middle,Bottom}SensorBarMesh`), probe count parameterized → a 45°-rotated
  1 m bar mesh with 50 probes needs scene authoring only, no C++. Fallback: add
  `CreateLineSensorGroup` binding during the rebuild.
- No diurnal sun loop exists in the scientific path (sun fixed overhead; only the video module
  sweeps sun and restores it). New driver code required; solar math reusable from
  `sorghum_4x10_illumination_video.py` (or pvlib per METHODS §2 convention).
- **Gotcha**: this code path's `SetSunDirection` is a vec3 (pitch, yaw, roll) rotating
  (0,0,−1) — NOT the (azimuth, elevation) two-arg form in project memory. Sanity-check with
  solar noon before trusting any τ run.
- Checkpoint fingerprints hash the whole Assets tree — asset changes invalidate old
  checkpoints by design; keep our experiment's assets separate to avoid churning theirs.

**Plan for E2 infrastructure** (order): engine rebuild (ray tracer + panicle albedo patch) →
new manual scene for position Y (markers via ConfigureSorghumLsPlantingGrid + two 45° bar
meshes above/below per plot pair) → experiment-local driver with 15-min sun loop → E1 extent
test → E2 baseline τ on 2021-07-26.

## 2026-09-10 — Engine rebuilt with panicle patch; zombie-process fix

- Panicle albedo patch applied at `EvoEngine_Packages/LSystem/src/SorghumLS.cpp` (~line 1052):
  raster-path albedo = 50/50 mix of descriptor immature/mature panicle colors instead of
  white (`vertex_color_only` still set; ray tracer unchanged). **Local patch — re-apply after
  any rebase** (recorded in memory local-patches note).
- Incremental rebuild: `cmake --build out\build\x64-Release --config Release --target
  PyDigitalAgriculture -- /m` (VS 2022 generator). First two attempts failed with LNK1104:
  `LSystemPackage.dll` locked by **zombie python.exe processes left by earlier render runs**
  — engine worker threads outlive `main()` after `Terminate()`, keeping package DLLs loaded.
  Killed PIDs 27704/16692 (user-approved); render script now ends with `os._exit()` after
  flushing to prevent recurrence.
- Verification render `renders/btx_vs_pawaga_v1_panicle_check.png`: panicles now dark
  green-brown; geometry unchanged. Rebuild+patch confirmed good.

## 2026-09-10 — Position-Y PARBAR scene built and engine-verified

New scene `ManualAssets/Scenes/Sorghum_PositionY_PARBAR45.evescene` (copy of the 4x10 PARBAR
scene; both rigs kept with their compile-time-required names). Built by
`build_positiony_scene.py` (two passes) + `verify_positiony_scene.py` (loads scene, builds
50-probe top-face sensor group, reports per-bar world center/span/axis, writes
`measured_bars.json`):
- Pass 1: rig roots translated to furrow lines and uniformly shrunk ×0.5618 (scene bar
  1.78 m → physical PARbar 1.0 m); no root rotation (mast line must stay along the furrow).
- Pass 2: each *SensorBarMesh rotated about its own measured bar center to the target axis.
  Needed two engine-verified iterations: (i) the six bars carry different baked twists
  (12–30°), so per-bar deltas, not one rig yaw; (ii) rotation-sense bug — ry(θ) rotates the
  measured atan2(dz,dx) angle by −θ — fixed by negating.
- Earlier dead end: rotating the whole rig root by 45° also rotated the mast line diagonally
  across rows (field masts run along the furrow) — reverted.
- Tooling gotcha: system Python is 3.9; `Path.write_text(newline=...)` is 3.10+ — pass 1
  silently never wrote on the first PowerShell run and verification read a stale file.
  Builder now uses open(); engine scripts run with the conda env python.
- **Final state (engine-verified)**: all 6 bars axis −135.0° from +X (≡ 45° NE–SW line,
  east end north, per SOP); centers on furrows z≈1.50–1.57 (BTX, rows z=1/2) and 5.50–5.57
  (Pawaga, rows z=5/6); span 0.979 m; bottom bars y 0.11–0.15 m, top bars 1.51/1.66 m
  (above canopy). World convention: +X = north = row direction, +Z = east; rows z = 0..6
  at 1 m (BTX plots 7410–7413 → z 0–3, Pawaga 7414–7416 → z 4–6).
- Cosmetic deviation, accepted: mast heights run north→south rather than the SOP's
  south→north (tallest pole at x≈0). Irrelevant to τ (solar-panel azimuths are screened).
- Next: diurnal driver (sun loop per 15-min bin, τ = below/above per genotype), then E1.

## 2026-09-10 — E2 BASELINE COMPLETE: first simulated τ vs field

Infrastructure finished this session:
- `sun_positions_20210726.csv` — pvlib 15-min solar positions 07:00–16:00 MST with the
  azimuth<245°/elevation>30° validity flag (25 valid bins = field window 8.25–14.25 h).
- Sun convention derived symbolically and encoded in `run_tau_diurnal.py`: OptiX
  `sun_direction` points TOWARD the sun (default zenith);
  d = (−sin y cos p, sin p, −cos y cos p) with SetSunDirection vec3 (pitch,yaw,roll) →
  **pitch = elevation, yaw = 270° − compass azimuth** (+X=north, +Z=east). Empirical support:
  the Pawaga morning/afternoon τ asymmetry matches its open-east-edge position.
- `run_tau_diurnal.py`: loads position-Y scene, plants 7×12 grid (BTX rows z=0–3, Pawaga
  z=4–6, 0.30 m in-row, 1 m rows), binds staged v1 descriptors, grows (84 plants), then per
  sun bin: SetSunDirection → EstimatePARSensors(128 rays, 4 bounces, per-bin seed) →
  per-panel means + per-probe CSV. τ = bottom/top per cultivar.

**E2 result (valid-window medians, single geometry seed 42_2021):**
| genotype | field τ | sim v1 τ | ratio |
|---|---|---|---|
| Pawaga | 0.265 | **0.267** | 1.01× |
| BTx623 | 0.247 | **0.596** | 2.41× |

Files: `results/tau_20210726_v1_E2_baseline.csv` (+ `_probes.csv`,
`_vs_field.png`).
- **Pawaga v1 is essentially on target** — level AND a plausible planophile diurnal shape
  (τ min ~0.19–0.20 near noon, rising toward low sun; field curve comparison in the PNG).
- **BTX v1 is far too transmissive (2.4×)**: erect leaves + 0.85 m blades leave the rows
  open; τ even *rises* around noon (0.65–0.71) as near-vertical beam passes between rows —
  the classic erectophile signature, but much too strong vs the field's 0.247.
- Caveats: single seed; Pawaga bar's east side is the block edge (2 rows east of the bar
  missing vs real field) — inflates Pawaga low-sun morning bins (visible pre-08:15), which
  are outside the valid window; E1 extent test will quantify.
- **Calibration direction (E3/E4)**: BTX needs substantially more light interception —
  candidates: longer blades (0.85→~1.0 m, still within A/B/C range), more bend (current
  render still stiffer than the greenhouse photo), higher tiller count, wider leaves
  (8.5 cm is the A/B/C prior; BTX623 lit. leaves can be wider). Sensitivity sweep first to
  avoid compensating errors; Pawaga should be left untouched.

## 2026-09-10 — E3 sensitivity (BTX only, Pawaga frozen at v1)

User guidance: proceed E3 BTX-only; field sorghum with panicles is never as erect as the
v1 BTX render — droopier per the greenhouse photo. Five one-at-a-time variants
(`descriptors/BTX623_20210726_e3*.sorghumls`), same geometry seed, valid bins only
(driver gained --btx-descriptor/--pawaga-descriptor overrides):

| variant | change | BTX median τ | Δ | Pawaga (control) |
|---|---|---|---|---|
| baseline v1 | — | 0.596 | — | 0.267 |
| e3bend | bending rank curve ↑ (tail 0.25→0.45, base 0.9→1.0) + earlier bend along blade | **0.519** | **−0.077** | 0.265 |
| e3blade | blade max 0.85→1.0 m | 0.544 | −0.052 | 0.268 |
| e3width | width max 0.085→0.10 m | 0.548 | −0.048 | 0.265 |
| e3tiller | tillers 2±1(0–4)→3±1(1–5) | 0.559 | −0.037 | 0.265 |
| e3insert | insertion max 46→56° | 0.574 | −0.022 | 0.268 |

- Bend is the strongest lever (confirms user intuition); insertion the weakest.
- Pawaga control stable (0.265–0.268) — no cross-block contamination.
- Sum of top four ≈ −0.21 vs required −0.35 → E4 combo (bend+blade+width+tiller) launched;
  if it lands short, remaining levers: leaf count (phytomer 14→16), even stronger droop, or
  the [PROV] structural assumptions (1 row/plot, 12 plants/row) — density is untested and
  potent.

## 2026-09-10 — E4 iterations; TOP-BAR ARTIFACT found and fixed (invalidates prior τ levels)

- E4 combo (bend+blade+width+tiller): BTX 0.596→0.338 — superadditive (−0.26 vs −0.21
  additive). Pawaga control 0.262.
- E4b (combo + phytomer 16): τ went UP to 0.376 and the render showed plants at 1.43 m —
  which exposed the artifact: **the uniform rig shrink had lowered the TOP bars to 1.51 m
  (BTX) / 1.66 m (Pawaga), inside/at canopy height (plants 1.2–1.67 m)**. The above-canopy
  reference was partially shaded, deflating the denominator and inflating τ in ALL earlier
  runs. This is exactly why field crews raised the physical top bar as the crop grew.
- Fix: builder pass 3 raises both top bars to world y = 2.30 m (engine-verified: centers at
  2.300, axes still −135.0°). Scene file rewritten in place.
- **Corrected results (valid-window medians, targets BTX 0.247 / Pawaga 0.265):**
  | run | BTX τ | Pawaga τ |
  |---|---|---|
  | v1 re-baseline (topfix) | 0.497 (was 0.596) | 0.226 (was 0.267) |
  | E4 combo (topfix) | **0.292** | 0.229 |
- Consequences: E3 sensitivity RANKING presumed still valid (all variants shared the same
  bias), but absolute Δs are ~15 % overstated; Pawaga's v1 "perfect match" was
  artifact-compensated — it is now 0.036 too closed and needs a slight opening.
- E4c launched: BTX = combo+phytomer16 retested on fixed scene; Pawaga v2 = blade
  0.95→0.90 m + bend curve −0.05 across ranks (slightly opener). One run tests both
  (blocks independent; cross-contamination <0.005 in E3 controls).

## 2026-09-10 — E4c/E4d iterations; E1 extent test; seed-noise discovery

- E4c: BTX combo+phyto16 on fixed scene = 0.339 — worse than combo (0.292) even without the
  top-bar artifact: more phytomers with the same internode curve → taller, vertically
  stretched, *sparser* canopy. **Phytomer lever dropped; stays 14.** Pawaga v2 = 0.238
  (moved +0.012 toward 0.265).
- E4d: BTX v2 (combo + extra droop + width 0.107) = 0.280; Pawaga v3 (v2 + blade 0.90→0.85
  + tillers 2→1.5) = 0.304, overshooting — the tiller lever bites harder on droopy
  architecture than the BTX-derived sensitivity predicted.
- Shape diagnosis: BTX excess τ concentrated at morning/afternoon shoulders (0.33) with
  midday on target (0.23) → low-sun beams entering through the open field beyond the 7-row
  scene — the neighboring-plots effect the user predicted → E1.
- **E1 extent test** (block layout: 15 rows = plots 7402–7416 per naming key, 180 plants;
  GPU OOM at fine mesh on the 8 GB RTX 2070 SUPER → leaf mesh coarsened 0.01/6 → 0.02/4;
  coarse-mesh control on small layout shifts medians ≤0.011, acceptable):
  | run | BTX τ | Pawaga τ |
  |---|---|---|
  | small fine (E4d) | 0.280 | 0.304 |
  | small coarse (control) | 0.291 | 0.305 |
  | block coarse | 0.216 | 0.427 |
  BTX shoulders collapsed 0.327→0.255 with midday unchanged (0.227→0.223) — extent effect
  confirmed and large; the block layout is henceforth the production scene.
- **But Pawaga jumped 0.305→0.427 — diagnosed as SEED NOISE, not physics**: top bars agree
  between rigs (unshaded); changing layout reshuffles per-plant random draws, and Pawaga v3's
  tiller_count 1.5±1 (min 0) makes single realizations fragile. Consequence: single-seed τ
  comparisons are only valid within a fixed layout; cross-layout or final numbers need
  **seed replicates** (METHODS §8.5 activated). Two more block-layout seeds launched.

## 2026-09-10 — 2×3 layout×seed grid: TWO earlier conclusions overturned

Full grid (BTX v2 + Pawaga v3, 3 geometry seeds × {small, block}):
| layout | BTX seeds → mean | Pawaga seeds → mean |
|---|---|---|
| small | 0.291/0.291/0.314 → 0.299 | 0.305/0.418/0.658 → 0.460 |
| block | 0.216/0.361/0.291 → 0.290 | 0.427/0.508/0.450 → 0.462 |

1. **Scene-extent effect on the medians ≈ 0** (0.299 vs 0.290; 0.460 vs 0.462). The earlier
   "E1 extent confirmed, shoulders collapsed" conclusion was a single-seed artifact —
   RETRACTED. (Extent may still matter for the *screened* low-sun bins; irrelevant to the
   valid-window fit. Small layout is acceptable for iteration; verify on block at the end.)
2. **Stand-realization variance dominates**: seed-to-seed SD ~0.03–0.06 (BTX) and up to
   0.15 (Pawaga v3) — driven by per-plant tiller draws (1.5±1, min 0). ALL single-seed
   numbers from E2→E4d carry this uncertainty; within-layout same-seed A-vs-B comparisons
   (E3 ranking) remain valid, absolute levels do not.
3. Pawaga v3's true mean is ~0.46, not the 0.304 single-seed value — the v3 opening
   overshot badly; even v2/v1 levels (0.238/0.226, n=1) are now suspect.
4. **Deep parallel to the field data**: the 2021 synthesis showed Pawaga plot-pair τ ranging
   0.157–0.316 at equal biomass — real stands vary this much too. The field target (0.265)
   is itself ONE stand realization. Fitting tolerance must respect stand-realization
   uncertainty (~±0.05); chasing 0.01 is overfitting.

**Protocol from here**: (a) 3-seed replicates minimum for any reported τ (mean ± SD);
(b) reduce non-physical stand stochasticity — field stands are consistently ~30 stems/plot
(2026 counts), so tiller deviation tightened (±0.5) and min ≥1 ("all genotypes tiller");
(c) next iteration: Pawaga v4 = v2-like interception with tightened tillering
(mean 2 ± 0.5, min 1, max 3, blade 0.90); BTX v2 kept (mean 0.299 ≈ within one stand-SD of
0.247) pending Pawaga's re-anchor.

## 2026-09-10 — Pawaga variance hunt (E4e–h) → ROOT CAUSE: bars at row end

Chased Pawaga's persistent 3-seed spread through four descriptor hypotheses — all null:
| iteration | change | Pawaga seeds → mean±SD |
|---|---|---|
| E4e (v4) | tillers 2±0.5 (1–3) | 0.257/0.345/0.470 → 0.357±0.107 |
| E4f (v5) | + insertion dev 18→8 | 0.253/0.339/0.482 → 0.358±0.116 |
| E4g (v6) | + internode dev 47%→27% rel | 0.261/0.354/0.460 → 0.358±0.100 |
| E4h (v7) | + blade back to 0.95, full v1 droop | 0.249/0.346/0.467 → 0.354±0.109 |
(BTX v3 stable throughout: 0.279–0.281 ± ~0.04.)

Azimuth decomposition: the wild seeds' excess is at SOUTH/midday sun (τ 0.54–0.60 vs 0.19
for the tame seed) — vertical beams through a canopy hole. Per-plant metadata showed no
degenerate plants. **Top-down renders over the Pawaga bar found it**: the rig-internal mast
offsets place the BOTTOM bars at x ≈ +1.39 (Pawaga) / +1.68 (BTX) — at/beyond the LAST
plants of the 3.3 m rows (x ≤ 1.65), with bare ground beyond; the bar tips hang over the
row end, and whether the end plants lean across the bar is the per-seed lottery. Violates
the SOP ("ceptometers fully within the planted area") and biases τ high for both cultivars
(BTX bar most exposed).

Fix: builder pass 4 slides each rig along the row so the top/bottom mast pair centers at
mid-row. Engine-verified: bottom bars now x = +0.82 (BTX) / +0.67 (Pawaga), tops at
−0.82/−0.67, ≥0.8 m of planted row beyond every bar tip; z, heights, 45° axes unchanged.
All E2–E4h absolute τ levels carry the edge bias → re-baseline required. METHODS lesson:
virtual sensor placement must be verified against the planted extent, not just the furrow.

## 2026-09-10 — E5: LEVEL CONVERGENCE on 2021-07-26 (BTX v4 / Pawaga v8)

Mid-row fix collapsed seed variance ~5× and re-ranked everything:
- E5 (BTX v3 + Pawaga v7): BTX 0.169±0.012 (now overshooting — E4 additions had been
  compensating the edge bias), Pawaga 0.239±0.024.
- Rebalance: **BTX v4** = v3 with width 0.107→0.10, blade 1.0→0.95, tillers 2.5±0.5 (2–3),
  droop kept (photo-anchored). **Pawaga v8** = v7 with blade 0.95→0.92.
- **E5b (3 seeds): BTX 0.238±0.041 (target 0.247, Δ0.009); Pawaga 0.251±0.026 (target
  0.265, Δ0.014, ensemble contains target). |Δτ|≤0.03 criterion MET on the means.**
- Diurnal SHAPE (plot `results/tau_20210726_CALIBRATED_v4v8_vs_field.png`):
  - BTx623: r=0.91, RMSE 0.042 — tracks the field curve closely, including the low-morning /
    midday-rise pattern. Excellent.
  - Pawaga: r=0.39, RMSE 0.080 — LEVEL right but shape wrong: field Pawaga (like field BTX)
    is LOW at low sun (τ≈0.11 at 8:15–9:30) rising to ~0.30 midday; sim Pawaga is high in
    the morning (0.26–0.29) and flat. Two candidate causes: (a) **east-edge shelter
    deficit** — in both current layouts row z=6 is the field edge, so morning (due-east)
    beams reach the Pawaga bar through a single row; the real field continued east
    (plots/border rows per aerial). Testable with an east-extended layout (E6). (b) real
    architecture (canopy too shallow / too horizontal-layered at low sun angles).
- Promoted: `BTX623_20210726_v4.sorghumls` + `Pawaga_20210726_v8.sorghumls` = current
  calibrated drafts for scan date 1.
- Next (E6): east-extended layout test for Pawaga's morning shape; then final renders,
  full-day curves, and the 08-22 / 09-21 validation dates.

## 2026-09-10 — E6: eastern rows (MANUSCRIPT DISCUSSION POINT)

Field truth from user: the BTX/Pawaga plots sat near the WEST end of the field with ~30
rows of other sorghum to their east (aerial confirms). Geometric scoping: at the valid
window's lowest elevation (31°), a beam reaching the 0.13 m bottom bar traverses ≤~2.5 m of
canopy horizontally → ~10 eastern rows saturate direct-beam paths (30 matter only for
screened dawn bins). Layout "east10" added (17 rows, 204 plants, BTX/Pawaga-like blocks
continuing east per user instruction).

**Result (same descriptors/seeds as E5b; figure
`results/tau_20210726_east_rows_effect.png`):**
| | no rows east (E5b) | 10 rows east (E6) | field |
|---|---|---|---|
| BTx623 τ / shape r | 0.238±0.041 / 0.91 | 0.237±0.041 / 0.91 | 0.247 |
| Pawaga τ / shape r | 0.251±0.026 / **0.39** | 0.233±0.030 / **0.68** | 0.265 |
| Pawaga morning (<10:30) | 0.244 | 0.203 | 0.131 |

- **Built-in control**: BTx623's bar sits deep in the block and is numerically untouched by
  the eastern rows; Pawaga's edge-adjacent bar responds strongly. The simulation therefore
  *detects* the neighboring-canopy context of a sensor — worth a manuscript paragraph: the
  virtual PARbar reproduces the field only when the field beyond the measured plots is
  represented, and it localizes which sensor cares.
- Remaining Pawaga morning gap (0.203 vs 0.131): candidates — full ~30 rows (dawn-adjacent
  bins), sky diffuse fraction (scene ambient 0.8 is azimuth-independent light on the bottom
  bar; E3-sky sensitivity still pending), or residual architecture. East10 is the new
  production layout for Pawaga-relevant runs.

## 2026-09-10 — SEASON VALIDATION: calibrate once, validate twice (V-0822, V-0921)

The calibrated 07-26 descriptors (BTX v4 / Pawaga v8) were run UNCHANGED on the two later
scan dates (east10 layout, 3 seeds, each date's own pvlib sun table; valid windows match the
field's: 08:30–14:45 and 09:00–15:30). Physiological basis: 07-26 = 2036 GDD is at/past
anthesis, so canopy geometry is essentially static afterward (senescence not modeled).

| date | BTX sim | BTX field | Pawaga sim | Pawaga field |
|---|---|---|---|---|
| 07-26 (calib) | 0.237±0.041 | 0.247 | 0.233±0.030 | 0.265 |
| 08-22 (valid) | 0.236±0.033 | 0.248 | 0.224±0.021 | 0.283 |
| 09-21 (valid) | 0.199±0.009 | 0.179 | 0.224±0.006 | 0.208 |

- **BTx623 validates within 0.02 on all three dates with zero re-tuning** — including
  reproducing the September τ DROP (0.237→0.199 sim vs 0.247→0.179 field) purely from solar
  geometry (lower sun = longer oblique paths) with static plants. Strong manuscript result.
- Pawaga: July/Sept within ~0.02–0.03; the biggest miss is August (sim 0.224 vs field
  0.283) — the field Pawaga OPENED Jul→Aug (0.265→0.283) while the sim is static. Candidate
  explanations: lodging/leaf relaxation post-anthesis, or plot-specific change; note the
  field's own Pawaga plot-pair spread (0.157–0.316) dwarfs this gap.
- Seed SD shrinks with lower sun (±0.04 July → ±0.01 Sept): oblique paths average over many
  plants, vertical paths sample the few nearest the bar — consistent with the sunfleck
  mechanism.
- Figure: `results/tau_three_dates_validation.png`.

## 2026-09-10 — E7 sky test (diffuse fraction exonerated) + final renders

- E7: `ConfigureRayTracerSkydome` wired into the driver (`--sky SUN SKYLIGHT AMBIENT`).
  Same seed/layout, skylight 1.0→0.5 and ambient→0.02: medians shift ≤0.013 (BTX
  0.236→0.249, Pawaga 0.260→0.263) and Pawaga's morning is UNCHANGED (0.233→0.231).
  **The dawn gap is not diffuse-fraction driven** — remaining candidates: the full ~30
  eastern rows for the earliest bins, or genuine architecture (post-anthesis Pawaga in the
  field may differ from the greenhouse-anchored droop). Parked; acceptable residual for
  scan-date-1 calibration.
- Final render `renders/btx_vs_pawaga_CAL1.png` (cal1 = BTX v4 + Pawaga v8 copies):
  both genotypes field-plausible, colored panicles, architecture contrast preserved.

## 2026-09-10 — Seasonal significance analysis (user request)

Statistical framework: the geometry seed (= stand realization) is the experimental unit,
n=3 per date; one-sample t-tests of sim seed medians against the field value, plus t-based
95% CIs. Table: `results/seasonal_stats_table.csv`; figure:
`results/tau_seasonal_agreement.png` (seasonal dot-interval view replacing the hard-to-read
diurnal panels, + genotype-contrast panel).

- **8 of 9 quantities: field value inside the sim 95% CI (p > 0.05)** — simulation not
  statistically distinguishable from the field.
- **The single detected difference: Pawaga 2021-08-22** (field 0.283 vs sim 0.224
  [0.172–0.276], p = 0.040) — the August field opening a static canopy can't follow.
- September (tight seed SD ±0.006–0.009): both genotypes just inside CI (p = 0.053–0.065),
  sim ~0.02 high — a watchable small bias.
- **Genotype contrast (Pawaga − BTX)**: field positive on all dates (+0.018/+0.035/+0.029).
  Sim matches in September (+0.025 [0.017,0.032] — right sign, right size, tight). In
  Jul/Aug sim contrast ≈ 0 (−0.004/−0.012) with wide CIs — not distinguishable from the
  field value, but the mean sign is wrong. IMPORTANT CONTEXT: the 2021 synthesis showed the
  field's own genotype contrast is not statistically estimable (genotype aliased with
  device+plot; within-genotype plot differences 2–3.5× the contrast), so sign-agreement on
  a 0.02–0.04 contrast exceeds what the field design itself can establish — manuscript point.
- Power note: distinguishing a 0.03 contrast at seed SD ~0.05 needs ~n≈25 seeds (~4 min
  each) — feasible overnight if wanted; n=3 is a deliberate iteration-speed choice.

## 2026-09-10 — Reproducibility + publication assets (user request)

- Analysis made reproducible as saved scripts: `analysis/seasonal_stats.py` (significance
  tests → `results/seasonal_stats_table.csv`) and `analysis/fig_seasonal_agreement.py`
  (figure). Both re-run from the results CSVs; field targets are declared constants with
  provenance comments.
- `tau_seasonal_agreement` redesigned per user: single panel (contrast panel removed),
  no suptitle/arrow annotations, one asterisk marking the sole significant difference
  (Pawaga Aug 22, p=0.04), 300 dpi PNG + vector PDF.
- Publication field renders replaced the unusable plant-pair captures:
  `render_field_publication.py` (saved, cameras parameterized) loads the PARBAR position-Y
  scene, plants/grows cal1 at fine mesh, lights with **SetNishitaSky** (az 135°, elev 40°,
  directional light aimed), captures `renders/publication/field_overview.png` (elevated 3/4
  of the block, masts + solar panels visible), `field_furrow.png` (low view down the BTX
  furrow, canopy walls + sensor station), `field_topdown.png` (2000² nadir, drone-orthophoto
  style echoing the 2021 aerial). Natural daylight — no photo-grade pass.

## 2026-09-10 — Figure overhaul + large seed ensemble (user-directed)

User direction: all figures must tell one story — "the EvoEngine illumination engine
simulates field light well"; genotype difference must be visible in renders; the east-rows
figure redesigned to (a) plots-only vs (b) with-field-context panels, each against PARbar
data; large seed ensembles authorized (100–1000 OK).

- **fig_genotype_architecture.png** (script `analysis/fig_genotype_views.py`): labeled
  top-down + row cross-section composite from new publication renders. Two bugs fixed
  during review: end-view genotype labels were mirrored (camera looks +X ⇒ screen-right =
  +Z ⇒ BTx623 left / Pawaga right), and the sky band with the floating raised reference
  bars is cropped out.
- **Layout saga**: "full" 25-row context OOMed (300 plants) → redefined as 17 rows with
  ≥4 rows (4 m) of canopy on each side of both bars — optically equivalent to the field's
  ~30 rows at valid-window sun angles (beam path ≤2.5 m). Row mapping engine-verified
  (`check_full_rows.py`).
- **Midday instability finding**: BTX's E5b midday peak (τ≈0.38) vanished in the full
  layout (τ≈0.15) across FIVE seeds; optics cannot explain it (11:00–12:30 sun is SE–S at
  75° elevation — those directions saw identical rows in E6, which matched E5b). Conclusion:
  valid-window medians at n=3–5 are unstable because midday τ is governed by the few plants
  flanking the bar, and layout changes reshuffle per-plant draws. E5b's excellent BTX
  midday was partly draw luck. → **n≈33 per config ensemble** authorized and launched:
  `batch_seeds.py` (saved; runs 25 fresh seeds × {small, full} detached, PID logged,
  progress in `batch_progress.txt`, sentinel `BATCH_DONE.txt`, Monitor armed).
- `analysis/fig_east_rows.py` saved (panel pair vs field); will be regenerated from the
  full ensemble when the batch lands — n=3-era conclusions about layout effects are
  provisional until then.

## 2026-09-11 — ENSEMBLE VERDICT (n=33 plots-only, n=31 full-context)

50-run batch complete (one overnight machine-sleep stall, resumed cleanly). Findings:
| config | BTX τ | Pawaga τ |
|---|---|---|
| plots-only (n=33) | 0.197±0.059 | 0.293±0.067 |
| full context (n=31) | 0.185±0.052 | 0.271±0.058 |
| field | 0.247 | 0.265 |
1. **Layout effect on medians: NOT significant** (Welch p=0.40 BTX / 0.16 Pawaga). The
   dramatic small-n context effects were largely ensemble noise. Curve SHAPE does improve
   modestly for Pawaga with context (ensemble-mean r 0.80→0.92, RMSE 0.092→0.063); BTX
   shape ≈0.9 in both.
2. **Pawaga v8 confirmed at high power**: 0.271 [0.250–0.292] vs field 0.265, p=0.58 —
   statistically indistinguishable. CALIBRATED.
3. **BTX v4 refuted at high power**: 0.185 [0.166–0.204] vs 0.247, p<0.0001 — too closed by
   ~0.06. The 2026-09-10 n=3 "convergence" (0.238±0.041) was favorable-draw luck.
   Deck/figures updated accordingly; prior small-n claims (incl. context r 0.39→0.87)
   superseded.
4. Correction: **BTX v5** = v4 opened via tillers 2.5→2.0±0.5 (1–3), blade 0.95→0.90 m,
   width 0.10→0.095 m (expected +0.05–0.06 from E3 directions); 12-seed full-context batch
   to verify.

## 2026-09-11 — BTX v5 overshot; v6 bisection

- v5 batch (8/12 seeds; 4 transient "Failed to submit immediate GPU work" errors right after
  the 50-run batch — fast-fail then recovery; batch runner now retries once after 30 s):
  **BTX v5 = 0.307±0.044 [0.271–0.344] vs 0.247, p=0.006 — overshot open** (v4 was 0.185).
  The intended +0.06 delivered +0.12: dropping the tiller floor 2→1 opens whole furrow
  segments — levers interact super-linearly near canopy closure.
- Bonus: Pawaga v8 replicated again on fresh seeds (0.247±0.039, p=0.23 vs 0.265) — stable.
- **BTX v6 = midpoint** (tillers 2.25±0.5 min 1, blade 0.92 m, width 9.7 cm); target 0.247
  sits at α=0.51 between v4/v5 medians. 12-seed batch running (seeds 7101–7112).

## 2026-09-11 — FINAL: v6/v8 ensemble calibration + season validation

- **BTX v6 verified on target**: 0.258±0.072 (n=12, CI 0.212–0.303) vs 0.247, p=0.61.
  Calibrated pair = BTX623_20210726_v6 + Pawaga_20210726_v8 (cal1 aliases updated).
- Season validation re-run with v6/v8, full-context layout, n=8/date (all 16 runs clean
  after the batch runner gained a 30 s retry; one earlier relaunch was needed for a
  3-tuple-unpack bug introduced when adding per-config sun tables):
  | date | BTX sim | field | Pawaga sim | field |
  |---|---|---|---|---|
  | Jul 26 (calib, n=12) | 0.258±0.072 | 0.247 | 0.277±0.065 | 0.265 |
  | Aug 22 (n=8) | 0.194±0.060 | 0.248 | 0.251±0.049 | 0.283 |
  | Sep 21 (n=8) | 0.172±0.042 | 0.179 | 0.232±0.031 | 0.208 |
- **8 of 9 quantities inside the sim 95 % CI.** Genotype ordering (Pawaga>BTX) right on all
  dates; Jul 26 contrast +0.019 vs field +0.018 (p=0.98). September within 0.007/0.024.
- **Sole detected difference: BTX Aug 22 (p=0.037)** — field τ flat Jul→Aug (0.247→0.248)
  while the static canopy follows the sun downward. Mirrors the earlier Pawaga-August
  signature: consistent, both-genotype evidence for unmodeled post-anthesis canopy opening.
  Manuscript-worthy observation rather than a defect to tune away.
- Deliverables regenerated at ensemble grade: `tau_seasonal_agreement.png/.pdf` (asterisk on
  BTX Aug 22), `seasonal_stats_table.csv`, `fig_field_context.png`, deck (v6 version rows,
  ensemble methodology bullet, updated results slide). All from saved scripts.

### SESSION END STATE (2026-09-10)
Calibrated: BTX623_20210726_v4 + Pawaga_20210726_v8 (= cal1). Protocol: east10 layout,
3 seeds (422021/4212022/4232023), mesh 0.02/4, valid-window medians. Season validation
passed (BTX |Δ|≤0.02 all dates; Pawaga ≤0.06 worst). Manuscript assets ready:
`tau_20210726_CALIBRATED_v4v8_vs_field.png`, `tau_20210726_east_rows_effect.png`,
`tau_three_dates_validation.png`, `btx_vs_pawaga_CAL1.png`. Open threads: Pawaga dawn gap,
Pawaga August opening (senescence/lodging unmodeled), full-30-row dawn check, middle-bar
comparisons (unused so far), installing cal1 into the shared pipeline as a growth stage.

**Panicle white-render diagnosis (same day)**: L-system panicle material is
`vertex_color_only=true` + white albedo, colors in vertex data (`SorghumLS.cpp:1051-1052`,
green→red-brown by maturity). OptiX honors the flag (`RayTracerLayer.cpp:903`); the Vulkan
rasterizer behind `CaptureCurrentScene` never reads it (SDK grep: only serialization/inspector
+ gizmo pipelines) → white panicles in rasterized captures only. Cosmetic: ray-traced
illumination (τ) uses the correct colored material. Candidate fix (pending user go-ahead, needs
engine rebuild, joins local-patch set): set panicle material albedo to the mixed panicle color
in `SorghumLS.cpp:1052` so the raster path matches.

## 2026-09-11 — FSPM↔CGM bridge bundle landed on this machine (user request)

Goal: connect the calibrated illumination (cal1) to the c4sorghum→APSIM coupling so the
manuscript CGM figures use the new τ-calibrated k/FINT. Plan + machine audit:
`../fspm_cgm_evoengine_experiment/LOCAL_INTEGRATION_PLAN.md` (living).

- Bundle `fspm_cgm_evoengine_experiment.zip` unpacked to the project root (bridge code,
  calibrated c4sorghum copy under `github_deps/WheatFspm/src`, older 2026-06/07 EvoEngine
  handoffs kept as reference only — nothing in the bridge reads them).
- New conda env `fspm-cgm` (py3.11) for the CGM arm: apsimNGpy 1.5.5 needs py≥3.10, so it
  cannot live in `evoengine` (py3.9). Arms exchange CSVs only.
- c4sorghum repointed to the bundled calibrated copy (GBS 0.10, KAPPA_2 0.12) via new
  `fspm/wheatfspm_path.py`; the project-root `c4sorghum/` junction copy is the older
  uncalibrated one and must NOT be used for the bridge.
- APSIM 2026.3.8019.0 not yet installed (download in progress); .NET 8 runtime also required
  (only 6.0.11 present). CGM runs blocked until then; tests marked requires_apsim skip.
- Data-contract gap identified: the bridge derives k from 10x10 per-plant irradiance grids
  (old uncalibrated scene). This experiment produces PARbar τ. Planned Route A: new
  `fspm/rederive_k_from_tau.py` (k = -ln τ / LAI on the ensemble valid-window τ per date);
  Route B (after the seed batch frees the GPU): regenerate 10x10 grids with cal1 descriptors
  so the shading-heatmap figure and interior/edge/corner split stay valid.
- Seed batch (6001..6025 x small/full) still running this morning — no GPU work launched.
- LATER SAME SESSION: APSIM 2026.9.8111.0 was installed (newer than the 2026.3.8019.0
  manuscript pin); apsimNGpy 1.5.5 auto-detected it, .NET 8.0.31 present. Driver needed one
  Windows fix (locked apsim_out.db on temp-dir cleanup → clean_up() + ignore_cleanup_errors).
  Reproduction: baseline 1817.7 g/m2 @8.9 plants/m2 — identical to the Mac number. Coupled
  BTx623 1245.0 vs Pawaga 1244.5 with the OLD (uncalibrated) EvoEngine k tables — the genotype
  contrast the calibrated τ must now supply. CGM arm is unblocked; next is Route A (τ→k).

## 2026-09-11 — Bridge integration decisions + new scripts (user-directed)

User decisions: keep APSIM 2026.9.8111.0 (recorded); EvoEngine geometric LAI is the MAIN LAI
for the tau->k inversion (c4sorghum LAI = sensitivity); constant k anchored on 07-26 as main,
date-varying k in the sensitivity analysis; run the 10x10 per-plant grids on the calibrated
BTX/Pawaga geometry after the seed batch; raw season PARbar files supplied (Downloads).

- `measure_stand_lai.py` (new): east10 layout, cal1 descriptors, 3 seeds -> per-plant
  leaf_area_m2 from GetSorghumLsPlantSceneMetadata -> stand LAI per genotype
  (`results/stand_lai_cal1.csv`). Same scene/layout as the tau runs, so k and tau share geometry.
- `run_perplant_grid.py` (new, Route B): 10x10 single-genotype stands at 1.0 x 0.30 m,
  EstimateSorghumLsGridIllumination full-context vs plant-alone -> bridge 3-section grid CSV
  (`results/perplant_grid/`) for the shading-heatmap figure + interior/edge/corner retention.
  NOTE: per-plant ABSORBED light, not transmittance (SetPARSensors only accepts the old .sg
  SorghumField), so it is not a k source.
- `fspm_cgm_bridge/fspm/rederive_k_from_tau.py` (new, Route A): k = -ln(tau)/LAI_evo from
  `results/seasonal_stats_table.csv` sim_mean; rewrites the genotype lookup tables (main:
  constant k, c4sorghum LAI trajectory re-anchored to LAI_evo at the 07-26 thermal time;
  `_kvar` and `_c4lai` sensitivity tables; provenance JSON). Dry run OK.
- `fspm_cgm_bridge/data/par_bar_analysis/analyze_par_bars_screened.py` (new): season-long
  field tau/fIPAR under this experiment's screening rules (per-minute medians, pvlib
  az<245/elev>30, fault days, excluded segments). REPRODUCES all six calibration targets
  (max |dtau| = 0.009, BTX 08-22; five within 0.003). The bridge's figure scripts now read
  the screened series instead of the old unscreened daily_max_fipar.csv.
- Second seed batch (E9v5, seeds 7001-7012, full layout) ran concurrently; seeds 7003-7006
  failed in 13 s each with Vulkan "device lost" at 09:30-09:31 and later seeds recovered.
  Cause not established (APSIM/pytest CPU load was running in this session at that time).

---
