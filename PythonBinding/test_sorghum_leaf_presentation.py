import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER = (
    ROOT
    / "Scripts"
    / "sorghum_leaf_materials"
    / "assets"
    / "leaf_anatomy_master_v2.png"
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SorghumLeafPresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.presentation = load(
            "sorghum_leaf_presentation",
            ROOT / "Scripts" / "blender" / "sorghum_leaf_presentation.py",
        )
        cls.atlas = load(
            "bake_continuous_sorghum_leaf_atlas",
            ROOT
            / "Scripts"
            / "sorghum_leaf_materials"
            / "bake_continuous_sorghum_leaf_atlas.py",
        )

    def test_only_distal_blade_components_receive_presentation_bend(self):
        self.assertFalse(self.presentation.is_blade_component(0.02, 0.48))
        self.assertFalse(self.presentation.is_blade_component(0.51, 0.59))
        self.assertTrue(self.presentation.is_blade_component(0.59, 0.99))
        self.assertTrue(self.presentation.is_blade_component(0.55, 0.99))

    def test_blade_base_is_pinned(self):
        self.assertEqual(self.presentation.blade_bend_weight(0.59, 0.59, 0.99, 0.20), 0.0)
        self.assertEqual(self.presentation.blade_bend_weight(0.66, 0.59, 0.99, 0.20), 0.0)
        self.assertAlmostEqual(self.presentation.blade_bend_weight(0.99, 0.59, 0.99, 0.20), 1.0)

    def test_continuous_atlas_meets_presentation_seam_contract(self):
        self.assertTrue(MASTER.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            result = self.atlas.bake_continuous_atlas(
                MASTER,
                Path(temporary),
                tile_size=256,
            )
            report = json.loads(result["report"].read_text(encoding="utf-8"))
            self.assertEqual(report["ownership"], "blender_presentation_only")
            self.assertEqual(report["variant_count"], 9)
            self.assertEqual(report["atlas_size"], [768, 768])
            self.assertLessEqual(report["seam_metrics"]["albedo_mean_rgb_255"], 4.0)
            self.assertLessEqual(report["seam_metrics"]["normal_mean_rgb_255"], 8.0)
            self.assertLessEqual(report["seam_metrics"]["roughness_mean_255"], 5.1)
            self.assertLessEqual(report["seam_metrics"]["height_mean_255"], 8.0)
            self.assertLessEqual(report["seam_metrics"]["ao_mean_255"], 5.1)
            for key in ("albedo", "normal", "roughness", "height", "ao", "metallic", "thickness"):
                self.assertTrue(result[key].is_file(), key)


if __name__ == "__main__":
    unittest.main()
