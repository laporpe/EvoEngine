# Sorghum render scripts

The Python that produced the sorghum growth videos and the BTx623 / Pawaga illumination
figures. Everything here drives EvoEngine through `PyDigitalAgriculture`; nothing renders
without a built engine.

```
abc-growth/    genotype A/B/C growth videos, heat scenarios, weekly descriptor fitting
btx-pawaga/    BTx623 & Pawaga canopy illumination, PARbar transmittance calibration
data/          AZMet hourly weather and the weekly field record
```

## What you need before anything runs

**1. EvoEngine, built with the Python bindings.** Branch `sorghum-growth-render-apis`. The
scripts call bindings that exist only on this branch — `SetNishitaSky`,
`CreateEntityFromSorghumGrowthStages`, `SetSorghumGrowthStagesTime`, `SetEntityPosition`.
Build `x64-Release` with the `PythonBinding` target; the scripts expect
`out/build/x64-Release/PythonBinding/Release/`. Needs Vulkan and CUDA — the rasteriser is
Vulkan, and the illumination work uses OptiX.

**2. The `DigitalAgricultureProject` submodule.** The project and scene files live there,
not in this repo. Pinned commit is `f8a931b`, which is on `penanito/codex/sorghum-gpu-field-geometry`
— you will need that remote added, as the commit is not on `origin`:

```bash
git submodule update --init --recursive Resources/DigitalAgricultureProject
```

Note the submodule working tree on the authoring machine also carried **uncommitted**
changes to `test_lsystem_sorghum.eveproj` and several untracked asset folders
(`Assets/GrowthStagesGdd`, `Assets/HandoffTuned`, `Assets/BtxPawagaDrafts`). Those are not
captured here. If a scene fails to load, this is the first thing to suspect.

**3. Genotype descriptors.** `Resources/HandoffTest/Assets/Descriptors/` — the six
`.sorghumls` files for genotypes A, B and C at weeks 6 and 7, committed alongside this
branch. `render_abc_growth.py` copies them into the project and rewrites their thermal
timing per run; it never edits the originals.

**4. Python.** 3.9 (matching the binding build), with:

```
numpy==2.0.2  pandas==2.3.3  imageio==2.37.2  imageio-ffmpeg==0.6.0
Pillow==11.3.0  matplotlib==3.9.4  pvlib==0.13.0  tqdm==4.67.3
```

`imageio-ffmpeg` is what writes the MP4s. The engine DLLs are added to the search path by
`configure_engine_imports()` at import time, so the interpreter must be able to see the
CUDA runtime as well.

**5. Point the scripts at your checkout.** Paths resolve from environment variables, each
falling back to the authoring machine:

| variable | meaning |
|---|---|
| `EVOENGINE_ROOT` | your EvoEngine checkout — **set this** |
| `SORGHUM_FIELD_CSV` | weekly field record; defaults to `data/` here |
| `SORGHUM_HOURLY_WEATHER` | AZMet hourly file; defaults to `data/` here |

Three scripts still carry absolute paths, none of them on the render path:
`set_tiller_lean.py` and `set_tiller_leaf_counts.py` read raw field measurements from a
`Downloads` folder (they re-derive descriptors from scratch — not needed to render), and
`btx-pawaga/batch_seeds.py` hard-codes a `conda.exe` location.

## Reproducing the growth videos

```bash
export EVOENGINE_ROOT=/path/to/EvoEngine

# baseline: sorghum's 95 F ceiling, nights as observed
python abc-growth/render_abc_growth.py --week 7 --weather --minutes-per-frame 10 \
  --weather-from 2026-08-06 --weather-to 2026-08-08 \
  --fps 24 --width 1920 --height 1080 \
  --upper-cap-f 95 --night-warming-f 0 --panel-min 0.35 --panel-max 2.00 \
  --scenario-label "95 F cap  -  nights as observed" \
  --output out/nights_current.mp4

# treatment: same ceiling, nights +5 F, accrued from planting
python abc-growth/render_abc_growth.py --week 7 --weather --minutes-per-frame 10 \
  --weather-from 2026-08-06 --weather-to 2026-08-08 \
  --fps 24 --width 1920 --height 1080 \
  --upper-cap-f 95 --night-warming-f 5 --panel-min 0.35 --panel-max 2.00 \
  --scenario-label "95 F cap  -  nights +5 F" \
  --output out/nights_warm.mp4
```

