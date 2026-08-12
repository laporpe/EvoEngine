from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PythonBinding"))
SPEC = importlib.util.spec_from_file_location(
    "sorghum_2026_6x10_gdd_timelapse",
    ROOT / "PythonBinding/sorghum_2026_6x10_gdd_timelapse.py",
)
TIMELAPSE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TIMELAPSE)


class Sorghum2026GddTimelapseTest(unittest.TestCase):
    def test_target_gdd_schedule_is_one_based_and_complete(self) -> None:
        self.assertAlmostEqual(0.66, TIMELAPSE.state_gdd(1, 660.0))
        self.assertAlmostEqual(660.0, TIMELAPSE.state_gdd(1000, 660.0))

    def test_requested_state_parser_supports_smoke_rendering(self) -> None:
        self.assertEqual(
            (1, 500, 1000), TIMELAPSE.requested_states("1000,500,1,500", 1000)
        )
        with self.assertRaises(ValueError):
            TIMELAPSE.requested_states("0,1000", 1000)

    def test_measured_abc_field_is_the_authoritative_default(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.DEFAULT_FIELD_PROFILE)
        self.assertEqual(("GenotypeA", "GenotypeB", "GenotypeC"), profile["labels"])
        self.assertEqual(
            (
                "GenotypeA",
                "GenotypeA",
                "GenotypeB",
                "GenotypeB",
                "GenotypeC",
                "GenotypeC",
            ),
            profile["row_labels"],
        )
        self.assertEqual(20, profile["plants_per_label"])
        self.assertEqual("authoritative_measured_abc_field", profile["ownership"])

    def test_btx_pawaga_is_an_explicit_reference_profile(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.REFERENCE_FIELD_PROFILE)
        self.assertEqual(("BTX", "Pawaga"), profile["labels"])
        self.assertEqual(
            "reference_demonstration_not_the_measured_abc_field", profile["ownership"]
        )
        self.assertTrue(profile["relabel_markers"])

    def test_multiple_full_lifetime_playback_scales_are_validated(self) -> None:
        self.assertEqual((12, 24, 48), TIMELAPSE.playback_rates("48,12,24,24"))
        with self.assertRaises(ValueError):
            TIMELAPSE.playback_rates("0,24")

    def test_final_panicle_emergence_requires_all_sixty_plants(self) -> None:
        complete = {
            genotype: {"plants": 20, "panicle_emerged_plants": 20}
            for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
        }
        TIMELAPSE.validate_full_panicle_emergence(complete)
        complete["GenotypeC"]["panicle_emerged_plants"] = 19
        with self.assertRaisesRegex(RuntimeError, "59/60"):
            TIMELAPSE.validate_full_panicle_emergence(complete)


if __name__ == "__main__":
    unittest.main()
