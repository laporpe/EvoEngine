from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sorghum_2026_panicle_timelapse",
    ROOT / "Scripts/blender/create_sorghum_2026_panicle_timelapse.py",
)
assert SPEC and SPEC.loader
TIMELAPSE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TIMELAPSE
SPEC.loader.exec_module(TIMELAPSE)


class Sorghum2026PanicleTimelapseTests(unittest.TestCase):
    def test_stage_plan_runs_from_seed_to_reproductive_maturity(self) -> None:
        stages = TIMELAPSE.stage_plan()
        self.assertEqual("Seed", stages[0].name)
        self.assertEqual("Reproductive maturity", stages[-1].name)
        self.assertEqual(1, stages[0].frame)
        self.assertEqual(1000, stages[-1].frame)
        self.assertEqual(
            sorted(stage.frame for stage in stages), [stage.frame for stage in stages]
        )

    def test_each_of_the_thousand_field_states_maps_to_target_gdd(self) -> None:
        self.assertAlmostEqual(0.66, TIMELAPSE.gdd_at_field(1, 660.0))
        self.assertAlmostEqual(660.0, TIMELAPSE.gdd_at_field(1000, 660.0))
        timeline = TIMELAPSE.panicle_timeline(660.0, 260.0)
        self.assertLess(timeline["boot"], timeline["emergence"])
        self.assertLess(timeline["emergence"], timeline["full_exsertion"])
        self.assertLess(timeline["full_exsertion"], timeline["anthesis_start"])
        self.assertLess(timeline["anthesis_start"], timeline["anthesis_end"])
        self.assertEqual(1000, timeline["maturity"])

    def test_layout_preserves_three_genotype_six_by_ten_design(self) -> None:
        layout = TIMELAPSE.field_layout()
        self.assertEqual(60, len(layout))
        self.assertEqual(
            {"GenotypeA": 20, "GenotypeB": 20, "GenotypeC": 20},
            {
                genotype: sum(row[0] == genotype for row in layout)
                for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
            },
        )
        self.assertEqual(60, len({(row[1], row[2]) for row in layout}))

    def test_panicle_form_is_genotype_parameterized(self) -> None:
        forms = {
            genotype: TIMELAPSE.panicle_style(genotype, 1.0, 13.0)
            for genotype in TIMELAPSE.PANICLE_STYLES
        }
        self.assertGreater(
            forms["GenotypeA"]["radius_m"], forms["GenotypeC"]["radius_m"]
        )
        self.assertGreater(
            forms["GenotypeC"]["branch_count"], forms["GenotypeA"]["branch_count"]
        )

    def test_midday_reference_is_fixed(self) -> None:
        TIMELAPSE.validate_spec()
        self.assertEqual((90.0, 0.0, 0.0), TIMELAPSE.MIDDAY_SUN_ANGLES_DEGREES)


if __name__ == "__main__":
    unittest.main()
