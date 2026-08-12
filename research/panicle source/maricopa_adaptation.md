# Applying panicle biology to the Maricopa experiments

## What is directly useful

The closest public analogue is the University of Arizona Maricopa Agricultural Center (MAC) field-phenomics work, not a generic greenhouse protocol. Its sorghum trials were conducted at 33°04'24.8" N, 111°58'25.7" W (366 m elevation) in 2020 and 2022, used the AZMET Maricopa station, and combined RGB, thermal, PSII fluorescence, and structured-light 3D sensing across season-long managed water treatments. The water-limited treatment was approximately 60% of well-watered irrigation and began about 50 days after emergence. This is a valuable template for event logging and sensing, especially where panicle stress must be separated from earlier canopy effects.

The current project should **not** inherit those dates, treatment amounts, coordinates, or genotype responses by default. Local project documentation explicitly identifies Maricopa/AZMET as a regional proxy and does not yet establish the exact experimental plot or heading timeline.

## Recommended panicle observation record

Record these per tagged plant if feasible; otherwise record a fixed, representative sample per plot and retain the sampling rule.

| Variable | Definition | Cadence / method |
| --- | --- | --- |
| Panicle initiation estimate | Dissect a small sentinel sample or infer from validated leaf-stage calibration | Once around transition; this is normally hidden and cannot be recovered from late images alone. |
| Boot score | 0=no swelling, 1=early boot, 2=late/swollen boot | Daily to every 2 days approaching heading. |
| First emergence | Date/time when any panicle tissue clears the flag-leaf sheath | Per plant. Define the threshold before collecting. |
| Exsertion fraction | 0–100% of final panicle length visibly outside sheath | Daily around heading; photograph side-on against scale. |
| Panicle geometry | Exposed length, maximum width, apparent compactness, branch angle class | At full exsertion, and again at maturity. Use the same view/scale. |
| Anthesis onset and zone | Fresh anthers visible in top/middle/base third | Morning daily observations for at least a week. This captures the downward wave. |
| Fertility / grain set | Filled grains divided by candidate fertile sessile positions from a defined subsample | Post-set and maturity; score top/middle/base separately. |
| Grain fill | Grain moisture plus 100-grain mass or individual grain mass by zone | Repeated destructive subsamples or maturity sample; preserve sampling position. |
| Stress covariates | Irrigation applied, soil water status, air temperature, RH/VPD, canopy temperature, wind | Plot/time aligned; retain AZMET and sensor provenance. |

## Minimum experimental event model

Use biological events rather than only days after sowing:

`emergence -> leaf-stage calibration -> panicle initiation (latent) -> boot -> first emergence -> full exsertion -> anthesis onset -> anthesis complete -> grain set -> physiological maturity`

For each transition, store `time`, `plant/plot`, `observer or sensor`, `confidence`, `treatment`, and `evidence`. The project already has a boolean `panicle_emerged`; preserve it, but expand it into dated first emergence and exsertion percentage so it can drive a continuous model.

## Maricopa-focused stress interpretation

- Match high-temperature and water-deficit summaries to anther/flower state, not simply calendar week. A 40 °C day during pre-anthesis floral differentiation asks a different question from the same day during late filling.
- Monitor **canopy/panicle-adjacent temperature** as well as weather-station air temperature. The MAC phenomics reference demonstrates thermal and 3D data as complementary signals; high wind and sensor heat load can degrade those measurements, so preserve QC flags.
- If water limitation starts before heading, test for delayed heading/exsertion and altered panicle dimensions before attributing a lower harvest grain count entirely to pollination failure.
- During anthesis, sample the top, middle, and basal third separately. Because flowering travels downward, each zone can experience a different heat or water history at the moment of fertility determination.
- For a simulation, use stress as a modifier of: (a) developmental rate, (b) fertile sessile-spikelet fraction, and (c) final kernel mass. Those three effects are more interpretable than one undifferentiated yield penalty.

## Suggested image / scanner protocol

1. Take a fixed-distance side image against a metric scale at first emergence, 50% exsertion, full exsertion, anthesis, early fill, and maturity.
2. At anthesis, add a close-up of each panicle zone in the morning. Fresh yellow anthers are a usable event indicator.
3. Capture a top/oblique image at full exsertion for width and branch-density estimates. Avoid inferring panicle shape from a single silhouette.
4. If the field scanner is available, retain raw point-cloud/thermal image IDs alongside the panicle event record. Use 3D height/volume as a validation signal, not a proxy for seed set without calibration.

## Immediate project changes suggested by the evidence

- The current L-system has a `SorghumPanicleBud` placeholder and no current panicle geometry. Implement growth stages and a branch/triad architecture before spending effort on grain shader detail.
- Give each plant an observed or simulated `panicle_emerged_time`, `anthesis_start_time`, and `anthesis_duration`; derive visibility and grain state from those rather than toggling a single mature head.
- Maintain a Maricopa scenario configuration separate from global sorghum defaults. It should accept local AZMET weather and irrigation inputs without asserting that the public MAC trial is the current experiment.
