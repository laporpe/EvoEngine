# August 11 A/B/C endpoint field

This workflow creates one deterministic 6x10 L-system field and three endpoint
descriptors from the selected August 11 workbook archive. It constrains the
final generated snapshot only. The intermediate growth path is intentionally
not calibrated.

## Contract

| Item | Value |
| --- | --- |
| Experiment ID | `Sorghum2026_6x10_2026-08-11` |
| Layout | Six rows by ten columns; A, A, B, B, C, C |
| Population | 20 generated plants per genotype |
| Source mapping | A = range 75, B = range 74, C = range 73 |
| Technical priors | Existing July `MeasurementStage02` A/B/C descriptors, which are BTX-derived |
| Endpoint mode | `finalize_snapshot_morphology: true` |
| Reproduction | A and B absent; C emerged in all five measured plants |
| Instrument context | Existing three-rig PARBAR scene context; no illumination result claimed |

The immutable source copy is outside the repository. By default, the importer
looks for `sources/Sorghum2026_6x10_2026-08-11` beside the repository; use
`--source-dir` to select another location. The source contains the original zip
plus the three selected workbooks. Leaf dimensions for range 75 are dated
August 12 in the workbook; its internode and angle/tiller measurements are dated
August 11. Those family-level dates are preserved rather than silently
rewritten.

The normalizer reads the workbooks at runtime. It retains source workbook,
sheet, cell, units, missing tokens, and SHA-256 provenance. No August 11
measurement is embedded in the scripts.

## Measured endpoint means

| Genotype | Height (m) | Main-culm leaves | Primary tillers | Panicle rate | Panicle length/width (m) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1.402 | 13.2 | 2.8 | 0.0 | not measured |
| B | 2.190 | 13.2 | 2.2 | 0.0 | not measured |
| C | 2.220 | 14.2 | 1.8 | 1.0 | 0.201 / 0.068 |

Leaf, internode, diameter, tiller-angle, and leaf-angle rank distributions are
also sourced from the workbooks. The device-angle conversion remains
`90 - abs(Y)` pending confirmation of the device coordinate system.

The engine allocates a variable number of phytomers, so a normalized rank curve
does not automatically preserve a measured plant's aggregate stem length or
maximum leaf dimensions. The calibration pass samples each descriptor and
writes multiplicative allocation corrections to
`descriptor_calibration_overrides.json`. The correction is computed from the
normalized tables and sampled engine output; it does not introduce fixed trait
values in code.

## Outputs

Within the Digital Agriculture Project:

- `Data/Experiments/Sorghum2026_6x10_2026-08-11/` contains normalized tables,
  source hashes, targets, calibration, the 60-plant scene manifest, and
  validation reports.
- `Assets/GeneratedAssets/Experiments/Sorghum2026_6x10_2026-08-11/Descriptors/FinalSnapshot/`
  contains `GenotypeA.sorghumls`, `GenotypeB.sorghumls`, and
  `GenotypeC.sorghumls`.
- `Assets/GeneratedAssets/Experiments/Sorghum2026_6x10_2026-08-11/Scenes/Sorghum_6x10_FinalSnapshot2026-08-11.evescene`

## Spatial review renders

`PythonBinding/sorghum_2026_6x10_aug11_review.py` produces an 18-view review set and a five-second endpoint-growth animation under `out/realism_review/Sorghum2026_6x10_2026-08-11/`. Whole-field framing uses the union of all 60 plant world-space bounding boxes. Inter-row and intra-row cameras use measured root rows, adjacent plant envelopes, and a 1.65 m walking eye height. Every camera position and its nearest plant-envelope clearance are recorded in the render manifest.

The animation is an illustrative linear-GDD interpolation. August 11 measurements constrain only its final frame; the script verifies that final frame against all 60 saved scene-manifest plants, including the A/B vegetative and C panicle-emergence states.

```powershell
py -3.13 PythonBinding/sorghum_2026_6x10_aug11_review.py
```
  is the generated field.

The saved field passed the endpoint gate. Its genotype means were 1.349, 1.995,
and 2.161 m for A, B, and C; height relative errors were 3.8%, 8.9%, and 2.6%.
All count errors were at most 0.45 plants. C had 20/20 emerged panicles, mean
rachis length 0.199 m, and reconstructed mean width 0.066 m. A and B had no
emerged panicles.

## Reproduction

From the repository root with the Debug Python binding built:

```powershell
python PythonBinding\sorghum_2026_6x10_aug11_data.py
python PythonBinding\sorghum_2026_6x10_aug11_descriptors.py
python PythonBinding\sorghum_2026_6x10_aug11_calibrate.py --sample-count 300
python PythonBinding\sorghum_2026_6x10_aug11_descriptors.py
python PythonBinding\sorghum_2026_6x10_validate_descriptors.py `
  --config Debug `
  --runtime-package-dir out\build\vs2026-x64\EvoEngine_App\Debug\Packages `
  --data-root Resources\DigitalAgricultureProject\Data\Experiments\Sorghum2026_6x10_2026-08-11 `
  --report Resources\DigitalAgricultureProject\Data\Experiments\Sorghum2026_6x10_2026-08-11\descriptor_engine_validation.json `
  --sample-count 300 --require-acceptance
python PythonBinding\sorghum_2026_6x10_aug11_scene.py
python PythonBinding\sorghum_2026_6x10_aug11_validate.py
```

The field seed is fixed for reproducibility. Finalization completes authored
organ dimensions without claiming that the uncalibrated path or phenological
maturity flags match the field history.
