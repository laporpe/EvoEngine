# 2026 sorghum 6x10 experiment

This workflow extends the descriptor-driven 2021 4x10 infrastructure without changing any 2021 scene, descriptor, PARBAR result, placement seed, or illumination algorithm. It creates two morphology-and-rendering scenes for an unpublished three-genotype panel.

## Experiment contract

| Item | Value |
| --- | --- |
| Experiment ID | `Sorghum2026_6x10` |
| Sessions | `MeasurementStage01`, `MeasurementStage02` |
| Rows | `GenotypeA`, `GenotypeA`, `GenotypeB`, `GenotypeB`, `GenotypeC`, `GenotypeC` |
| Columns | 10 |
| Plants | 60 per session; 20 per genotype |
| Genotype aliases | A = source range 75, B = 74, C = 73 |
| Pedigree / relationship to BTx623, Pawaga, or 2021 | Unknown; none assumed |
| Provisional selection story | Aridity-index selection, pending confirmation |
| Plant spacing | 0.76 m within row; 1.10 m within each 2x10 block; 2.20 m between adjacent block rows; 3.30 m block-center spacing |
| Instrumentation | Three visual PARBAR rigs, each with top/middle/bottom bars, spatially replicated from the manual 4x10 profile; no 2026 observations or illumination results claimed |

The source workbooks remain outside Git under `C:\AlexC\01_EvoEngineProjects\sources`. Stage 1 preserves the recorded date difference: Genotype A measurements are dated 2026-07-16 while Genotypes B and C are dated 2026-07-15. Stage 2 measurements are dated 2026-07-21.

The July 21 leaf widths are provisionally interpreted as centimetres and are recorded as such in QC. The Genotype C, plant 3, rank-4 leaf length value `4.35` is excluded as a suspected decimal transcription outlier; it is not corrected. Device-angle conversion and the provisional aridity-index description remain pending confirmation.

Leaf midrib curvature was not measured. The generated descriptors therefore use zero intrinsic `leaf_bending` and a restrained shared `leaf_gravity_droop_compliance` prior of `0.02`. Gravity is never calibrated to force agreement with measured tallest-leaf height. The validation report records tallest-leaf, main-culm-tip, and highest-mature-collar heights separately; only the directly measured organ dimensions and counts enter descriptor acceptance until curvature measurements are available.

## Outputs

The resource submodule owns all generated experiment assets and provenance:

- `Data/Experiments/Sorghum2026_6x10/`: normalized long tables, cell-level source references, QC, descriptor targets, the validation contract, exact 2021 baseline, scene manifest, and engine-validation reports.

## Full-lifecycle panicle deliverable

The A/A/B/B/C/C field remains the authoritative full-lifecycle layout and preserves 20 plants per field identity. The current presentation revision deliberately reuses the manual BTX descriptor for non-panicle growth across A, B, and C while applying a separate, explicitly documented shared A/B/C panicle presentation. Before any video is accepted, it requires 60/60 final-state emergence, vegetative maturity, panicle maturity, and whole-plant maturity with no developmental modules remaining; every panicle must also clear its own vegetative canopy. The same 1,000 GDD-indexed native renders are delivered at 12, 24, and 48 fps for slow study, standard review, and fast overview. BTx/Pawaga is maintained only as an explicitly labeled reference demonstration and is not interchangeable with the measured 2026 field. See `docs/sorghum-2026-panicle-timelapse.md` for the execution and validation contract.
- `Assets/GeneratedAssets/Experiments/Sorghum2026_6x10/Descriptors/`: six descriptor assets, one per genotype and measurement session.
- `Assets/ManualAssets/Scenes/Sorghum_6x10_2026.evescene`: reusable 60-marker template with soil and one three-bar PARBAR rig per genotype block.
- `Assets/GeneratedAssets/Experiments/Sorghum2026_6x10/Scenes/`: two persisted descriptor-driven scenes.

