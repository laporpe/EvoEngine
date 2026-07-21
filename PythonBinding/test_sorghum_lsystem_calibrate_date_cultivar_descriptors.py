from types import SimpleNamespace
import unittest

from sorghum_lsystem_calibrate_date_cultivar_descriptors import (
    Knobs,
    Target,
    sample_descriptor,
    summarize_records,
    update_knobs,
)


def axis(axis_id: int, leaf_ratio: float = 1.0, height_ratio: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(axis_id=axis_id, leaf_ratio_to_main=leaf_ratio, height_ratio_to_main=height_ratio)


def record(seed: int, height: float, culm_ratio: float, collar_ratio: float) -> SimpleNamespace:
    return SimpleNamespace(
        seed=seed,
        height_m=height,
        main_culm_leaf_count=12,
        live_leaf_count=36,
        leaf_area=1.2,
        stem_area=0.2,
        has_geometry=True,
        axes=[axis(0), axis(1, 0.7, 0.8), axis(2, 0.8, 0.9)],
        primary_tiller_count=2,
        main_culm_tip_height_ratio=culm_ratio,
        main_culm_mature_collar_height_ratio=collar_ratio,
        main_culm_max_blade_length_m=0.60,
        main_culm_max_target_blade_length_m=0.70,
        main_culm_max_blade_width_m=0.08,
        main_culm_max_target_blade_width_m=0.09,
    )


class SorghumPhenotypeSummaryTests(unittest.TestCase):
    def test_calibration_samples_the_serialized_finalized_snapshot_at_date_gdd(self) -> None:
        calls: list[tuple[object, ...]] = []
        evo = SimpleNamespace(SampleSorghumLsDescriptorPhenotypes=lambda *args: calls.append(args) or [])
        args = SimpleNamespace(btx_descriptor="BTX", pawaga_descriptor="Pawaga")
        target = Target("2021-07-01", "BTX", 13.0, 1.0, 0.5, 0.1, 1.0, 1)

        sample_descriptor(evo, args, target, Knobs(13.0, 1.0, 1.0, 1.0, 0.9, 0.9), 1, 0)

        self.assertTrue(calls[0][11])
        self.assertAlmostEqual(calls[0][7], 0.080 / 0.126)
        expected_leaf_scale = 0.597166 / 1.1869 * 0.9
        self.assertAlmostEqual(calls[0][13], expected_leaf_scale)
        self.assertAlmostEqual(calls[0][14], expected_leaf_scale)
        self.assertEqual(calls[0][-1], 512.0)

    def test_height_calibration_does_not_rescale_the_authored_leaf_profile(self) -> None:
        target = Target("2021-08-30", "BTX", 18.0, 1.0, 2.0, 0.2, 1.0, 1)
        knobs = Knobs(18.0, 1.0, 1.0, 1.0, 1.0, 1.0)
        metrics = {
            "leaf_mean": 18.0,
            "leaf_std": 1.0,
            "height_mean_m": 1.0,
            "height_std_m": 0.2,
            "tiller_leaf_ratio_mean": 0.9,
            "tiller_height_ratio_mean": 0.9,
        }

        updated = update_knobs(target, metrics, knobs)

        self.assertGreater(updated.length_mean_scale, 1.0)
        self.assertEqual(updated.leaf_length_mean_scale, 1.0)
        self.assertEqual(updated.leaf_length_deviation_scale, 1.0)

    def test_oversized_early_blades_may_shorten_but_never_exceed_the_authored_profile(self) -> None:
        target = Target("2021-07-01", "BTX", 13.0, 1.0, 0.5, 0.1, 1.0, 1)
        knobs = Knobs(13.0, 1.0, 0.2, 1.0, 1.0, 1.0)
        metrics = {
            "leaf_mean": 13.0,
            "leaf_std": 1.0,
            "height_mean_m": 0.8,
            "height_std_m": 0.1,
            "tiller_leaf_ratio_mean": 0.9,
            "tiller_height_ratio_mean": 0.9,
        }

        shortened = update_knobs(target, metrics, knobs)
        metrics["height_mean_m"] = 0.4
        corrected_upward = update_knobs(target, metrics, shortened)

        self.assertLess(shortened.leaf_length_mean_scale, 1.0)
        self.assertEqual(corrected_upward.leaf_length_mean_scale, shortened.leaf_length_mean_scale)

    def test_summarizes_height_allocation_and_realized_versus_target_blades(self) -> None:
        metrics = summarize_records([record(1, 0.6, 0.45, 0.4), record(2, 0.7, 0.55, 0.44)], 2)

        self.assertAlmostEqual(metrics["main_culm_tip_height_ratio_mean"], 0.5)
        self.assertAlmostEqual(metrics["main_culm_mature_collar_height_ratio_mean"], 0.42)
        self.assertAlmostEqual(metrics["main_culm_max_blade_length_mean_m"], 0.60)
        self.assertAlmostEqual(metrics["main_culm_max_target_blade_length_mean_m"], 0.70)
        self.assertAlmostEqual(metrics["main_culm_max_blade_width_mean_m"], 0.08)
        self.assertAlmostEqual(metrics["main_culm_max_target_blade_width_mean_m"], 0.09)
        self.assertAlmostEqual(metrics["tiller_leaf_ratio_mean"], 0.75)
        self.assertAlmostEqual(metrics["tiller_height_ratio_mean"], 0.85)

if __name__ == "__main__":
    unittest.main()
