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

This sorghum 261 branch uses `Resources/DigitalAgricultureProject` as a Git submodule backed by `Penanito/EvoEngine_SorghumProject`, with large assets stored in Git LFS. Install Git LFS before cloning when possible, then run:

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
python PythonBinding\sorghum_migrate_fidelity_v4_descriptors.py
python PythonBinding\sorghum_calibrate_morphology_allocation.py --sample-count 1000 --apply
python PythonBinding\sorghum_calibrate_morphology_allocation.py --sample-count 1000 --validate-only
python PythonBinding\sorghum_validate_2026_morphology.py --sample-count 1000
python PythonBinding\sorghum_generate_calibrated_field_scenes.py
```

These commands use the Release runtime by default. Single-process descriptor calibration avoids concurrent CUDA and
asset-metadata access on Windows. The 2021 main-culm leaf-count and complete-plant height distributions are mandatory
fit targets; the unknown-genotype 2026 measurements are reported as morphology priors rather than cultivar truth.
The ten generated date/cultivar descriptors are measured-date snapshots finalized at their stage-specific GDD, so
their saved geometry matches those calibration targets. The shared L-system remains time-resolved for future
dynamic-growth work when snapshot finalization is disabled.

The promoted descriptors use crown-attached primary tillers with distichous leaf-axil origins and restrained same-side
crown splay, absolute rank-specific blade widths,
descriptor-owned blade/sheath thickness, stem-fitted overlapping sheaths, a reduced static gravity response driven by
leaf thermal age and along-blade stiffness, deterministic plant-coherent wind deflection and twist, multi-scale
centerline and margin waviness, the promoted 3x3 leaf atlas, constrained rank/age color and damage variation,
elliptical sheaths, main-culm lean, and a continuous textured culm mesh. The first three stages use 50% wider blades
without changing their authored physical thicknesses.

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

Run replicated PARBAR illumination estimates for all five current 4x10 scenes with:

```bat
python PythonBinding\sorghum_4x10_parbar_sensor_illumination_handoff.py --replicates 10000 --probes-per-panel 100 --samples 64 --bounces 4 --output-dir out\handoff\sorghum_4x10_parbar_10000 --checkpoint-dir out\handoff\.sorghum_4x10_parbar_10000_checkpoints
python PythonBinding\sorghum_render_4x10_parbar_sensor_illumination_pngs.py --handoff-dir out\handoff\sorghum_4x10_parbar_10000 --expected-replicates 10000
```

The handoff regenerates 40 uniquely seeded rooted plants per scene and replicate, writes online mean, sample standard
deviation, standard error, and 95% interval columns for every PARBAR probe, and stores driver, runtime, and full
project-asset-tree hashes in
`run_manifest.json`. Add `--resume` to the first command with the same arguments after an interruption. Values remain
relative simulated light estimates rather than calibrated physical PAR units. The default ten-replicate engine batch
restarts EvoEngine at durable checkpoint boundaries to bound long-campaign memory use; tune it with
`--engine-batch-size`. Campaign and per-date worker locks reject concurrent use of the same checkpoint directory, and
the parent terminates its active worker when an interruption can be handled.

`PythonBinding/sorghum_4x10_scene.py` is the small importable boundary for custom illumination code. Call
`query_4x10_scene(...)` to resolve a published date, `prepare_4x10_scene(...)` once after importing EvoEngine, and
`grow_4x10_scene(...)` for each deterministic morphology seed. The returned scene declares EvoEngine Y-up coordinates;
`plant_organ_ids(...)` provides stable plant, main-culm, tiller, and leaf IDs. Probe creation and all illumination
settings remain caller-owned, so alternate probe logic can sample the published PARBAR geometry without changing the
scene API. The existing CSV command above uses this API and remains the supported averaged 10,000-replicate runner.

```python
from pathlib import Path
from sorghum_4x10_scene import query_4x10_scene, prepare_4x10_scene, grow_4x10_scene

project = Path("Resources/DigitalAgricultureProject")
scene = query_4x10_scene(
    project / "Assets/GeneratedAssets/Reports/field_manifest.csv",
    Path("GeneratedAssets/Descriptors"),
    "2021-08-30",
)
prepare_4x10_scene(evo, project / "test_lsystem_sorghum.eveproj", packages, scene, 2_000_000, 2 / 3, 2, 30000)
probes = create_my_parbar_probes(evo, scene)
grow_4x10_scene(evo, scene, geometry_seed=2_001_000, max_wait_frames=30000)
```

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
