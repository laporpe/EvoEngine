# 2026 6x10 A/B/C full-lifecycle render

## Authoritative field

The authoritative panicle deliverable retains the measured 2026 `GenotypeA`, `GenotypeB`, and `GenotypeC` identities, experimental A,A,B,B,C,C row order, and 20 plants per genotype. For this render revision, all three identities deliberately reuse `Assets/ManualAssets/Descriptors/BTX.sorghumls` for non-panicle growth. The A/B/C labels therefore express field ownership only; they do not imply distinct vegetative morphology in this deliverable.

The BTX descriptor currently serializes no panicle-specific fields. The authoritative profile therefore keeps its reproductive presentation explicitly separate from BTX vegetative morphology: it uses a shared 0.82 m exserted peduncle, 0.34 m rachis, 0.18 m primary-branch envelope, 20 primary branches, seven spikelet triads per branch, and a mature rust-brown color. These are transparent presentation/model parameters, not measured A/B/C reproductive traits. The older Stage-2 A/B/C vegetative render is retained only as `abc-measured-vegetative-reference` and is superseded for presentation.

The renderer performs a final-state engine preflight before capturing any frames. It first evaluates the shared descriptor target, currently 660 GDD, and calculates a lower maturity bound as `max target GDD + max sampled organ delay`. The current maximum delay is 261 GDD: the larger of 240 GDD vegetative maturity and the native 1 + 260 GDD panicle initiation/maturity interval. The resulting 921-GDD floor is applied to every plant. If any sampled plant still has a developmental module, an immature leaf/internode, or an immature rachis/branch/spikelet, the common field clock advances in 20-GDD steps. The other plants wait while the latest plant reaches its last possible state.

A deliverable is valid only when all 60 plants pass every native final-state rule: panicle emerged, vegetative organs mature, panicle organs mature, no developmental modules remain, and whole-plant maturity is 60/60. It also requires every mature panicle tip to clear its own vegetative canopy by at least 0.08 m, preventing a metadata-pass/visually-hidden failure. The current seeds require an endpoint of 1081 GDD, a 421-GDD extension beyond the descriptor target. At that endpoint the minimum vegetative and panicle growth progress are both exactly 1.0, and the least canopy clearance is 0.111 m.

The final output contains the same 1,000 source renders encoded at three playback time scales:

| Playback | Duration | Use |
| --- | ---: | --- |
| 12 fps | 83.33 s | Slow study view |
| 24 fps | 41.67 s | Standard review |
| 48 fps | 20.83 s | Fast overview |

States 1, 100, 250, 500, 750, and 1000 are identified as milestone stills in the manifest. All encodings span the complete GDD lifetime; playback speed does not change the biological state mapping.

## Scientific boundary

Field ownership comes from the measured A/B/C pipeline, while vegetative morphology is intentionally shared from the manual BTX descriptor. The experiment did not measure genotype-specific reproductive architecture or dates of heading, anthesis, grain filling, or maturity. The shared A/B/C panicle structure, exsertion, color, and timing are therefore explicit SorghumLS model outputs, not observations of reproductive differences between A, B, and C.

The fixed PARBAR rigs and midday lighting are visual context only. No 2026 illumination or sensor measurement is inferred from this render.

## BTx/Pawaga reference demonstration

BTx and Pawaga are retained as a separate, non-authoritative reference profile named `btx-pawaga-reference`. It relabels the marker positions and uses the manual BTx/Pawaga descriptors. It is not the measured A/B/C field and must be written to a separately named output directory. Its report ownership is `reference_demonstration_not_the_measured_abc_field`.

## Run

Authoritative A/B/C deliverable:

```powershell
python PythonBinding\sorghum_2026_6x10_gdd_timelapse.py
```

Optional BTx/Pawaga reference demonstration:

```powershell
python PythonBinding\sorghum_2026_6x10_gdd_timelapse.py `
  --field-profile btx-pawaga-reference `
  --output-dir out\panicle_timelapse\sorghum_2026_6x10_btx_pawaga_reference
```

The authoritative output directory is `out/panicle_timelapse/sorghum_2026_6x10_abc_btx_vegetative_full_lifecycle_1000_native_1080p`. It contains 1,000 PNG frames, per-state JSON records, three verified H.264 videos, and `sorghum_2026_6x10_abc_btx_vegetative_full_lifecycle.json`.

`docs/sorghum-2026-panicle-render-freeze.json` records the frozen source, milestone-frame, report, video, and asset-commit hashes. The portable deliverable is backed up under `G:/My Drive/Sorghum/2026-08-12_6x10_ABC_BTX_Vegetative_Full_Maturity_Visible_Panicles_1081GDD_Native_LSystem`.

The older Blender generator is retained only as a presentation reference. Its synthetic boot, anthesis, grain-color, and A/B/C panicle-style animations are not the native SorghumLS deliverable.
