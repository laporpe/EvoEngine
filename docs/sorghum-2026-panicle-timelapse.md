# 2026 6x10 A/B/C full-lifecycle render

## Authoritative field

The authoritative panicle deliverable is the measured 2026 `GenotypeA`, `GenotypeB`, and `GenotypeC` field. It retains the experimental A,A,B,B,C,C row order and 20 plants per genotype. `PythonBinding/sorghum_2026_6x10_gdd_timelapse.py` reads the `MeasurementStage02` descriptors and renders 1,000 ordered SorghumLS states from 0.1% through 100% of the full-lifecycle GDD endpoint.

The renderer performs a final-state engine preflight before capturing any frames. A deliverable is valid only when all 60 plants have `panicle_emerged=true`. It first tests the shared descriptor target, currently 660 GDD. If that endpoint is insufficient, it advances in 20-GDD steps up to 1.5 times the descriptor target and records the extension in the manifest. Failure to reach 60/60 aborts the render and video assembly.

The final output contains the same 1,000 source renders encoded at three playback time scales:

| Playback | Duration | Use |
| --- | ---: | --- |
| 12 fps | 83.33 s | Slow study view |
| 24 fps | 41.67 s | Standard review |
| 48 fps | 20.83 s | Fast overview |

States 1, 100, 250, 500, 750, and 1000 are identified as milestone stills in the manifest. All encodings span the complete GDD lifetime; playback speed does not change the biological state mapping.

## Scientific boundary

The vegetative morphology and field ownership come from the measured A/B/C pipeline. The experiment did not measure genotype-specific reproductive architecture or dates of heading, anthesis, grain filling, or maturity. Native panicle structure and timing are therefore model outputs using the shared SorghumLS reproductive defaults, not observations of A/B/C reproductive differences.

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

The authoritative output directory is `out/panicle_timelapse/sorghum_2026_6x10_abc_full_lifecycle_1000_native_1080p`. It contains 1,000 PNG frames, per-state JSON records, three verified H.264 videos, and `sorghum_2026_6x10_abc_full_lifecycle.json`.

`docs/sorghum-2026-panicle-render-freeze.json` records the frozen source, milestone-frame, report, video, and asset-commit hashes. The portable deliverable is backed up under `G:/My Drive/Sorghum/2026-08-12_6x10_ABC_Full_Lifecycle_Native_LSystem`.

The older Blender generator is retained only as a presentation reference. Its synthetic boot, anthesis, grain-color, and A/B/C panicle-style animations are not the native SorghumLS deliverable.