The render review is intentionally untracked under `out/realism_review/sorghum_2026_6x10/`. It contains 12 fixed views per session—three field overviews plus representative plant, basal, and leaf-detail views for Genotypes A, B, and C—and one labeled multi-view contact sheet per session. Lighting, the temporary ground extension, grading, and camera selection are presentation-only and are never serialized into the scientific scenes.

The equivalent Blender review uses the same view inventory and the approved
Cycles presentation contract: the authored leaf SSS/specular nodes, explicit
leaf and soil color-calibration nodes, AgX medium-high contrast at `-0.9`
exposure, Nishita sun elevation `55 deg` and rotation `135 deg`, displaced PBR
soil, and OptiX denoising. Each session produces a 12-camera `.blend`, 12 PNGs,
a contact sheet, and a machine-readable settings report. The export is several
gigabytes, so use a high-capacity output drive when necessary:

```powershell
python scripts/blender/export_sorghum_2026_6x10_review.py `
  --output-dir D:\AlexC\Sorghum_2026_6x10_blender_review `
  --samples 128 --resolution-x 1280 --resolution-y 720
```

The review blend also applies a presentation-only `42 deg` distal leaf bend,
starting at 20% of each leaf's longitudinal UV span. This is a deliberately
moderate qualitative prior between the zero-bend canonical descriptors and the
discarded 100-150 degree inherited curves. It is not presented as a measured
curvature parameter and is never written back to the descriptors or Evo scenes.

Exported internode meshes contain a uniform white corner-color placeholder that
does not provide a biological stem color and resolves as black through Blender
5's generic Attribute node. The preparation pass therefore recalculates their
render normals and assigns one shared field-photo-grounded olive material
(`0.38, 0.54, 0.20`) with roughness `0.60`, specular `0.30`, and restrained
`0.25` stem-only indirect fill. This presentation correction is validated on
all 60 stem meshes and is not serialized back into EvoEngine.

The dry-soil presentation is grounded in `ClusterSpacing_3378`,
`ClusterSpacing_3380`, `Tiller_attachment_3418`, and `Coleoptile_3428`. Those
photographs show matte fine grains, centimetre-scale aggregates and clods,
shallow local furrows, small stones or dry plant fragments, and soil accumulated
around culm clusters. They do not show dominant polygonal mud cracking, so the
Blender material uses sparse, warped millimetre-scale fissures as a qualitative
dryness cue rather than a measured site property.

The close-range soil material is selected through a fixed-scale bakeoff rather
than by tuning the full field blindly. `export_soil_material_bakeoff.py` renders
the legacy control, a minimally corrected legacy shader, two CC0 Poly Haven
scans, and calibrated scan combinations on the same `1.2 m` patch with a `10 cm`
scale bar. Camera, Nishita sky, AgX transform, exposure, and Cycles settings are
identical. Field-photo crops and descriptive color/contrast statistics are saved
beside the renders; the statistics are diagnostic and do not replace visual
comparison. Downloaded files, source URLs, licenses, API metadata, and MD5 hashes
are recorded under
`Assets/ManualAssets/Soil/ScannedPBR/PolyHaven/`.

The production treatment uses the 1.3 m `brown_mud_dry` scan for correlated
diffuse, OpenGL normal, 32-bit EXR roughness, fine bump, and EXR displacement.
The 2.0 m `dirt` scan contributes only 8-28% low-frequency compacted-patch color
and roughness; mixing its unrelated height field would blur the physical relief.
True Cycles material displacement is enabled at `0.042 m` with midlevel `0.58`,
the authored roughness variation is not compressed, specular IOR level remains
the neutral `0.5`, and millimetre detail uses `0.003 m` bump distance. The old
8-bit height is no longer applied in Geometry Nodes, material displacement, and
bump simultaneously. Sparse `0.0012 m` fissures remain a restrained local cue,
not a claim that the sandy-loam field forms broad shrinkage polygons.

