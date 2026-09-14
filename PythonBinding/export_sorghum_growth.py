"""Export native A/B/C growth snapshots for build_sorghum_growth_cache.py."""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from sorghum_growth_export import GrowthGeometryExporter, sha256

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "out/build/growth-python")
    parser.add_argument("--config", default="Release")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "out/exports/abc_growth_blender"
    )
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--start-gdd", type=float, default=0)
    parser.add_argument("--end-gdd", type=float, default=2320.35)
    parser.add_argument("--seed", type=int, default=202609020)
    parser.add_argument("--spacing", type=float, default=2.2)
    parser.add_argument("--vertical-step", type=float, default=0.01)
    parser.add_argument("--horizontal-steps", type=int, default=6)
    args = parser.parse_args()
    if (
        not all(
            math.isfinite(v)
            for v in (args.start_gdd, args.end_gdd, args.spacing, args.vertical_step)
        )
        or args.frames < 2
        or args.fps < 1
        or not 0 <= args.start_gdd < args.end_gdd
    ):
        parser.error(
            "Need at least two frames, positive FPS, and increasing nonnegative GDD"
        )
    if args.vertical_step < 0.001 or args.horizontal_steps < 2 or args.spacing <= 0:
        parser.error(
            "Vertical step must be at least 0.001 m, horizontal steps at least 2, and spacing positive"
        )
    output, build = args.output.resolve(), args.build.resolve()
    exporter = GrowthGeometryExporter(output, args.fps)
    project = output / "project"
    project.mkdir(exist_ok=True)
    specification = importlib.util.spec_from_file_location(
        "abc_growth", ROOT / "research/sorghum-renders/abc-growth/render_abc_growth.py"
    )
    abc = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(abc)
    abc.PROJECT_ROOT = project
    abc.SOURCE_DESCRIPTORS = ROOT / "Resources/HandoffTest/Assets/Descriptors"
    descriptors = abc.stage_descriptors(7, 100, args.end_gdd)
    paths = [
        build / "PythonBinding" / args.config,
        build / "EvoEngine_App" / args.config,
        build / "EvoEngine_App" / args.config / "Packages",
        build / "EvoEngine_SDK" / args.config,
        build / "EvoEngine_Services/CudaModule" / args.config,
    ]
    _dll_handles = (
        [os.add_dll_directory(str(p)) for p in paths if p.is_dir()]
        if os.name == "nt"
        else []
    )
    sys.path.insert(0, str(paths[0]))
    os.chdir(paths[0])
    import PyDigitalAgriculture as evo

    exporter.manifest["metadata"] = {
        "engine_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "engine_binding_sha256": sha256(evo.__file__),
        "engine_binding": str(evo.__file__),
        "seed_base": args.seed,
        "growth": {
            "week": 7,
            "plastochron_gdd": 100,
            "maturity_gdd": 800,
            "finalize_snapshot_morphology": False,
            "schedule": "linear_gdd",
        },
        "mesh_quality": {
            "vertical_step_m": args.vertical_step,
            "horizontal_steps": args.horizontal_steps,
            "bottom_face": False,
            "leaf_sheath": True,
        },
        "descriptors": {
            key: {
                "path": f"project/Assets/{value}",
                "sha256": sha256(project / "Assets" / value),
            }
            for key, value in descriptors.items()
        },
    }
    if not evo.RunLSystemSorghumProject(
        str(project / "growth.eveproj"), str(paths[2]), "", False
    ):
        raise RuntimeError("Engine initialization failed")
    try:
        if not evo.WaitForProjectIdle(30000):
            raise RuntimeError("Project did not become idle")
        labels = ["GenotypeA", "GenotypeB", "GenotypeC"]
        if (
            evo.ConfigureSorghumLsPlantingGrid(
                labels, 1, args.spacing, args.spacing, 0.0, 0.0
            )
            != 3
        ):
            raise RuntimeError("Expected three planting markers")
        if evo.InstantiateSorghumLsPlantsFromPlantingMarkers() != 3:
            raise RuntimeError("Expected three instantiated plants")
        if evo.SetSorghumLsGenotypeDescriptors(descriptors, False, args.seed) != 3:
            raise RuntimeError("Could not configure all three genotypes")
        if (
            evo.ConfigureSorghumLsLeafMeshQuality(
                args.vertical_step, args.horizontal_steps, False, True, False
            )
            != 3
        ):
            raise RuntimeError("Could not configure all three plant meshes")
        if evo.SetSorghumLsFinalizeSnapshotMorphology(False) != 3:
            raise RuntimeError("Could not disable snapshot finalization")
        for index, gdd in enumerate(
            np.linspace(args.start_gdd, args.end_gdd, args.frames), start=1
        ):
            grow = (
                evo.GrowSorghumLsPlantsToGdd
                if index == 1
                else evo.AdvanceSorghumLsPlantsToGdd
            )
            if grow(float(gdd), args.seed, False) != 3:
                raise RuntimeError(f"Expected three plants at frame {index}")
            exporter.capture(evo, float(gdd))
            if index == 1 or index % 20 == 0 or index == args.frames:
                print(f"EXPORTED {index}/{args.frames} GDD={gdd:.2f}", flush=True)
        print(f"GROWTH_EXPORT_PASSED {exporter.finish()}", flush=True)
    finally:
        evo.Terminate()


if __name__ == "__main__":
    main()
