from __future__ import annotations

import unittest

from sorghum_render_2026_6x10 import OVERVIEW_VIEWS, VIEWS, VIEW_LABELS, camera_for_view, scene_asset
from sorghum_render_4x10_mobile_review import Bounds


class Sorghum2026RenderTest(unittest.TestCase):
    def test_scene_paths_are_experiment_scoped(self) -> None:
        path = scene_asset("MeasurementStage02").as_posix()
        self.assertEqual(
            path,
            "GeneratedAssets/Experiments/Sorghum2026_6x10/Scenes/Sorghum_6x10_MeasurementStage02.evescene",
        )

    def test_overview_cameras_frame_the_same_bounds(self) -> None:
        bounds = Bounds((0.0, 0.0, 0.0), (6.0, 1.5, 5.0))
        perspective = camera_for_view(bounds, "perspective", 16 / 9)
        top = camera_for_view(bounds, "near_top_down", 16 / 9)
        row = camera_for_view(bounds, "row_side", 16 / 9)
        self.assertEqual(perspective["target"], bounds.center)
        self.assertEqual(top["target"], bounds.center)
        self.assertEqual(row["target"], bounds.center)
        self.assertNotEqual(perspective["position"], top["position"])
        self.assertNotEqual(perspective["position"], row["position"])

    def test_multiview_review_covers_field_and_all_genotypes(self) -> None:
        self.assertEqual(OVERVIEW_VIEWS, ("perspective", "near_top_down", "row_side"))
        self.assertEqual(len(VIEWS), 12)
        self.assertEqual(set(VIEWS), set(VIEW_LABELS))
        for prefix in ("genotype_a", "genotype_b", "genotype_c"):
            for detail in ("plant", "basal", "leaf"):
                self.assertIn(f"{prefix}_{detail}", VIEWS)


if __name__ == "__main__":
    unittest.main()
