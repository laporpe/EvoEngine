from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PythonBinding"))
SPEC = importlib.util.spec_from_file_location(
    "sorghum_2026_6x10_gdd_timelapse", ROOT / "PythonBinding/sorghum_2026_6x10_gdd_timelapse.py"
)
TIMELAPSE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TIMELAPSE)


class Sorghum2026GddTimelapseTest(unittest.TestCase):
    def test_target_gdd_schedule_is_one_based_and_complete(self) -> None:
        self.assertAlmostEqual(0.66, TIMELAPSE.state_gdd(1, 660.0))
        self.assertAlmostEqual(660.0, TIMELAPSE.state_gdd(1000, 660.0))

    def test_requested_state_parser_supports_smoke_rendering(self) -> None:
        self.assertEqual((1, 500, 1000), TIMELAPSE.requested_states("1000,500,1,500", 1000))
        with self.assertRaises(ValueError):
            TIMELAPSE.requested_states("0,1000", 1000)


if __name__ == "__main__":
    unittest.main()
