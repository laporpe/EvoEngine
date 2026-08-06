from __future__ import annotations

import unittest

from sorghum_calibrate_morphology_allocation import fit_scale


class SorghumMorphologyAllocationCalibrationTest(unittest.TestCase):
    def test_fit_scale_finds_monotonic_height_target(self) -> None:
        scale, metrics = fit_scale(lambda value: {"height_mean_m": 0.4 + 0.5 * value}, 0.65, iterations=10)
        self.assertAlmostEqual(scale, 0.5, places=2)
        self.assertAlmostEqual(metrics["height_mean_m"], 0.65, places=2)

    def test_fit_scale_returns_nearest_boundary_for_unreachable_target(self) -> None:
        scale, _ = fit_scale(lambda value: {"height_mean_m": 0.7 + value}, 0.5)
        self.assertEqual(scale, 0.2)


if __name__ == "__main__":
    unittest.main()
