# Sorghum growth export: EvoEngine → Blender

Use this workflow to record **the evaluated SorghumLS geometry from your own simulation**, then light, shade and render it in Blender. The reusable API has no A/B/C requirement and does not change growth settings. `export_sorghum_growth.py` is a separate, runnable three-genotype example.

## 1. Prepare your Python runtime

Use the Python interpreter matching your `PyDigitalAgriculture` build. From the repository root:

```powershell
python -m pip install -r PythonBinding/requirements-growth-export.txt
cmake --build <your-configured-build> --config Release --target PyDigitalAgriculture --parallel 8
```

The binding must be built from this branch, with DigitalAgriculture, LSystem, DatasetGeneration, EcoSysLab, Gpr and BillboardClouds, and the CUDA service enabled. Existing shared binding helpers require CUDA/OptiX even though the getter reads CPU arrays. PhysX can be disabled; runtime initialization needs Vulkan. Use the repository's normal CMake configuration for your platform. Do not reuse a binding compiled before `GetSorghumLsGeometrySnapshots` was added.

`PyResourceCopy` copies the Python helper module beside the built binding. Alternatively, add the repository's `PythonBinding` directory to your script's Python path. Blender is a separate process: the tested Blender 5.0.1 includes NumPy and the `pxr` USD writer. Do not install the engine binding into Blender's Python.

## 2. Capture your existing simulation

After initializing your project, assigning your descriptors/seeds/quality, and evaluating initial growth as usual:

```python
from sorghum_growth_export import GrowthGeometryExporter

export = GrowthGeometryExporter("C:/exports/my_trial", fps=24)
export.capture(evo, initial_gdd)  # capture the current evaluated state

for gdd in remaining_gdd_schedule:
    # Your existing growth call, retaining your current seeds/settings.
    evo.AdvanceSorghumLsPlantsToGdd(float(gdd), -1, True)
    export.capture(evo, float(gdd))

manifest_path = export.finish()
print(manifest_path)
```

Here `evo` is your initialized `PyDigitalAgriculture` module. Use an absolute, new/empty output directory. The first capture can be at any nonnegative GDD; subsequent captures must be nondecreasing. You can capture just one frame for a still. If your orchestration already advances growth differently, keep it: insert `capture()` after that call instead. The export methods never advance growth, change quality, finalize morphology, reparent plants, or replace descriptors.

The recording supports any fixed roster of SorghumLS entities, with stable identities and seed metadata. Stems, leaves and panicles may emerge, disappear and change topology. Adding/removing entire plants or changing their identities/descriptors requires a new recording. For selected plants, use `export.write_frame(selected_snapshots, gdd)` with dictionaries from `evo.GetSorghumLsGeometrySnapshots()`.

`finish()` writes `manifest.json` only after successful captures. It also supplies a default overview camera/daylight setup; optional `camera=` and `lighting=` dictionaries replace those defaults. These are presentation settings, not a capture of your engine camera or environment. Requested and actually evaluated GDD are stored separately in each frame's metadata. Optional `metadata=` on the exporter stores your experiment provenance.

### Runnable A/B/C example

```powershell
python PythonBinding/export_sorghum_growth.py --build out/build/growth-python --output out/exports/my_abc_run --frames 240 --fps 24
```

This example initializes an isolated project with the committed A/B/C week-7 descriptors, seed base 202609020 and spacing 2.2 m. It uses the existing ABC timing calibration (plastochron 100, maturity 800), disables snapshot finalization, and samples 0–2320.35 GDD. Only C's descriptor enables a panicle. These choices belong to the example, not the reusable exporter. `--start-gdd`, `--end-gdd`, `--frames`, `--seed`, `--spacing`, `--vertical-step` and `--horizontal-steps` control it. Thermal time is linear, not a weather-derived calendar.

## 3. Create the Blender scene once

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' --background --factory-startup --python-exit-code 1 --python Scripts/blender/build_sorghum_growth_cache.py -- --manifest C:/exports/my_trial/manifest.json --validate-all
```

The default leaf atlas is under `Resources/DigitalAgricultureProject/Assets/GeneratedAssets/Materials/SorghumLeaves/LeafAtlas/atlas`. Initialize that pinned submodule (`git submodule update --init Resources/DigitalAgricultureProject`) or supply `--leaf-atlas <atlas-directory>`. The builder copies textures beside the scene and makes cache/texture paths relative.

Open `C:/exports/my_trial/blender/abc_growth.blend` in Blender. Scrub the timeline: stable per-plant stem, leaf and panicle objects load time-sampled meshes through USD cache modifiers. Initially empty organs are included. The generic file names retain `abc_growth` for compatibility; recordings can contain other cultivars and plant counts.

**Beautify freely:** replace or rename materials, paint textures, change the camera, lights, ground and render settings. Save a copy such as `beautiful.blend`. Keep the USD cache modifier and plant transforms intact to preserve geometry. Keep materials linked to the object, as initially configured, so changing mesh data does not replace them. The validator deliberately allows presentation/material edits while rejecting changes to plant positions or topology. Modifiers that deform, subdivide or displace plants change the geometry contract.

Keep the `.blend`, `growth.usdc`, and `textures/` together when handing off the scene. The NPZ frames and manifest are also needed to rerun source comparisons, but Blender playback itself uses only the USD cache. You may import `growth.usdc` directly into another Blender scene instead; disable “Visible Only” during import so initially empty organs are retained.

## 4. Render the edited scene

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' --background --python-exit-code 1 --python Scripts/blender/build_sorghum_growth_cache.py -- --manifest C:/exports/my_trial/manifest.json --reuse-scene --scene C:/exports/my_trial/blender/beautiful.blend --render-output C:/exports/my_trial/blender/beauty/renders --render
```

