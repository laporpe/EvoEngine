"""Sweep the season and report what each genotype is doing, GDD by GDD.

Answers two questions that decide the render window:
  * where is culm tip height still climbing for all three genotypes, and
  * where have the panicles emerged.

Culm tip height is internode-derived, so unlike the bounding-box height it has no
mechanism to go backwards - a leaf arching over cannot pull it down. That makes it
the metric to frame a "plants only get bigger" window on.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_abc_growth import (  # noqa: E402
    BUILD, CONFIG, GENOTYPES, PROJECT, TEMPLATE_SCENE, MATURITY_RATIO,
    PLASTOCHRON_GDD, configure_engine_imports, field_weeks, stage_descriptors,
)

SEED = 202_609_020
WEEK = 7
STEPS = 60


def main() -> int:
    weeks = field_weeks()
    end_gdd = max(g for _, g in weeks.values())
    descriptors = stage_descriptors(WEEK, PLASTOCHRON_GDD, end_gdd)

    configure_engine_imports()
    os.chdir(BUILD / "PythonBinding" / CONFIG)
    import PyDigitalAgriculture as evo  # noqa: E402

    packages = BUILD / "EvoEngine_App" / CONFIG / "Packages"
    if not evo.RunLSystemSorghumProject(str(PROJECT), str(packages), str(TEMPLATE_SCENE)):
        raise SystemExit("failed to load the template scene")
    evo.WaitForProjectIdle(30000)
    if hasattr(evo, "RemoveParbarContext"):
        evo.RemoveParbarContext()

    labels = [f"Genotype{g}" for g in GENOTYPES]
    evo.ConfigureSorghumLsPlantingGrid(labels, 1, 0.76, 0.76)
    evo.InstantiateSorghumLsPlantsFromPlantingMarkers()
    evo.ConformSorghumLsPlantsToGroundMesh()
    evo.ConfigureSorghumLsLeafMeshQuality(0.02, 4, False, True, False)
    evo.SetSorghumLsGenotypeDescriptors(descriptors, False, SEED)
    evo.SetSorghumLsFinalizeSnapshotMorphology(False)

    low, high = 900.0, end_gdd
    probe = [low + (high - low) * i / (STEPS - 1) for i in range(STEPS)]
    evo.GrowSorghumLsPlantsToGdd(probe[0], SEED, True)
    evo.WaitForProjectIdle(30000)

    print("\n  GDD    DAP |     culm tip height (m)    |   panicle emerged")
    print("             |    A       B       C       |   A    B    C")
    rows = []
    for value in probe:
        evo.AdvanceSorghumLsPlantsToGdd(value, SEED, True)
        evo.WaitForProjectIdle(30000)
        tip, panicle = {}, {}
        for record in evo.GetSorghumLsPlantSceneMetadata(True):
            name = record.cultivar.replace("Genotype", "")
            main = None
            for axis in record.axes:
                if int(axis.axis_id) == 0:
                    main = axis
                    break
            tip[name] = float(main.culm_tip_height_m) if main else 0.0
            panicle[name] = bool(record.panicle_emerged)
        rows.append((value, tip, panicle))
        print(f"{value:6.0f}       | {tip.get('A', 0):6.3f}  {tip.get('B', 0):6.3f}  "
              f"{tip.get('C', 0):6.3f}  |  {'Y' if panicle.get('A') else '.'}    "
              f"{'Y' if panicle.get('B') else '.'}    {'Y' if panicle.get('C') else '.'}",
              flush=True)

    print("\nmonotonic stretches of culm tip height (all three rising):")
    runs, start = [], None
    for i in range(1, len(rows)):
        rising = all(rows[i][1].get(g, 0) >= rows[i - 1][1].get(g, 0) - 1e-6
                     for g in GENOTYPES)
        gaining = any(rows[i][1].get(g, 0) > rows[i - 1][1].get(g, 0) + 1e-4
                      for g in GENOTYPES)
        if rising and gaining:
            start = rows[i - 1][0] if start is None else start
        elif start is not None:
            runs.append((start, rows[i - 1][0]))
            start = None
    if start is not None:
        runs.append((start, rows[-1][0]))
    for a, b in runs:
        pan = next(r[2] for r in rows if r[0] >= b - 1e-6)
        gain = {g: next(r[1][g] for r in rows if r[0] >= b - 1e-6)
                   - next(r[1][g] for r in rows if r[0] >= a - 1e-6) for g in GENOTYPES}
        flags = "".join(g for g in GENOTYPES if pan.get(g))
        print(f"  {a:6.0f} to {b:6.0f} GDD   gain "
              f"A {gain['A']:+.3f}  B {gain['B']:+.3f}  C {gain['C']:+.3f}   "
              f"panicles: {flags or 'none'}")

    evo.Terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
