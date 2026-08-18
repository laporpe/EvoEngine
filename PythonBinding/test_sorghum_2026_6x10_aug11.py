from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sorghum_2026_6x10_aug11_data as data
import sorghum_2026_6x10_aug11_descriptors as descriptors
from sorghum_2026_6x10_aug11_calibrate import updated_scales
from sorghum_2026_6x10_scene import descriptor_maps


class Sorghum2026Aug11Tests(unittest.TestCase):
    def test_aggregate_calibration_multiplies_existing_scales(self) -> None:
        measured = {
            "internode_sum_m": 2.0,
            "maximum_leaf_length_m": 1.0,
            "maximum_leaf_width_m": 0.1,
        }
        sampled = {
            "sampled_internode_sum_m": 1.0,
            "sampled_maximum_leaf_length_m": 0.8,
            "sampled_maximum_leaf_width_m": 0.08,
        }
        scales = updated_scales(measured, sampled, {"internode_length_scale": 0.5})
        self.assertEqual(scales["internode_length_scale"], 1.0)
        self.assertEqual(scales["leaf_length_scale"], 1.25)
        self.assertEqual(scales["leaf_width_scale"], 1.25)

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = data.repo_root_from_script()
        cls.source_dir = cls.repo.parent / "sources" / data.EXPERIMENT_ID
        if not cls.source_dir.is_dir():
            raise unittest.SkipTest(f"source directory unavailable: {cls.source_dir}")
        cls.sources = data.load_sources(cls.source_dir)
        cls.normalized = data.normalize_sources(cls.sources)
        cls.targets = data.target_tables(cls.normalized)

    def test_imports_one_endpoint_with_five_plants_per_genotype(self) -> None:
        self.assertEqual(3, len(self.sources))
        self.assertEqual(15, len(self.normalized["plants"]))
        self.assertEqual(3, len(self.targets["descriptor_targets"]))
        self.assertEqual({5}, {row["sample_count"] for row in self.targets["descriptor_targets"]})

    def test_source_manifest_does_not_embed_a_machine_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data.write_outputs(self.source_dir, Path(directory))
            manifest = json.loads((Path(directory) / "source_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(data.EXPERIMENT_ID, manifest["source_directory"])

    def test_range_mapping_dates_and_panicle_state_are_preserved(self) -> None:
        plants = self.normalized["plants"]
        self.assertEqual({"2026-08-12"}, {row["collection_date"] for row in plants if row["genotype_id"] == "GenotypeA"})
        self.assertEqual({"2026-08-11"}, {row["collection_date"] for row in plants if row["genotype_id"] != "GenotypeA"})
        rates = {row["genotype_id"]: row["panicle_emerged_rate"] for row in self.targets["descriptor_targets"]}
        self.assertEqual({"GenotypeA": 0.0, "GenotypeB": 0.0, "GenotypeC": 1.0}, rates)

    def test_measured_height_targets_match_source_means(self) -> None:
        targets = {row["genotype_id"]: row for row in self.targets["descriptor_targets"]}
        self.assertAlmostEqual(1.402, targets["GenotypeA"]["height_m_mean"])
        self.assertAlmostEqual(2.19, targets["GenotypeB"]["height_m_mean"])
        self.assertAlmostEqual(2.22, targets["GenotypeC"]["height_m_mean"])
        self.assertAlmostEqual(0.201, targets["GenotypeC"]["panicle_length_m_mean"])
        self.assertAlmostEqual(0.068, targets["GenotypeC"]["panicle_width_m_mean"])

    def test_builds_three_endpoint_descriptors_from_existing_abc_priors(self) -> None:
        project = self.repo / "Resources" / "DigitalAgricultureProject"
        data_root = project / "Data" / "Experiments" / data.EXPERIMENT_ID
        with tempfile.TemporaryDirectory() as directory:
            reports = descriptors.build_all(data_root, Path(directory), project / "Assets")
            self.assertEqual(3, len(reports))
            mapped = descriptor_maps({"descriptors": reports}, (data.SESSION_ID,))
            self.assertEqual(set(descriptors.GENOTYPES), set(mapped[data.SESSION_ID]))
            for report in reports:
                text = (Path(directory) / report["descriptor_asset_path"]).read_text(encoding="utf-8")
                self.assertIn("finalize_snapshot_morphology: true", text)
                enabled = report["genotype_id"] == "GenotypeC"
                self.assertIn(f"enable_panicle: {str(enabled).lower()}", text)
                self.assertTrue(report["technical_prior_is_existing_btx_derived_genotype"])
            c_text = (Path(directory) / reports[2]["descriptor_asset_path"]).read_text(encoding="utf-8")
            self.assertIn("panicle_rachis_length_m:", c_text)
            self.assertIn("panicle_branch_length_m:", c_text)


if __name__ == "__main__":
    unittest.main()
