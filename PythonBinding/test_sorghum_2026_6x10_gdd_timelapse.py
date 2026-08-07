from __future__ import annotations

from collections import Counter
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

    def test_pawaga_btx_layout_preserves_two_full_and_one_split_2x10_blocks(self) -> None:
        self.assertEqual(("BTX", "Pawaga"), TIMELAPSE.CULTIVARS)
        self.assertEqual(("BTX", "BTX", "Pawaga", "Pawaga", "BTX", "Pawaga"), TIMELAPSE.ROW_CULTIVARS)
        self.assertEqual(Counter(TIMELAPSE.ROW_CULTIVARS), Counter({"BTX": 3, "Pawaga": 3}))
        self.assertEqual(("BTX", "Pawaga"), TIMELAPSE.PLOT_LAYOUT[2]["cultivars"])
        self.assertEqual(30, TIMELAPSE.PLANTS_PER_CULTIVAR)


if __name__ == "__main__":
    unittest.main()
