import unittest
from pathlib import Path

import sorghum_2026_6x10_data as data


class Sorghum2026DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source_dir = data.repo_root_from_script().parent / "sources"
        if not source_dir.is_dir():
            raise unittest.SkipTest(f"source directory unavailable: {source_dir}")
        cls.sources = data.load_sources(source_dir)
        cls.normalized = data.normalize_sources(cls.sources)
        cls.targets = data.target_tables(cls.normalized)

    def test_source_inventory_and_unique_plant_keys(self) -> None:
        self.assertEqual(6, len(self.sources))
        self.assertTrue(all(len(source.rows) == 15 for source in self.sources.values()))
        plants = self.normalized["plants"]
        self.assertEqual(30, len(plants))
        self.assertEqual(30, len({row["plant_id"] for row in plants}))

    def test_genotype_mapping_and_first_session_dates(self) -> None:
        plants = self.normalized["plants"]
        stage1_dates = {
            genotype: {row["collection_date"] for row in plants if row["session_id"] == "MeasurementStage01" and row["genotype_id"] == genotype}
            for genotype in data.GENOTYPE_LABELS
        }
        self.assertEqual({"2026-07-16"}, stage1_dates["GenotypeA"])
        self.assertEqual({"2026-07-15"}, stage1_dates["GenotypeB"])
        self.assertEqual({"2026-07-15"}, stage1_dates["GenotypeC"])

    def test_internode_semantics_are_normalized_separately(self) -> None:
        rows = self.normalized["internodes"]
        self.assertTrue(all("minus_1cm" in row["length_semantics"] for row in rows if row["session_id"] == "MeasurementStage01"))
        self.assertTrue(all(row["length_semantics"] == "individual_collar_length_cm" for row in rows if row["session_id"] == "MeasurementStage02"))

    def test_unit_assumption_and_decimal_outlier_remain_explicit(self) -> None:
        leaves = self.normalized["leaves"]
        assumed = [row for row in leaves if row["width_qc"] == "unit_assumption_pending_confirmation"]
        self.assertGreater(len(assumed), 150)
        outliers = [row for row in leaves if row["length_qc"] == "suspected_decimal_transcription_outlier_excluded"]
        self.assertEqual(1, len(outliers))
        self.assertEqual(("MeasurementStage02", "GenotypeC", 3, 4.35, None), (
            outliers[0]["session_id"], outliers[0]["genotype_id"], outliers[0]["leaf_rank"], outliers[0]["length_raw"], outliers[0]["length_m"]
        ))

    def test_six_descriptor_targets_each_have_five_plants(self) -> None:
        targets = self.targets["descriptor_targets"]
        self.assertEqual(6, len(targets))
        self.assertTrue(all(row["sample_count"] == 5 for row in targets))


if __name__ == "__main__":
    unittest.main()
