# EvoEngine

![Windows Release](https://github.com/edisonlee0212/EvoEngine/actions/workflows/Windows-RelWithDebInfo.yml/badge.svg)
![Windows Debug](https://github.com/edisonlee0212/EvoEngine/actions/workflows/Windows-Debug.yml/badge.svg)
![Linux Release](https://github.com/edisonlee0212/EvoEngine/actions/workflows/Linux-RelWithDebInfo.yml/badge.svg)
![Linux Debug](https://github.com/edisonlee0212/EvoEngine/actions/workflows/Linux-Debug.yml/badge.svg)

EvoEngine is a C++17 research framework for interactive simulation, digital forestry, digital agriculture, synthetic dataset generation, and Vulkan rendering. It includes a reusable SDK, an editor, a project/asset system, Python automation hooks, build-time Services, and runtime packages that can be loaded by the editor or apps.

Windows is the primary development platform. Linux builds are supported for the core stack, while some Services and packages are Windows-only or require optional SDKs.

![EvoEngine rendering demo](Resources/GitHub/RenderingDemo.png)

## Quick Start

Clone with submodules:

```bash
git clone --recursive https://github.com/edisonlee0212/EvoEngine.git
cd EvoEngine
```

The sorghum workflow uses `Resources/DigitalAgricultureProject` as a Git submodule backed by
`Penanito/EvoEngine_SorghumProject`, with large assets stored in Git LFS. Install Git LFS before cloning when possible,
then run:

```bash
git submodule foreach --recursive git lfs pull
```

Run the same command if any resource assets appear as small LFS pointer files after checkout.

If the repository was cloned without submodules:

```bash
git submodule update --init --recursive
```

On Windows, generate the Visual Studio build tree and install runnable apps:

```bat
python Scripts\build_project.py
python Scripts\install_apps.py
```

Installed app binaries are written to:

```text
out/install/vs2026-x64/bin/
```

Start with `EvoEngineLauncher.exe` to create or open a project. Use `EvoEngineEditor.exe --project <path-to-project.eveproj>` when launching the editor directly.

For detailed setup, platform requirements, Linux commands, VSCode notes, and install layout, see [docs/building.md](docs/building.md).

## What Is In The Framework?

| Area | Purpose |
| --- | --- |
| SDK | Application lifecycle, layer composition, ECS, scene management, renderer, editor UI, assets, serialization, jobs, input, and utilities. |
| Editor | ImGui-based project editor with scene, entity, asset, console, inspector, runtime package, and playback workflows. |
| Renderer | Vulkan renderer with deferred/forward paths, PBR materials, render textures, editor cameras, shadows, environment lighting, and optional advanced GPU features. |
| Projects and assets | `.eveproj` projects, handle-based assets, file/folder metadata, YAML serialization, staged asset loading, and editor inspectors. |
| Services | Build-time domain modules under `EvoEngine_Services`. |
| Runtime packages | Shared-library modules under `EvoEngine_Packages` that can be loaded, unloaded, rebuilt, and reloaded independently from the app. |
| Python bindings | pybind11 modules and scripts for automation workflows. |

## Documentation

| Topic | Documentation |
| --- | --- |
| Getting started | [docs/getting-started.md](docs/getting-started.md) |
| Build and install | [docs/building.md](docs/building.md) |
| Testing | [docs/testing.md](docs/testing.md) |
| SDK architecture | [docs/architecture.md](docs/architecture.md) |
| Projects, assets, and serialization | [docs/projects-assets-serialization.md](docs/projects-assets-serialization.md) |
| Runtime packages | [docs/runtime-packages.md](docs/runtime-packages.md) |
| Extending EvoEngine | [docs/extending-evoengine.md](docs/extending-evoengine.md) |
| Python bindings | [docs/python-bindings.md](docs/python-bindings.md) |
| Runtime package index | [EvoEngine_Packages/README.md](EvoEngine_Packages/README.md) |
| Service index | [EvoEngine_Services/README.md](EvoEngine_Services/README.md) |

## Repository Map

| Path | Purpose |
| --- | --- |
| `EvoEngine_SDK` | Core runtime, ECS, editor, renderer, assets, serialization, jobs, input, and utilities. |
| `EvoEngine_App` | Executable apps, shared demo setup, app entry points, and app resources/configuration. |
| `EvoEngine_Packages` | Runtime package shared-library modules loaded from `Packages` folders. |
| `EvoEngine_Services` | Build-time domain modules linked into apps, packages, or Python bindings. |
| `EvoEngine_Tests` | C++ tests, render tests, launcher smoke tests, and test helper scripts. |
| `PythonBinding` | pybind11 modules and Python automation scripts. |
| `Resources` | Demo projects, screenshots, textures, and sample assets. |
| `Scripts` | Build, install, test, and formatting helpers. |
| `Extern` | Vendored third-party libraries and submodules. |
| `cmake` | CMake helper modules. |

## Demo Gallery

| Rendering | Ray Tracing |
| --- | --- |
| ![Rendering demo](Resources/GitHub/RenderingDemo.png) | ![Ray tracing demo](Resources/GitHub/RayTracingDemo.png) |

| Planet Terrain | Star Clusters |
| --- | --- |
| ![Planet terrain demo](Resources/GitHub/PlanetsDemo.png) | ![Star cluster demo](Resources/GitHub/StarClusterDemo.png) |

| Tree Framework | Tree Fracture |
| --- | --- |
| ![Tree framework demo](Resources/GitHub/TreeFrameworkDemo.png) | ![Tree fracture](Resources/GitHub/TreeFracture.png) |

| Strand Visualization | Illumination Estimation |
| --- | --- |
| ![Strand visualization](Resources/GitHub/StrandVisualization.png) | ![Illumination estimation demo](Resources/GitHub/IlluminationEstimationDemo.png) |

| Sorghum Model | Sorghum Point Cloud |
| --- | --- |
| ![Sorghum model](Resources/GitHub/SorghumModel.png) | ![Sorghum point cloud](Resources/GitHub/SorghumPointCloud.png) |

| Sorghum Environment Lighting |
| --- |
| ![Sorghum environment lighting](Resources/GitHub/SorghumEnvLighting.png) |

## Sorghum 4x10 RT Realism Review

Install the image/PDF dependencies once, then render the five calibrated 4x10 scenes into a local review package:

```bat
python -m pip install -r PythonBinding\requirements-mobile-review.txt
python PythonBinding\sorghum_render_4x10_mobile_review.py --width 3840 --height 2160 --samples 128 --bounces 4
```

The package is written to `out/realism_review/sorghum_4x10/Iteration_01_RT_PhysicalSun`. Add `--publish-drive` to
publish the verified iteration under
`G:\My Drive\Sorghum\4x10_Scene_Review_Latest\Iteration_01_RT_PhysicalSun` without replacing earlier reviews.
It contains 45 lossless Scene (RT) captures, 45 labeled images, five stage contact sheets, and a PDF review book.

To regenerate all calibrated scenes and publish the review in one operation:

```bat
python PythonBinding\sorghum_generate_calibrated_field_scenes.py --skip-10x10 --publish-mobile-review
```

Recalibrate all ten descriptors at the paper-validation sample sizes before scene generation with:

```bat
python PythonBinding\sorghum_lsystem_calibrate_date_cultivar_descriptors.py --iteration-sample-count 1000 --validation-sample-count 10000 --max-iterations 6 --single-process
python PythonBinding\sorghum_generate_calibrated_field_scenes.py
```

These commands use the Release runtime by default. Single-process descriptor calibration avoids concurrent CUDA and
asset-metadata access on Windows. The 2021 main-culm leaf-count and complete-plant height distributions are mandatory
fit targets.
The ten generated date/cultivar descriptors are measured-date snapshots finalized at their stage-specific GDD. Use
the generated calibration and scene-validation reports as the authority for current measurement agreement. The
shared L-system remains time-resolved for future dynamic-growth work when snapshot finalization is disabled.

The promoted descriptors use crown-attached primary tillers with distichous leaf-axil origins and restrained same-side
crown splay, absolute rank-specific blade widths,
descriptor-owned blade/sheath thickness, stem-fitted overlapping sheaths, a reduced static gravity response driven by
leaf thermal age and along-blade stiffness, deterministic plant-coherent wind deflection and twist, multi-scale
centerline and margin waviness, the promoted 3x3 leaf atlas, constrained rank/age color and damage variation,
elliptical sheaths, main-culm lean, and a continuous textured culm mesh. Growth stages 2 through 5 use 25% wider
maximum blades without changing their authored physical thicknesses. The distal blade droop is increased by 50%,
and independent leaf-roll and tiller-azimuth variation are doubled. BTX
uses the more upright `26.25 +/- 3.75` degree tiller insertion distribution; Pawaga retains `35 +/- 5` degrees.

The manual soil mesh carries baked geometric relief derived from its PBR height map, so the EvoEngine RT review uses
real geometry rather than a raster-only displacement approximation. Rebuild that mesh after replacing the manual PBR
set with:

```bat
python PythonBinding\sorghum_bake_soil_relief.py
```

The scene generator conforms each plant root to the displaced ground surface.
After the five-stage review is rendered, append and publish the mature 10x10 views with:

```bat
python PythonBinding\sorghum_render_10x10_fidelity_review.py --width 3840 --height 2160 --samples 128 --bounces 4 --publish-drive
```

Each scene is regrown with deterministic seed `2000000`. All nine views per stage use the OptiX skydome with a
physical `0.526` degree sun, 128 samples, and four bounces. Temporary review cameras never save changes back to scene
assets. Measurement dates appear in labels and manifests while generated filenames use `GrowthStage01..05`.

Run the supported five-date 4x10 PARBAR campaign with:

```bat
python PythonBinding\sorghum_4x10_parbar_sensor_illumination_handoff.py --replicates 10000 --probes-per-panel 100 --samples 64 --bounces 4 --output-dir out\handoff\sorghum_4x10_parbar_10000
```

The command generates a different deterministic 40-plant realization for every replicate, reports per-probe mean,
sample standard deviation, standard error, and 95% interval, and checkpoints after each batch. Add `--resume` with the
same arguments after an interruption. The values are relative EvoEngine illumination estimates; physical conversion
and interpretation belong to the illumination analysis.

For the optional 25-second paper video, run 100 realizations per date with `--video`:

```bat
python PythonBinding\sorghum_4x10_parbar_sensor_illumination_handoff.py --replicates 100 --probes-per-panel 100 --samples 64 --bounces 4 --video --output-dir out\handoff\sorghum_4x10_parbar_video_100
```

Video output is limited to at most 300 realizations, requires Pillow plus `ffmpeg` and `ffprobe`, and does not alter the
scientific CSV calculation. The CSV-only 10,000-replicate run remains the production path.

`PythonBinding/sorghum_4x10_scene.py` is the small importable boundary for custom analysis. Resolve one date with
`query_4x10_scene(...)`, prepare its in-process scene once, then call `grow_4x10_scene(...)` for each morphology seed.
The scene uses EvoEngine Y-up coordinates, and `plant_organ_ids(...)` returns plant, main-culm, tiller, and leaf IDs.
Probe construction and all illumination settings remain caller-owned.

Run `python PythonBinding\sorghum_validate_gpu_field_geometry.py` after engine changes. It compares the destructive
CPU reference with persistent and replayed snapshots, requires a different seed to diverge, compares fixed-seed
PARBAR outputs, and verifies that OptiX GAS and IAS updates occurred.

```python
from pathlib import Path
from sorghum_4x10_scene import query_4x10_scene, prepare_4x10_scene, grow_4x10_scene

# After configuring the build paths and importing PyDigitalAgriculture as evo:
project = Path("Resources/DigitalAgricultureProject")
packages = Path("out/build/vs2026-x64/EvoEngine_App/RelWithDebInfo/Packages")
scene = query_4x10_scene(
    project / "Assets/GeneratedAssets/Reports/field_manifest.csv",
    Path("GeneratedAssets/Descriptors"),
    "2021-08-30",
)
prepare_4x10_scene(evo, project / "test_lsystem_sorghum.eveproj", packages, scene, 2_000_000, 2 / 3, 2, 30000)
probes = create_my_parbar_probes(evo, scene)
grow_4x10_scene(evo, scene, geometry_seed=2_001_000, max_wait_frames=30000)
```

The full CSV command above already uses this API; the sketch is only for a consumer supplying custom probe logic.

### Frozen 4x10 scenes

`PythonBinding/sorghum_4x10_saved_scene.py` provides the small saved-scene boundary. Freezing uses the descriptors
already referenced by the selected published growth-stage scene, assigns a deterministic seed to each plant, grows
all plants to the requested **evaluation GDD**, moves the middle PARBAR panels, and saves a new `.evescene`. It does
not edit or replace the descriptor asset, including the descriptor's published target/maturity GDD distribution.

The scene serializes each plant's descriptor reference, seed, evaluation GDD, and leaf mesh settings. A neighboring
`.provenance.json` records all 40 identities and hashes the scene and its fixed published descriptor assets. The
L-system package automatically reconstructs runtime-only plant geometry when the scene is attached after an editor or
engine restart. The editor's ordinary Save Scene command uses this same contract. Generic scene, mesh, material,
texture, and soil serialization are unchanged. Identical geometry is expected with the same EvoEngine build and
assets; cross-build bitwise identity is intentionally not promised.

Run from `PythonBinding`, or add that directory to `PYTHONPATH` when importing from the repository root. The current
EvoEngine SDK does not reliably survive a second shutdown after restarting in one interpreter, so each function
intentionally owns one engine session and must be called from a fresh Python process. Save first; analyze in a later
invocation.

```python
from pathlib import Path
from sorghum_4x10_saved_scene import save_4x10_scene_at_growth

project = Path("Resources/DigitalAgricultureProject/test_lsystem_sorghum.eveproj")
snapshot = save_4x10_scene_at_growth(
    project=project,
    source_scene=Path("GeneratedAssets/Scenes/Sorghum_4x10_GrowthStage03.evescene"),
    scene=Path("GeneratedAssets/Scenes/MyFrozenField.evescene"),
    evaluation_gdd=725.0,
    geometry_seed=2_000_000,
)
```

Then, from a new Python process:

```python
from pathlib import Path
from sorghum_4x10_saved_scene import analyze_saved_4x10_scene

project = Path("Resources/DigitalAgricultureProject/test_lsystem_sorghum.eveproj")
result = analyze_saved_4x10_scene(
    project=project,
    scene=Path("GeneratedAssets/Scenes/MyFrozenField.evescene"),
    output_dir=Path("out/scene_analysis"),
    probes_per_panel=100,
    illumination_samples=64,
    illumination_bounces=4,
    render_samples=64,
    render_bounces=4,
)
```

Analysis loads the saved recipe and asks the L-system package to restore its runtime-only geometry without Vulkan
render uploads. The Python binding contains no plant reconstruction rules and never reassigns seeds or evaluation GDD
or samples descriptor target GDD. It writes `scene.png`, raw single-scene `parbar_probes.csv`, `plants.csv`,
`organs.csv`, and `manifest.json`. Illumination values remain EvoEngine-relative; PPFD conversion and physical
interpretation remain illumination-consumer responsibilities.

## Related Publications

EvoEngine supports research workflows used in digital forestry and digital agriculture. Related work includes:

- [Learning to Reconstruct Botanical Trees from Single Images, SIGGRAPH Asia 2021](https://storage.googleapis.com/pirk.io/projects/single_tree_reconstruction/index.html)
- [Rhizomorph: The Coordinated Function of Shoots and Roots, SIGGRAPH 2023](https://storage.googleapis.com/pirk.io/projects/rhizomorph/index.html)
- [DeepTree: Modeling Trees with Situated Latents, TVCG 2023](https://storage.googleapis.com/pirk.io/projects/deep_tree/index.html)
- [Latent L-systems: Transformer-based Tree Generator, SIGGRAPH 2024](https://dl.acm.org/doi/pdf/10.1145/3627101)
- [Tree-D Fusion: Simulation-Ready Tree Dataset from Single Images with Diffusion Priors, ECCV 2024](https://link.springer.com/chapter/10.1007/978-3-031-72940-9_25)
- [Interactive Invigoration: Volumetric Modeling of Trees with Strands, SIGGRAPH 2024](https://storage.googleapis.com/pirk.io/projects/invigoration/index.html)
- [TreeStructor: Forest Reconstruction With Neural Ranking, TGRS 2025](https://lewkesy.github.io/treestructor/)
- [Stressful Tree Modeling: Breaking Branches with Strands, SIGGRAPH 2025](https://dl.acm.org/doi/10.1145/3721238.3730745)
- [3D reconstruction identifies loci linked to variation in angle of individual sorghum leaves, PeerJ](https://peerj.com/articles/12628/)
- [Sorghum segmentation and leaf counting using in silico trained deep neural model, The Plant Phenome Journal](https://acsess.onlinelibrary.wiley.com/doi/pdf/10.1002/ppj2.70002)
- [PlantSegNet: 3D point cloud instance segmentation of nearby plant organs with identical semantics, Computers and Electronics in Agriculture](https://www.sciencedirect.com/science/article/abs/pii/S0168169924003132)
- [Woodstock](https://jango6324.github.io/woodstock/)

## License

EvoEngine is source-available for inspection, learning, and direct contribution only. It is not open source. You may not copy, reuse, redistribute, publish, sublicense, incorporate, or commercially use EvoEngine code, assets, documentation, or other repository content without prior written permission.

Contributions are welcome. You may fork, clone, build, and modify EvoEngine solely to prepare contributions directly back to this repository. See [LICENSE](LICENSE) for the full terms.
