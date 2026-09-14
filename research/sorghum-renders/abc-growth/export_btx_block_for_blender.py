"""Export the BTx623 / Pawaga PARBAR block as a model file for Blender.

    python export_btx_block_for_blender.py [--layout small] [--format fbx]

Rebuilds exactly the stand that btx-pawaga-illumination/render_field_publication.py
renders - same scene, descriptors, seed, layout and leaf-mesh quality - by
importing that work's own constants read-only, then writes it through
ExportSorghumLsPlantsAsModel. Nothing in btx-pawaga-illumination/ is modified.

Alongside the model it writes a JSON sidecar describing the planting grid, so
the Blender side can label rows by genotype and frame the whole block without
guessing at its extent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "btx-pawaga-illumination"))
from run_tau_diurnal import (  # noqa: E402  (read-only import of the other work's constants)
    BUILD, CONFIG, PROJECT, SCENE, LAYOUTS, COLUMNS, COLUMN_SPACING_M, ROW_SPACING_M, CENTER_X_M,
    configure_engine_imports, stage_descriptors,
)

SEED = 422021                       # render_field_publication.py default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--layout", default="small", choices=sorted(LAYOUTS))
    parser.add_argument("--btx-descriptor", default="BTX623_20210726_cal1.sorghumls")
    parser.add_argument("--pawaga-descriptor", default="Pawaga_20210726_cal1.sorghumls")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--leaf-vsub", type=float, default=0.01)
    parser.add_argument("--leaf-hsub", type=int, default=6)
    parser.add_argument("--format", nargs="+", default=["fbx"])
    parser.add_argument("--out-dir", type=Path, default=HERE / "blender-export")
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    args = parser.parse_args()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    descriptors = stage_descriptors("v1", args.btx_descriptor, args.pawaga_descriptor)
    row_genotypes, center_z = LAYOUTS[args.layout]
    expected = len(row_genotypes) * COLUMNS

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402
    if not hasattr(evo, "ExportSorghumLsPlantsAsModel"):
        raise SystemExit("this build has no ExportSorghumLsPlantsAsModel")

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(packages), str(SCENE)):
        raise SystemExit(f"failed to load {SCENE}")
    evo.WaitForProjectIdle(args.max_wait_frames)

    if int(evo.ConfigureSorghumLsPlantingGrid(row_genotypes, COLUMNS, COLUMN_SPACING_M,
                                              ROW_SPACING_M, CENTER_X_M, center_z)) != expected:
        raise SystemExit(f"expected {expected} planting markers")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != expected:
        raise SystemExit(f"failed to instantiate {expected} plants")
    evo.ConformSorghumLsPlantsToGroundMesh()
    if int(evo.SetSorghumLsGenotypeDescriptors(descriptors, False, args.seed)) != expected:
        raise SystemExit("descriptor bind failed")
    evo.ConfigureSorghumLsLeafMeshQuality(args.leaf_vsub, args.leaf_hsub, False, True, False)
    print(f"growing {expected} plants to adulthood ({args.layout}: "
          f"{len(row_genotypes)} rows x {COLUMNS})", flush=True)
    if int(evo.GrowSorghumLsPlantsToAdulthood(args.seed, "", False, True)) != expected:
        raise SystemExit("growth failed")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise SystemExit("post-growth idle failed")

    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    heights = {}
    for r in records:
        heights.setdefault(r.cultivar, []).append(float(r.plant_height_m))
    for cultivar, hs in sorted(heights.items()):
        print(f"  {cultivar:8s} n={len(hs):2d}  mean height {sum(hs)/len(hs):.2f} m", flush=True)

    # Sidecar: everything Blender needs to label and frame the block. Engine
    # axes are Y-up; rows advance along z, plants along x.
    sidecar = {
        "layout": args.layout,
        "row_genotypes": row_genotypes,
        "columns": COLUMNS,
        "column_spacing_m": COLUMN_SPACING_M,
        "row_spacing_m": ROW_SPACING_M,
        "center_x_m": CENTER_X_M,
        "center_z_m": center_z,
        "seed": args.seed,
        "mean_height_m": {k: sum(v) / len(v) for k, v in heights.items()},
        "engine_axes": "y up; rows along z (east), plants along x (north)",
        "blender_axes": "x = engine x, y = -engine z, z = engine y",
    }
    (args.out_dir / f"btx_block_{args.layout}.json").write_text(json.dumps(sidecar, indent=1))

    written = []
    for suffix in args.format:
        path = args.out_dir / f"btx_block_{args.layout}.{suffix.lstrip('.')}"
        count = int(evo.ExportSorghumLsPlantsAsModel(str(path)))
        if count == 0:
            print(f"  FAILED {path.name}", flush=True)
            continue
        print(f"  wrote {path.name}  ({count} plants, {path.stat().st_size / 1e6:.1f} MB)", flush=True)
        written.append(path)

    evo.Terminate()
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
