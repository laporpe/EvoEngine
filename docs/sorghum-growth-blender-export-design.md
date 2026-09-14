# Exporting EvoEngine sorghum growth to Blender

Investigated 2026-09-12 on `laporpe/EvoEngine`, branch `sorghum-growth-render-apis`, commit `abd4e20`.

Historical design note: source anchors and descriptions below refer to that initial commit. The current API and workflow are documented in [the colleague quick start](sorghum-growth-blender.md); the subsequent upstream static-export work is retained alongside the animation exporter.

## Recommendation

Export the actual EvoEngine geometry at each growth sample into an animated USD mesh cache (`.usdc`). Import that cache into a Blender presentation scene and render with Cycles. EvoEngine remains responsible for genotype, seeds, growth, weather/GDD, plant placement, camera poses, and lighting schedules. Blender supplies shading and rendering.

The smallest extension uses the **existing CPU geometry snapshots**, a new Python binding that exposes their arrays, and a Blender Python conversion script using `pxr`. The installed Blender 5.0.1 already includes both USD import and the `pxr` writer, verified locally. This avoids adding an OpenUSD C++ dependency to the engine. A disk handoff also keeps the engine's Python runtime separate from Blender's runtime.

This document records the original design and broader roadmap. The native snapshot binding, three-genotype sequence exporter, animated USD cache, and Blender rendering pipeline are now implemented. See [the implementation guide](sorghum-growth-blender.md) for commands, validation evidence, and the supported scope. Arbitrary scene export and animated camera/sun schedules remain future work.

## What already exists

| Source | Existing capability and implication |
| --- | --- |
| `PythonBinding/src/PyDigitalAgriculture.cpp:2586` | `GrowSorghumLsPlantsToGdd` initializes/replays; `AdvanceSorghumLsPlantsToGdd` advances an established simulation. |
| `EvoEngine_Packages/LSystem/src/LSystemLayer.cpp:205` | Generates snapshots across plants, publishes them, and updates transforms. Both growth bindings accept `update_render_geometry`. |
| `EvoEngine_Packages/LSystem/include/SorghumGeometrySnapshot.hpp:37` | Snapshot schema v2 contains culm, leaf, and panicle vertex/triangle arrays, internode instances, seed, target GDD, geometry version, and organ ranges. |
| `EvoEngine_Packages/LSystem/include/SorghumGeometrySnapshot.hpp:23` | Organ ranges include kind, axis, rank, node ID, and vertex/triangle offsets. These support metadata without splitting every organ into a Blender object. |
| `EvoEngine_Packages/LSystem/src/SorghumLS.cpp:557` | Incremental snapshots reuse exact geometry when no new growth step occurs. |
| `PythonBinding/src/PyDigitalAgriculture.cpp:3337` | Existing plant metadata exposes snapshot counts/versions, but does not expose the mesh arrays. |
| `research/sorghum-renders/abc-growth/render_abc_growth.py:886` | Already maps weather/GDD to frames and advances plants. Replace the image-capture sink with a geometry-export sink. |
| `PythonBinding/sorghum_2026_6x10_gdd_timelapse.py:631` | Existing 60-plant lifecycle orchestration is another integration point. |
| `EvoEngine_App/src/DigitalAgricultureApp.cpp:896` | Static Blender batch export writes one glTF/FBX snapshot through a prefab. |
| `Scripts/blender/prepare_lsystem_cycles_scene.py:680` | Imports one glTF, builds materials/presentation, and saves a `.blend`. Reuse presentation functions with an additional cache-import path. |

The older `Scripts/blender/create_sorghum_2026_panicle_timelapse.py` constructs Blender geometry and keys scale/color. Its report labels it as presentation-only. It is not a transfer of the native L-system's growth.

## Why an animated mesh cache

Plant topology changes: leaves appear and die, panicles emerge, and subdivision counts increase with leaf length. See `SorghumLS.cpp:818` (live-leaf aggregation), `:880` (panicle generation), and `SorghumLeafMesh.cpp:908` / `:1037` (length-dependent subdivision). A fixed-topology shape-key animation would require changing or resampling that geometry and proving vertex correspondence.

The current Assimp export path (`EvoEngine_SDK/src/Prefab.cpp:1147`) builds meshes, materials, and scene nodes once; it does not populate animation channels. Changing the output extension alone cannot add growth animation.

