# How sorghum panicles grow

## Bottom line

A sorghum head is a determinate, branched inflorescence, not a leaf-like bud that simply swells into a grain-covered oval. The central rachis produces primary branches, which can produce higher-order branches. Branch tips carry a **triple-spikelet unit**: one central sessile spikelet (normally fertile in grain sorghum) with a pedicellate spikelet on each side (normally arrested or male/sterile). This architecture, the opening of the panicle from the boot, and the top-to-bottom flowering wave should drive both the model and measurements.

## Developmental sequence

| Phase | What is growing | Visible field cue | Modeling / measurement consequence |
| --- | --- | --- | --- |
| Vegetative apex | Stem and leaf primordia only | Leaf stage advances | Do not render a visible panicle. Calendar days alone are not transferable among genotypes or sowing dates. |
| Floral transition and branch initiation | The shoot apex becomes an inflorescence meristem; rachis and branch meristems form | Still internal | Architecture is being set before heading. Water stress here can alter timing and potential sink size. |
| Triple-spikelet and floral-organ formation | Sessile/pedicellate triplets form; florets and anthers differentiate | Young panicle remains enclosed in the flag-leaf sheath | This is a fertility-sensitive interval; include a hidden `boot` state rather than jumping from stem to an exposed head. |
| Panicle expansion / boot | Branch axes elongate and panicle mass increases within the sheath | Swollen boot; flag leaf present | Panicle volume can grow while its visibility remains zero. Separate internal panicle size from exsertion. |
| Heading / emergence | Panicle emerges from the flag-leaf sheath | Upper head becomes visible, then increasing exsertion | Record first emergence and percent exserted per plant or plot. Existing project data already exposes a `panicle_emerged` field. |
| Anthesis | Anthers exert, dehisce, pollination/fertilization occur | Fresh pale/yellow anthers; activity starts toward the top and moves downward | Model as a moving band along the rachis, typically completing over several days, not one instant. Morning checks are essential. |
| Grain set and fill | Fertilized sessile florets enlarge into caryopses; branches and rachis support a growing grain load | Green head to colored/firm grain, depending on genotype | Store grain number separately from grain size; heat during fill can reduce final individual grain mass. |
| Maturity / dry-down | Filling ends; grains desiccate and head colour changes | Hard grain, senescing plant | Use grain moisture or a maturity rule, not merely head colour. |

The anther study in this folder aligns the internal sequence with leaf stages: reproductive development begins around the eight-leaf phase in its material; triple-spikelet/branch formation, floral-organ formation, anther maturation, and heading then overlap successive leaf/boot stages. Treat those leaf-stage labels as developmental landmarks rather than universal dates.

## Architecture that matters

- **Rachis:** the central axis that defines panicle length and flowering order.
- **Primary / secondary / tertiary branches:** their count, attachment density, length, and angle generate the compact-to-open panicle silhouette. Genotype and environment alter these strongly.
- **Triple spikelets:** one sessile spikelet plus two pedicellate spikelets at a branch terminus. In standard grain sorghum, the sessile spikelet supplies the grain; pedicellate spikelets commonly abort. Fertile pedicellate spikelets are a special genotype/developmental outcome, not the default.
- **Panicle form:** open/loose, semi-compact, and compact heads can have very different branch angles and densities even at similar total grain number. Parameterize form rather than scaling a single ellipsoid.

The local close-up photographs deliberately show both the whole-panicle silhouette and the flower/triad scale. Use them together: large-scale density cannot reveal spikelet fertility, and a macro flower image cannot determine branch distribution.

## Flowering and grain formation

Anthesis starts shortly after panicle emergence and generally progresses from the upper panicle toward the base. A plant is therefore not uniformly at anthesis: top, middle, and basal zones can be at different reproductive states on the same morning. Flower opening and pollen release are concentrated in the morning, so a single afternoon visual check can miss the biologically meaningful event.

This creates a useful model state for every branch or normalized rachis position:

`pre-anthesis -> anthesis-active -> fertilized/setting -> filling -> mature`

Advance this state with a top-to-bottom phase offset, then modulate it by genotype and stress. It supports a realistic early grain-size gradient and makes heat events at flowering interpretable by the zone that was actually open.

## Heat and water stress: the panicle-specific windows

The strongest recurring result is that stress timing matters at least as much as seasonal average stress.

- In the controlled/field study by Prasad et al. (2015), short high-temperature episodes from roughly 10 to 5 days before anthesis and from 5 days before through 5 days after anthesis were especially damaging to floret fertility. Hot conditions during subsequent grain filling chiefly reduced individual grain weight.
- The pollen/pistil work identifies both male and female functions as heat-sensitive; fertility loss should not be reduced to a purely visual panicle-size effect.
- ICRISAT drought work reports that stress around panicle initiation can delay initiation and flowering, prolong the initiation-to-flowering interval, and under sufficiently severe water deficit temporarily stop panicle development. Recovery after irrigation is possible, so a model should represent delayed progression rather than only permanent loss.
- Pre-anthesis ovary development sets an important part of potential kernel size. Grain filling cannot fully compensate for a restricted pre-flowering sink.

Do not interpret a generic ambient temperature cutoff as a universal fertility threshold. The relevant response varies with day/night temperature, duration, vapor demand, plant water status, genotype, and which floral zone was at the sensitive state.

## Implementation implications for this project

1. Replace a single `PanicleBud` placeholder with an internal panicle state plus a separate exsertion state.
2. Generate a rachis and hierarchical branch skeleton first, then attach triple-spikelet units at terminal positions. Populate mature grains primarily on fertile sessile spikelets.
3. Let panicle compactness arise from branch length, branch angle, and branch-order density—not just scale.
4. Drive heading, anthesis, set, and filling from a developmental clock with top-to-bottom offsets. Couple the clock to observed leaf stage / heading when available.
5. Add explicit stress events with stage-specific effects: delayed initiation/heading, reduced fertile spikelet fraction, and shortened or weakened grain filling.
6. Keep genotype parameters separate from seasonal forcing. A Maricopa weather trace should alter a named genotype's trajectory, not silently redefine panicle architecture.

## Primary sources in this collection

- Hilley et al., *MSD1 regulates pedicellate spikelet fertility in sorghum through the jasmonic acid pathway* — structural and fertility basis.
- *Morphological analysis and stage determination of anther development in Sorghum* — 18-stage anther framework and field-visible staging bridge.
- Prasad et al., *Impact of high temperature stress on floret fertility and individual grain weight of grain sorghum* — sensitive reproductive windows.
- *Pre-anthesis ovary development determines genotypic differences in potential kernel weight in sorghum* — early sink capacity.
- ICRISAT guide/development chapters — practical phenology, anthesis, and field context.
