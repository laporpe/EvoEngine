import importlib.util
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "Scripts" / "blender" / "sorghum_2026_background.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sorghum_2026_background", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Sorghum2026BackgroundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.background = load_module()

    def test_sierra_estrella_proxy_scale_is_restrained(self):
        angle = self.background.angular_height_degrees(362.0, 1235.0, 29.94)
        self.assertTrue(math.isclose(angle, 1.67, abs_tol=0.02))
        self.assertEqual(self.background.SITE_PROXY["source"], "University of Arizona AZMET Maricopa")
        self.assertEqual(self.background.SIERRA_PROFILE_LICENSE, "USGS public domain")

    def test_artistic_heading_keeps_the_range_visible_without_claiming_plot_orientation(self):
        self.assertTrue(math.isclose(self.background.scene_azimuth_degrees(307.0), 25.0, abs_tol=1.0e-9))
        self.assertEqual(self.background.ORIENTATION_POLICY, "artistically_aligned_plot_heading_not_measured")

    def test_bakeoff_variants_add_layers_monotonically(self):
        previous = set()
        self.assertEqual(tuple(self.background.BACKGROUND_VARIANTS), (
            "control", "horizon", "apron", "agriculture", "mountains", "final"
        ))
        for variant in self.background.BACKGROUND_VARIANTS:
            layers = set(self.background.BACKGROUND_VARIANT_LAYERS[variant])
            self.assertLessEqual(previous, layers)
            previous = layers
        self.assertEqual(previous, {"terrain", "lane", "agriculture", "mountain", "haze", "finish"})

    def test_measurement_views_do_not_force_far_landscape(self):
        for view in ("near_top_down", "genotype_a_basal", "genotype_b_leaf", "genotype_c_basal"):
            self.assertNotIn("mountain", self.background.layers_for_view(view, "final"))
            self.assertNotIn("haze", self.background.layers_for_view(view, "final"))
            self.assertNotIn("lane", self.background.layers_for_view(view, "final"))
        for view in ("perspective", "row_side", "genotype_a_plant"):
            self.assertIn("mountain", self.background.layers_for_view(view, "final"))

    def test_render_only_contract_blocks_all_non_camera_rays(self):
        self.assertEqual(self.background.RENDER_ONLY_OWNERSHIP, "blender_presentation_only")
        self.assertEqual(
            self.background.RAY_VISIBILITY_CONTRACT,
            {
                "camera": True,
                "diffuse": False,
                "glossy": False,
                "transmission": False,
                "shadow": False,
                "volume_scatter": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