`--reuse-scene` preserves the saved materials, camera, lights, resolution and samples. Explicit `--width`, `--height` or `--samples` override their corresponding settings. `--frame-start` / `--frame-end` select a valid subset for previews or resuming the same render. Keep FPS equal to the manifest. The initial scene uses Cycles/OptiX where available and otherwise CPU; select the appropriate device on another machine. Deformation motion blur starts disabled because vertex identities can change with topology.

The builder refuses to overwrite an existing scene. Reuse it to preserve edits, or choose a fresh `--output` for another scene build. Use a **new render directory for each changed presentation**. `renders/source.json` binds frames to the source manifest, USD cache, saved scene, external textures and render settings, preventing mixtures across runs. You can resume the same unchanged presentation into its existing directory. Old scenes/frames made before these source records were introduced must be rebuilt in a new directory.

For a quick default movie, append `--render` to the scene-creation command; the default is 1280×720 at 32 Cycles samples.

## 5. Encode the movie

```powershell
python Scripts/blender/encode_sorghum_growth.py --manifest C:/exports/my_trial/manifest.json --renders C:/exports/my_trial/blender/beauty/renders
```

This checks the source binding and all expected PNGs, encodes H.264, and verifies the decoded frame count. It creates `abc_growth.mp4`, `poster.png`, `growth_contact_sheet.jpg`, and `render_report.json` beside the selected renders directory. Omit `--renders` for the default `blender/renders` sequence. `--hold-seconds` defaults to 1.5; it is rounded to an integer number of frames. H.264 requires even pixel dimensions.

## Geometry contract and current limits

- `GetSorghumLsGeometrySnapshots()` copies current native stem/leaf/panicle positions, normals, UVs, colors and triangle arrays into owned NumPy buffers, with plant world transforms, identities and organ metadata. These snapshots are the inputs used by the SorghumLS mesh renderers. CPU/GPU mesh quality is not changed by capture.
- Source NPZ geometry is unchanged. At the USD boundary, faces whose winding disagrees with their vertex normals have their last two indices exchanged, matching the upstream static exporter. Vertex positions and triangle membership are unchanged; this avoids inward-facing stems in Blender. No remeshing, decimation, thickness, or simulated Blender growth is applied.
- Y-up meters are converted to Blender's coordinates. Saved-scene checks compare local/world vertex positions, face connectivity after winding conversion, UVs and vertex colors. `--validate-all` checks every frame in reverse order; the default checks milestones. Source/cache hashes are checked on reuse even for frames outside the milestone set.
- Normals are preserved in USD, but Blender's custom-normal encoding can differ around collapsed or degenerate leaf faces. Angular differences and affected corner counts are **reported separately**, not treated as vertex/shape errors. The shading is not a claim of pixel parity with EvoEngine. Blender material alpha/displacement can also change visible silhouettes if you choose different settings.
- This captures SorghumLS CPU snapshots and plant-owner transforms. It is not a general scene exporter: arbitrary objects, separate organ-child transform/visibility edits, arbitrary GPU deformation, animated engine cameras/lights, tangents, and renderer-specific visibility are not captured. Vulkan–OptiX parity is not established by these checks. Use the upstream static model-export workflow separately when appropriate.
- All samples are authored into one USD stage. The three-plant sequence is tested; field-scale memory/storage should be benchmarked before recording a large season.

## Tests and local evidence

```powershell
python -m unittest discover -s PythonBinding -p test_sorghum_growth_export.py -v
$env:BLENDER_EXECUTABLE = 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe'
python Scripts/blender/test_growth_pipeline.py -v
```

The Blender integration suite creates its own tiny atlas/geometry in a temporary directory; it needs no engine build or project assets. It covers changing topology, empty/disappearing/reappearing organs, reversed winding, all-frame comparison, edited scenes, invalid render ranges, stale source rejection, external texture changes, and fractional movie padding.

The local native validation uses this branch's Release binding at `out/build/growth-python/PythonBinding/Release/PyDigitalAgriculture.cp312-win_amd64.pyd`, built with Python 3.12, MSVC 14.51, CUDA 13.2, bundled OptiX 8.1 and Vulkan 1.4.341.1. Logs and outputs stay ignored under `out/`; binaries, caches, images and movies are not part of the source change. The initial 240-frame movie and repeat-run hashes remain under `out/exports/abc_growth_blender`. The post-integration handoff run is under `out/exports/abc_growth_handoff` with its own binding hash, manifest and validation report.

After integrating upstream through `9e3e978`, the Release target, 11 unit tests, and six Blender integration tests passed. All 240 native frames passed geometry comparisons (2,160 plant-part samples), and their original arrays matched the pre-refactor run exactly. Normal diagnostics found 690 corner samples above one degree out of 88,284,096 tested corners, with a maximum of 89.48 degrees around degenerate leaf geometry. Those are Blender shading differences; the geometry checks still require matching positions and triangle membership for every tested mesh.
