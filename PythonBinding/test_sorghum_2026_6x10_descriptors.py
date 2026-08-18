import tempfile
import unittest
import re
from pathlib import Path

import sorghum_2026_6x10_descriptors as descriptors


class Sorghum2026DescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = descriptors.repo_root_from_script()
        cls.project = cls.repo / "Resources" / "DigitalAgricultureProject"
        cls.data_root = cls.project / "Data" / "Experiments" / descriptors.EXPERIMENT_ID
        cls.base = cls.project / "Assets" / "ManualAssets" / "Descriptors" / "BTX.sorghumls"

    def test_builds_six_separately_named_descriptors_from_one_neutral_prior(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            reports = descriptors.build_all(self.data_root, assets, self.base)
            self.assertEqual(6, len(reports))
            self.assertEqual({False}, {report["technical_prior_is_biological_relationship"] for report in reports})
            self.assertEqual(6, len({report["descriptor_asset_path"] for report in reports}))
            for report in reports:
                path = assets / report["descriptor_asset_path"]
                self.assertTrue(path.is_file())
                self.assertTrue(Path(f"{path}.evefilemeta").is_file())
                text = path.read_text(encoding="utf-8")
                self.assertIn("total_phytomer_count:", text)
                self.assertIn("leaf_blade_length:", text)
                self.assertIn("internode_length:", text)
                self.assertEqual(0.02, report["parameters"]["leaf_gravity_droop_compliance"])
                self.assertEqual("neutral_zero_unmeasured", report["parameters"]["leaf_bending_policy"])
                bending = re.search(r"(?ms)^leaf_bending:\n(.*?)(?=^[a-z_]+:)", text)
                self.assertIsNotNone(bending)
                self.assertNotIn("- [0, 0.75]", bending.group(1))
                self.assertIn("- [0, 0]", bending.group(1))

    def test_bootstrap_and_leave_one_out_are_deterministic(self) -> None:
        first = descriptors.uncertainty([1, 2, 3, 4, 5], 42)
        second = descriptors.uncertainty([1, 2, 3, 4, 5], 42)
        self.assertEqual(first, second)
        self.assertEqual(5, first["n"])
        self.assertEqual(2.5, first["leave_one_out_mean_min"])
        self.assertEqual(3.5, first["leave_one_out_mean_max"])


if __name__ == "__main__":
    unittest.main()
