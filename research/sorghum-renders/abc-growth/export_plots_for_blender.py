"""Grow the three genotype plots and export them as model files for Blender.

The video renders run a deliberately cheap leaf mesh, because at 1080p the extra
subdivisions never survive the pixel grid. Geometry destined for Blender is
shaded and re-lit there, so it is worth paying for the finer mesh here.

    python export_plots_for_blender.py --gdd 1858 --columns 5 --format fbx obj

Use .fbx for Blender - it carries materials and the per-plant hierarchy.
.obj works too but is ASCII, so the same stand is a much larger file.
glTF is refused by the engine: Assimp's glTF2 writer faults on these scenes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_abc_growth import (  # noqa: E402
    BUILD, CONFIG, GENOTYPES, PROJECT, TEMPLATE_SCENE, PLASTOCHRON_GDD,
    configure_engine_imports, field_weeks, stage_descriptors,
)

SEED = 202_609_020


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gdd", type=float, default=1858.0,
                        help="thermal age to grow to before exporting; 1858 is the close "
                             "of the August window the videos cover")
    parser.add_argument("--week", type=int, choices=(6, 7), default=7)
    parser.add_argument("--columns", type=int, default=5,
                        help="plants per genotype row")
    parser.add_argument("--spacing", type=float, default=0.76)
    parser.add_argument("--row-spacing", type=float, default=1.10)
    parser.add_argument("--emergent-leaf-width", type=float, default=0.35)
    parser.add_argument("--leaf-vsub", type=float, default=0.008,
                        help="vertical subdivision length. Finer than the videos use "
                             "(0.02), because this mesh gets re-lit in Blender rather "
                             "than resampled onto a 1080p grid")
    parser.add_argument("--leaf-hsub", type=int, default=8)
    parser.add_argument("--out-dir", type=Path,
                        default=Path(__file__).parent / "blender-export")
    parser.add_argument("--format", nargs="+", default=["fbx", "obj"],
                        help="fbx, obj, ply, stl or eveprefab. glTF is unavailable")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()

    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    weeks = field_weeks()
    end_gdd = max(g for _, g in weeks.values())
    descriptors = stage_descriptors(args.week, PLASTOCHRON_GDD, end_gdd,
                                    args.emergent_leaf_width)

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402

    if not hasattr(evo, "ExportSorghumLsPlantsAsModel"):
        raise SystemExit("this build has no ExportSorghumLsPlantsAsModel - rebuild "
                         "the PyDigitalAgriculture target")

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(packages), str(TEMPLATE_SCENE)):
        raise SystemExit("failed to load the template scene")
    evo.WaitForProjectIdle(args.max_wait_frames)
    if hasattr(evo, "RemoveParbarContext"):
        evo.RemoveParbarContext()

    expected = 3 * max(1, args.columns)
    labels = [f"Genotype{g}" for g in GENOTYPES]
    if int(evo.ConfigureSorghumLsPlantingGrid(labels, max(1, args.columns), args.spacing,
                                              args.row_spacing)) != expected:
        raise SystemExit(f"expected {expected} planting markers")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise SystemExit(f"failed to instantiate {expected} plants")
    evo.ConformSorghumLsPlantsToGroundMesh()
    evo.ConfigureSorghumLsLeafMeshQuality(args.leaf_vsub, args.leaf_hsub, False, True, False)
    evo.SetSorghumLsGenotypeDescriptors(descriptors, False, SEED)
    evo.SetSorghumLsFinalizeSnapshotMorphology(False)

    print(f"growing {expected} plants to {args.gdd:.0f} GDD "
          f"(leaf mesh {args.leaf_vsub} / {args.leaf_hsub})", flush=True)
    if int(evo.GrowSorghumLsPlantsToGdd(args.gdd, SEED, True)) != expected:
        raise SystemExit(f"failed to grow to {args.gdd:.0f} GDD")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("geometry never became idle")

    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    triangles = sum(int(r.leaf_triangle_count) + int(r.culm_triangle_count)
                    + int(r.panicle_triangle_count) for r in records)
    print(f"  {len(records)} plants, {triangles:,} triangles", flush=True)

    written = []
    for suffix in args.format:
        path = args.out_dir / f"sorghum_plots_{args.gdd:.0f}gdd.{suffix.lstrip('.')}"
        count = int(evo.ExportSorghumLsPlantsAsModel(str(path)))
        if count == 0:
            print(f"  FAILED {path.name}", flush=True)
            continue
        size = path.stat().st_size / 1e6 if path.is_file() else 0.0
        print(f"  wrote {path.name}  ({count} plants, {size:.1f} MB)", flush=True)
        written.append(path)

    evo.Terminate()
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