USD time samples can carry changing points and face topology. Blender reads animated USD and Alembic through Mesh Sequence Cache modifiers. Alembic is a viable geometry-cache alternative, but USD is the recommended first implementation because the installed Blender also provides a writer and USD can carry transforms, scene metadata, and material bindings.

Sources: [OpenUSD mesh topology attributes](https://openusd.org/dev/api/class_usd_geom_mesh.html), [Blender Mesh Sequence Cache](https://docs.blender.org/manual/id/4.2/modeling/modifiers/modify/mesh_sequence_cache.html). Local Blender verification below is the evidence for this machine's behavior.

## Concrete extension

### 1. Expose the current snapshots without changing simulation state

Add a binding such as `GetSorghumLsGeometrySnapshots()` in `PythonBinding/include/PyDigitalAgriculture.hpp` and `PythonBinding/src/PyDigitalAgriculture.cpp`. **This name is proposed and does not exist yet.** Return one record per plant:

- Persistent scene entity handle, readable plant name, genotype, descriptor path/hash, and fixed seed.
- Owner world transform; keep vertices in plant-local coordinates.
- Requested GDD, actual `growth_model.accumulated_gdd`, snapshot version, and mesh-quality settings.
- For each of `culm`, `leaves`, and `panicle`: positions, normals, UVs, RGBA vertex colors, triangle indices, material key, and organ ranges.

Use owned NumPy arrays or capsules retaining the immutable snapshot. Do not return pointers into buffers that the next growth step can release. Export the continuous culm mesh used by `PublishGeometrySnapshot`; exporting both that mesh and the legacy internode cylinders would duplicate stems.

Use a stable plant handle/name mapping, with organ identity derived from plant + kind + axis + rank/node. Generated render-child handles and sequential `material_N` labels are unsuitable for identity. Verify node identity across the particular reset/replay schedule before treating it as persistent across runs.

### 2. Record a deterministic frame sequence in the existing Python driver

Initialize once at the first sample; advance in increasing GDD order. Fix descriptor parameters and seeds for the sequence. For fitted descriptors, call the existing `SetSorghumLsFinalizeSnapshotMorphology(False)` before growth: the ABC driver already does this at line 667 because finalization would force endpoint morphology into early frames.

Start with `update_render_geometry=False` for export jobs, using the CPU snapshots directly. This suppresses mesh upload through the existing publishing path; it does not make the entire application independent of Vulkan or eliminate all publishing work. Verify the actual export job's initialization requirements.

Write frame arrays to bounded NPZ chunks, plus a versioned JSON manifest. Avoid Python lists for large geometry. Record:

- Frame index, output FPS, timestamp/time zone, requested GDD, actual evaluated GDD, weather/scenario identity, and seed assignment.
- Engine commit, source scene/descriptor hashes, mesh quality, and texture paths/hashes.
- Per-frame transforms, camera projection/pose and sun/environment settings when animated.
- Per-plant mesh counts, organ ranges, and hashes for validation/resume.

GDD is not playback time. USD sample time is the output frame number; a 24 FPS movie can map each frame to ten simulated minutes or a different explicit schedule. `LSystemGrowthModelBase.hpp:271` advances whole growth steps, so requested GDD can differ from accumulated GDD. Retain both. Unchanged geometry can reuse cached buffers while the timeline still records weather/camera changes. Snapshot `target_gdd` alone is insufficient for these repeated samples.

Resume must reproduce the simulation state before capturing a missing frame; skipping existing files must not change the growth evaluation schedule. Confirm reset-to-target and incremental equivalence before using arbitrary-frame replay as a shortcut.

### 3. Convert the frame chunks to animated USD in Blender's Python runtime

Add `Scripts/blender/build_sorghum_growth_cache.py`, using the verified `pxr.Usd` / `UsdGeom` APIs. Use stable paths such as:

```text
/Plants/plant_<stable_id>             # transform
    /Culm                           # time-sampled mesh
    /Leaves                         # time-sampled mesh
    /Panicle                        # time-sampled mesh
```

At each sample author `points`, `faceVertexCounts`, `faceVertexIndices`, normals, `primvars:st`, display color/opacity, and extents. Use `subdivisionScheme = none`. Keep material identity stable while sampling changing vertex colors/UVs. Define paths for late organs from the start; write explicit empty mesh samples before birth and after disappearance. Import with `import_visible_only=False` so initially empty/invisible organs remain available.

Declare meters and Y-up consistently with EvoEngine. Blender's USD import performs the coordinate conversion; do not additionally apply the glTF path's conversion. Test rotations, nonuniform scale, and reflected transforms beyond the simple translation/height case already probed.

Build caches in bounded frame chunks for large fields, composing/referencing them through a stage or another verified USD sequence mechanism. Do not assume calling `Save()` frees an in-memory USD stage's samples. First benchmark 3 plants/24 frames, then 60 plants before committing to a season-long cache layout.

### 4. Reuse the presentation pipeline and transfer scene orchestration

Import the static ground/PARBAR/context once, then use cached meshes for the plant collection. Initially a static glTF can provide the established context and materials, with its static plant geometry removed/replaced by stable identity. Add a non-mutating scene snapshot route for automation.

Do not loop the current static CLI export in a live simulation. `DigitalAgricultureApp.cpp:369` adds baked particle meshes and `:880` creates an export parent and reparents scene roots, without restoration in those functions. Its preserve-state mode also regenerates plants; it does not serialize the exact existing incremental snapshot.

Refactor `prepare_lsystem_cycles_scene.py` so presentation setup can accept USD meshes and semantic material keys. Explicitly connect animated vertex colors to leaf/panicle shaders. Preserve atlas UVs, material textures, roughness, thickness and translucency settings. Static texture assets should be copied once.

The existing preparation code authors a fixed camera at line 589 and Blender world at line 629. Add manifest-driven camera transforms/projection and sun keys so EvoEngine can orchestrate the shot. A Nishita sky is not guaranteed to render identically across engines: transfer the schedule/parameters and calibrate the Blender shader conversion, or export an environment map when a closer environment match is required.

Save a `.blend` referencing the cache with relocatable paths. Render each sampled frame with Blender's normal animation renderer. Initially disable deformation motion blur and avoid interpolating between samples with changed vertex identity. Smooth motion and subframe shutter samples need a separate correspondence/sampling validation.

## Verification completed

Ran a synthetic probe using the installed executable:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.0/blender.exe' --background --factory-startup --python-exit-code 1 --python out/growth_export_probe/probe_usd.py
```

Result: exit code 0, Blender 5.0.1, `GROWTH_USD_PROBE_PASSED`. The probe wrote two meshes over four USD samples and checked:

- Vertex/triangle counts change correctly, including empty geometry and a mesh born after frame 1.
- Automatic Mesh Sequence Cache modifiers are present.
- Sampled UV values and vertex colors survive import and update with time.
- Y-up geometry becomes the expected Blender world height in meters.
- Scrubbing backward restores earlier geometry.
- Saving and reopening the `.blend` retains cache playback.

Local artifacts are in `out/growth_export_probe/`: `probe_usd.py`, `varying_topology.usdc`, `varying_topology.blend`, and `report.json`. This was a format/dependency test, not an EvoEngine plant export or a rendered plant video. Visibility flags alone were not validated as an animation mechanism; empty geometry provided the verified disappearance behavior.

## Implementation acceptance checks

1. Export one native plant at early growth, leaf emergence, panicle emergence, and maturity. Compare counts, bounds, normals, UVs, colors, organ ranges, and transforms to the exact engine snapshots.
2. Run the three-genotype weather schedule twice with the same seeds; compare frame hashes and actual GDD. Check paused growth and backward/random playback in Blender.
3. Render matching views in Blender with the existing leaf atlas and presentation materials; verify no duplicate stems, invisible late panicles, static replacement plants, or unexpected color resets.
4. Verify camera/sun schedule and static context placement independently of shading parity.
5. Scale to the 60-plant field, measure cache bytes/frame, export time, peak memory, and frame-load time; test relocation and resume.
6. Confirm the existing static export path still works and neither export path modifies source scene/descriptor files.

At initial investigation the new clone had no initialized submodules or engine build. Implementation initialized the pinned build dependencies and DigitalAgricultureProject at `340e6ca0087f182187242ce7567f5cb725b57cb7`, then built this checkout's `PyDigitalAgriculture` Release target with CUDA/OptiX enabled. The native validation uses that new binary, committed A/B/C descriptors, and the initialized leaf atlas. The broader acceptance checks above include future field-scale and full-scene work; they are not claims that those features have been completed.
