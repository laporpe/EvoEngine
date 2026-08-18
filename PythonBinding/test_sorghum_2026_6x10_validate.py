import json
import tempfile
import unittest
from pathlib import Path

import sorghum_2026_6x10_validate as validation


class Sorghum2026ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = validation.repo_root_from_script()
        cls.project = cls.repo / "Resources" / "DigitalAgricultureProject"
        cls.data_root = cls.project / "Data" / "Experiments" / validation.EXPERIMENT_ID

    def test_normalized_contract(self) -> None:
        result = validation.validate_normalized(self.data_root)
        self.assertEqual("valid", result["status"])
        self.assertEqual(30, result["measured_plant_count"])

    def test_legacy_baseline_is_immutable(self) -> None:
        baseline = self.data_root / "legacy_4x10_baseline.json"
        if not baseline.is_file():
            self.skipTest("legacy baseline has not been generated")
        self.assertEqual("exact_match", validation.validate_legacy(self.project, baseline)["status"])

    def test_generated_scene_profile_preserves_manual_block_spacing(self) -> None:
        result = validation.validate_scene_manifest(self.data_root)
        self.assertEqual("valid", result["status"])
        self.assertEqual(120, result["plant_rows"])

    def test_detects_baseline_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in validation.LEGACY_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative, encoding="utf-8")
            baseline_path = root / "baseline.json"
            validation.write_baseline(root, baseline_path)
            target = root / validation.LEGACY_PATHS[0]
            target.write_text("changed", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validation.validate_legacy(root, baseline_path)


if __name__ == "__main__":
    unittest.main()
