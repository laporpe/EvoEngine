

## 1. Install prerequisites

Install:

- Git
- CMake
- Visual Studio 2026 with **Desktop development with C++**
- [Vulkan SDK](https://vulkan.lunarg.com/)
- Miniconda or Anaconda
- An NVIDIA GPU with a recent driver for GPU TLS scanning

## 2. Download EvoEngine

The tree scene generator is currently developed on branch
`codex/sorghum-gpu-field-geometry`.

```powershell
git clone --recursive https://github.com/edisonlee0212/EvoEngine.git
cd EvoEngine
git switch codex/sorghum-gpu-field-geometry
git branch --show-current
git submodule update --init --recursive
```

Run the submodule update after switching branches even when `--recursive` was
used during cloning, because the selected branch may reference different
submodule commits.

## 3. Create the Python environment

The Python bindings must be built and run with the same Python version. The
current setup uses Python 3.12.

```powershell
conda create -n evoengine python=3.12
conda activate evoengine
python -m pip install numpy open3d matplotlib jupyter
```

## 4. Configure and build

Run these commands from the EvoEngine repository root:

```powershell
$python = (Get-Command python).Source
python Scripts/build_project.py --clean `
  --cmake-arg="-DPython3_EXECUTABLE=$python" `
  --cmake-arg="-DPython_EXECUTABLE=$python" `
  --cmake-arg="-DEVOENGINE_ENABLE_EcoSysLab_PACKAGE=ON" `
  --cmake-arg="-DEVOENGINE_ENABLE_BillboardClouds_PACKAGE=ON" `
  --cmake-arg="-DPythonBinding-PyEcoSysLab=ON"

cmake --build out/build/vs2026-x64 --config RelWithDebInfo `
  --target PyEcoSysLab EcoSysLabPackage BillboardCloudsPackage
```

Confirm that a Python 3.12 module was produced:

```powershell
Get-ChildItem out/build/vs2026-x64/PythonBinding/RelWithDebInfo/PyEcoSysLab*.pyd
```

Its filename should contain `cp312`.

## 5. Generate scenes

Generate one scene of each type as a quick test:

```powershell
python PythonBinding/tree_generation/generate_scene_batch.py --count 1 --timing
```

Generate five scenes of each type:

```powershell
python PythonBinding/tree_generation/generate_scene_batch.py --count 5 --timing
```

Generate only selected scene types:

```powershell
python PythonBinding/tree_generation/generate_scene_batch.py `
  --count 5 --scenes alley dense_park --timing
```

Use `--seed 41827` to reproduce a batch. Use `--resume` with the same seed and
settings to skip scenes that already finished successfully.

Each scene includes randomized species, ages, positions, bushes, buildings,
large spruces, one approximately 10 m conifer, and close double-tree pairs.
TLS station positions are randomized inside the scene. Run
`python PythonBinding/tree_generation/generate_scene_batch.py --help` for the
plant-count and TLS-density parameters.

## 6. Find the output

All generated data is written under `out`:

```text
out/AlleyTreeScene/AlleyTreeScene_001/
out/DenseParkScene/DenseParkScene_001/
out/SparseParkScene/SparseParkScene_001/
```

Important files in each scene folder:

- `<SceneName>.obj`: complete scene geometry
- `<SceneName>_trees.obj`: combined plant geometry
- `individual_plants/`: one OBJ per tree or bush
- `<SceneName>_view.png`: rendered scene preview
- `<SceneName>_tls_scan_XX.ply`: one occluded TLS point cloud per station
- `<SceneName>_geometry_sampled.ply`: dense geometry sampling without occlusion
- `<SceneName>_object_ids.json`: instance IDs and object metadata
- `<SceneName>_generation.json`: seed, placements, TLS stations, and settings

Tree and bush instance IDs are in the range `1-99`. Ground and building IDs
start at `1000`. The PLY property `instance_index` stores these IDs.

## 7. View point clouds

Open:

```powershell
jupyter notebook PythonBinding/tree_generation/visualize_point_cloud.ipynb
```

In the first notebook cell, set `scene_type`, `scene_id`, and choose either a
TLS scan or `geometry_sampled`. The notebook colors points by instance ID and
can open the full point cloud in the interactive Open3D viewer.

## Common problems

- `No module named PyEcoSysLab`: activate the `evoengine` environment and
  rebuild after confirming the CMake cache uses its Python 3.12 executable.
- `BillboardCloudsPackage.dll` error 127: rebuild both `EcoSysLabPackage` and
  `BillboardCloudsPackage`; do not manually copy a DLL from another build
  configuration.
- Stop a long batch with `Ctrl+C`. Restart it with the same `--seed`, settings,
  and `--resume` to retain completed scenes.