One deterministic Blender-only collection adds shallow six-row bed/furrow
geometry, shared contact mounds for all 60 culm clusters, 15-64 mm clods,
4-18 mm aggregate, 5-24 mm pebbles, and sparse 3.5-18 cm dry crop residue.
Aggregate and pebbles are native Geometry Nodes instances so this added close-up
detail does not inflate the blend into millions of realized decorative faces.
Every mound overlaps its culm center by at least `0.002 m`; contact clods are
concentrated around each plant. The collection and instance prototypes are
explicitly marked `blender_presentation_only`, included in the render report,
and never written into a descriptor, EvoEngine scene, PARBAR probe, or
illumination result.

The field-background treatment follows the same presentation-only boundary.
One deterministic Blender collection extends the approved soil into a broad
terrain apron, adds subdued service lanes and shallow boundary berms, and
places two low-cost generic crop bands outside the measured plot. These objects
exist only to prevent the 6x10 field from reading as a finite tabletop. They are
camera-visible but disabled for diffuse, glossy, transmission, shadow, and
volume-scatter rays, so they cannot change plant or PARBAR illumination.

The distant skyline is derived from a public-domain USGS 3DEP bare-earth DEM.
It uses the University of Arizona AZMET Maricopa station only as a regional
geographic proxy; the experiment's exact plot coordinates and heading are not
established. The July 9 field photographs are close-range morphology, soil, and
color references and do not establish a horizon or mountain bearing. Therefore
the Sierra Estrella profile is scale-correct but artistically rotated into the
paper camera, with the explicit policy
`artistically_aligned_plot_heading_not_measured`. The generated JSON records
the DEM request URL, geographic extent, license, hash, bearing samples, and the
roughly two-degree peak elevation angle. This is Arizona visual context, not a
claim that a particular ridge was visible from the photographed plot.

Perspective, row-side, and whole-plant views can show the terrain, adjacent
agriculture, skyline, and restrained horizon haze. Near-top-down, basal, and
leaf-detail measurement views show only the neutral terrain apron: artificial
lanes, crop bands, mountains, and haze are hidden. A six-frame fixed-camera
bakeoff (`control`, `horizon`, `apron`, `agriculture`, `mountains`, `final`)
makes the contribution of every background layer auditable. Add
`--background-bakeoff` to the Blender export command to regenerate it.

Regenerate the material validation set with:

```powershell
python Scripts/blender/fetch_polyhaven_soil_assets.py `
  --output Resources/DigitalAgricultureProject/Assets/ManualAssets/Soil/ScannedPBR/PolyHaven
python Scripts/blender/export_soil_material_bakeoff.py `
  --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
```

Blender export and rendering are presentation-only. The orchestrator hashes the
source scenes, verifies 60 named plants, three PARBAR roots, nine sensor bars,
all shader/world values, all 60 deformed leaf objects, every background object,
the USGS profile, and every rendered view. It requires the two canonical scene
hashes to remain exact and never saves the scientific EvoEngine scenes.

Close-up leaf presentation keeps the canonical L-system geometry and atlas UVs
unchanged. The previous Blender bend treated the disconnected sheath, neck, and
blade surface pieces as independent leaves, which exposed artificial cut ends.
The corrected presentation policy bends only components whose local atlas range
is the distal blade (`V >= 0.5` with a blade tip near `V=1`), pins the blade base,
leaves sheath and neck geometry fixed, and stitches only exactly coincident
duplicates at `1e-6 m`. The render report records component counts, maximum base
motion, stitch count, ownership, and the unchanged canonical-scene hashes.

The V2 3x3 atlas uses one photo-grounded continuous sorghum
blade-collar-sheath master for all nine controlled variants. Its provenance
file identifies the July field photographs and records that the bitmap is a
generated albedo source rather than measured BRDF data. Normal, height,
roughness, AO, metallic, and thickness are deterministic derived maps. The
export gate requires all seven V2 maps, nine variants, objective map-junction
thresholds, thickness-driven SSS, restrained underside response, and
longitudinal anisotropy. A fixed Genotype A basal bakeoff separates the legacy
control, blade-only geometry repair, continuous albedo, full PBR maps, and final
shader so each contribution is auditable.

