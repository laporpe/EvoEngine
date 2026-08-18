import unittest

from sorghum_2026_6x10_validate_descriptors import acceptance


class Sorghum2026DescriptorValidationTests(unittest.TestCase):
    def test_acceptance_passes_measured_population_tolerances(self) -> None:
        target = {"height_m": 1.0, "leaf_count": 12.0, "tiller_count": 2.0, "max_leaf_length_m": 0.8, "max_leaf_width_m": 0.08}
        metrics = {
            "height_mean_m": 0.95,
            "leaf_mean": 12.4,
            "tiller_count_mean": 2.2,
            "main_culm_max_target_blade_length_mean_m": 0.78,
            "main_culm_max_target_blade_width_mean_m": 0.079,
            "main_culm_gravity_tip_deflection_mean_m": 0.01,
            "main_culm_centerline_arc_to_chord_mean": 1.02,
        }
        self.assertTrue(acceptance(target, metrics)["success"])

    def test_tallest_leaf_height_is_diagnostic_when_curvature_is_unmeasured(self) -> None:
        target = {"height_m": 1.0, "leaf_count": 12.0, "tiller_count": 2.0, "max_leaf_length_m": 0.8, "max_leaf_width_m": 0.08}
        metrics = {
            "height_mean_m": 0.7,
            "leaf_mean": 12.0,
            "tiller_count_mean": 2.0,
            "main_culm_max_target_blade_length_mean_m": 0.8,
            "main_culm_max_target_blade_width_mean_m": 0.08,
            "main_culm_gravity_tip_deflection_mean_m": 0.01,
            "main_culm_centerline_arc_to_chord_mean": 1.02,
        }
        result = acceptance(target, metrics)
        self.assertTrue(result["success"])
        self.assertAlmostEqual(0.3, result["diagnostics"]["tallest_leaf_height_relative_error"])

    def test_acceptance_rejects_excessive_unmeasured_droop(self) -> None:
        target = {"height_m": 1.0, "leaf_count": 12.0, "tiller_count": 2.0, "max_leaf_length_m": 0.8, "max_leaf_width_m": 0.08}
        metrics = {
            "height_mean_m": 1.0,
            "leaf_mean": 12.0,
            "tiller_count_mean": 2.0,
            "main_culm_max_target_blade_length_mean_m": 0.8,
            "main_culm_max_target_blade_width_mean_m": 0.08,
            "main_culm_gravity_tip_deflection_mean_m": 0.3,
            "main_culm_centerline_arc_to_chord_mean": 1.4,
        }
        result = acceptance(target, metrics)
        self.assertFalse(result["success"])
        self.assertEqual(["gravity_tip_deflection_fraction", "centerline_arc_to_chord_excess"], result["failed_metrics"])


if __name__ == "__main__":
    unittest.main()