Roughly 40 minutes each at 1080p on an RTX-class GPU. Run them **detached**
(`nohup … &`) — a foreground wrapper getting killed will take the render with it.

`probe_growth_window.py` sweeps the season and reports culm tip height and panicle status
per genotype; that is how the August window was chosen. It needs no arguments.

A few flags worth knowing:

- `--panel-min/--panel-max` pin the chart axis. **Always set these when rendering a pair** —
  two charts meant to be compared must share one scale, or the comparison misleads.
- `--steady-light` holds the sun at one hour for every frame. Sampling several hours per day
  makes the picture swing dark-bright-dark a few times a second, which is a strobe.
  Season-length videos should use it.
- `--heat-source thermal` (the default) spreads each day's heat over all 24 hours. `solar`
  confines it to daylight, which is visually intuitive and biologically wrong: extension
  follows meristem temperature, not light.
- `--minutes-per-frame` resamples the hourly weather for short, high-frame-count windows.

## Exporting to Blender

`abc-growth/export_plots_for_blender.py` grows the plots to a chosen thermal age
and writes them as a model file:

```bash
python abc-growth/export_plots_for_blender.py --gdd 1858 --columns 5 --format fbx obj
```

Each plant becomes its own named node, and each plant's internodes, leaves and
panicle stay as separate objects under it - a 15-plant stand exports as 45 named
objects, so material assignment and selection in Blender work per organ.

Working formats, measured on a 15-plant stand at 874k triangles:

| format | size | notes |
|---|---|---|
| `.fbx` | 185 MB | **use this for Blender** - materials and hierarchy |
| `.obj` | 137 MB | plus `.mtl` and a `textures/` folder; ASCII, so large |
| `.ply` | small | geometry only |
| `.stl` | small | geometry only, no colour |
| `.eveprefab` | - | native format, for round-tripping into EvoEngine |

**glTF/GLB are refused by design.** Assimp's glTF2 writer faults on these scenes
rather than returning an error, which takes the whole interpreter down. The
engine now rejects those extensions with a message pointing at `.fbx`. `.dae` is
not compiled into this Assimp build.

Raise the mesh quality before exporting. The videos run `--leaf-vsub 0.02
--leaf-hsub 4`, which is tuned so the subdivisions survive a 1080p pixel grid and
no further; geometry that gets re-lit in Blender deserves more. `0.012 / 6` gives
874k triangles for 15 plants and is a reasonable starting point.

The export is a snapshot at one thermal age - the plants are rebuilt from the
L-system at whatever GDD you grow to, so pick `--gdd` to match the growth stage
you want rather than expecting an animated sequence.

For **growth animation**, `GetSorghumLsGeometrySnapshots()` exposes the same native
culm, leaf and panicle meshes as owned arrays. `GrowthGeometryExporter` records
samples from your existing simulation without changing growth settings. The
Blender builder creates an animated USD cache and an editable Cycles scene.
See [the growth export quick start](../../docs/sorghum-growth-blender.md) for the
reusable API, A/B/C example, validation, and Blender handoff.

## Interpreting the output

`render_abc_growth.py` plots **culm tip height**, derived from internodes. Internodes only
elongate, so the trace cannot go backwards. The obvious alternative, `plant_height_m`, is
the top of the geometry bounding box — a leaf arching over under gravity pulls it *down*
by several centimetres while the plant is still growing, which over a short window is
comparable to the growth itself. Use culm tip height for anything short.

Heat scenarios change the **night** temperature, not a uniform offset. At this site in
August a uniform +8 F moves the heat total by +0.3 %, because most hours already sit above
the ceiling; nights still have headroom. Warming is accrued from planting rather than only
across the rendered window — three days of warmer nights is worth about 0.3 cm and is
invisible, a season of them is worth roughly 10 cm and three days of development.

`btx-pawaga/METHODS.md` and `EXPERIMENT_LOG.md` carry the equivalent detail for the
illumination work, including the transmittance targets and the screening rules.

## Not included

Rendered outputs — videos, `results/`, `renders/` — are left out to keep the branch small.
The BTx/Pawaga run outputs alone are over 100 MB.