## Reproduction

From the repository root:

```powershell
python PythonBinding/sorghum_2026_6x10_data.py
python PythonBinding/sorghum_2026_6x10_descriptors.py
cmake --preset vs2026-x64
cmake --build out/build/vs2026-x64 --config RelWithDebInfo --target PyDigitalAgriculture -- /m:1
python PythonBinding/sorghum_2026_6x10_validate_descriptors.py --sample-count 1000 --require-acceptance
python PythonBinding/sorghum_2026_6x10_scene.py
python PythonBinding/sorghum_2026_6x10_validate.py
python PythonBinding/sorghum_2026_6x10_measurement_validation.py
python PythonBinding/sorghum_render_2026_6x10.py
```

Run the engine-dependent scripts from a configured build. They automatically use the built Python runtime directory for EvoEngine shader/resource lookup and restore the project manifest byte-for-byte after engine startup.

## Measurement-fidelity validation

The measurement validator runs 30 plant-level leave-one-out folds: for each
session/genotype group, it reconstructs a descriptor from four measured plants
and evaluates 512 generated plants against the omitted fifth plant. Leaves,
internodes, tillers, and angle records remain nested within their plant rather
than being treated as independent replicates. The full run produces 15,360
prediction plants, 1,647 measured-organ comparisons, and 298 plant/trait scores.

The strongest held-out result is main-culm leaf count (76.7% coverage by the
nominal 90% predictive interval, 8.6% normalized median error). Leaf length and
width are directionally represented but under-cover omitted plants (66.9% and
68.6% coverage). Internode length is the clearest primary-trait weakness (53.4%
coverage, 42.7% normalized median error). Tallest-leaf height remains an
explicitly diagnostic failure (10.0% coverage), consistent with the missing
leaf-curvature measurements; it is not used to distort leaf mechanics.

Persisted-scene typicality is reported separately from measurement fit. Four
tails occur in the Stage 2 Genotype B/C blocks: their saved seeds produce high
mean height and leaf-count realizations. No placement seed or canonical scene
is changed in response. Genotype contrasts are descriptive only because each
genotype is represented by one source plot per session.

The output directory also contains an auditable contract, raw comparison
tables, paper figures, and a 138-file manifest for the July 9 field photographs
(68 HEIC and 70 PNG). The photographs remain a separate qualitative stream
because they are not date- or plant-matched to the workbooks. The validator
hashes all six source workbooks, six canonical descriptors, both persisted
scenes, and the project manifest; the report is valid only when they remain
byte-exact and the temporary validation scratch assets have been removed.

This is robustness evidence for representation of the measured within-plot
sample distributions, not independent external biological validation.

## Acceptance and boundaries

The descriptor gate samples 1,000 plants from each of the six descriptor populations. It checks leaf count, primary tiller count, maximum leaf length, maximum leaf width, gravity-tip deflection, and centerline arc/chord ratio. Tallest-leaf height remains a reported diagnostic because fitting it without measured curvature produced nonphysical willow-like leaves. Main-culm-tip and mature-collar height are reported separately. The scene gate requires 60 unique stable root identities, 20 plants per genotype, unique deterministic seeds, the exact A,A,B,B,C,C row ownership, valid soil context, the repeated `1.10, 2.20, 1.10, 2.20, 1.10 m` row-delta pattern, three complete PARBAR rig roots, and nine sensor-bar meshes.

`legacy_4x10_baseline.json` fingerprints 21 protected 2021 files. The final validator must report `exact_match`; the baseline is never regenerated during ordinary workflow runs. The replicated PARBARs are explicitly visual/spatial context. They do not establish a 2026 sensor calibration or authorize illumination estimation, so no 2026 PARBAR observation or illumination result is produced.

The render worker deliberately keeps its presentation-only ground skirt alive until process shutdown. Deleting it immediately after OptiX capture can leave a stale GPU reference. The parent validates completed per-session reports, image dimensions, and scene hashes, and restores protected project bytes after every worker attempt.
