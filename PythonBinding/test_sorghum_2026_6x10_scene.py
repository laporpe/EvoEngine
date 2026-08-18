from __future__ import annotations

import unittest
from types import SimpleNamespace

from sorghum_2026_6x10_scene import (
    collection_dates,
    descriptor_maps,
    validate_parbar_scene_text,
    validate_profile_geometry,
    validate_records,
)


class Sorghum2026SixByTenSceneTest(unittest.TestCase):
    def test_descriptor_report_requires_all_six_assets(self) -> None:
        rows = [
            {
                "session_id": session,
                "genotype_id": genotype,
                "descriptor_asset_path": f"Generated/{session}/{genotype}.sorghumls",
            }
            for session in ("MeasurementStage01", "MeasurementStage02")
            for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
        ]
        result = descriptor_maps({"descriptors": rows})
        self.assertEqual(result["MeasurementStage02"]["GenotypeC"].name, "GenotypeC.sorghumls")

    def test_collection_dates_preserve_stage_one_genotype_a_difference(self) -> None:
        result = collection_dates(
            [
                {"session_id": "MeasurementStage01", "genotype_id": "GenotypeA", "collection_date": "2026-07-16"},
                {"session_id": "MeasurementStage01", "genotype_id": "GenotypeB", "collection_date": "2026-07-15"},
            ]
        )
        self.assertEqual(result["MeasurementStage01"]["GenotypeA"], ("2026-07-16",))
        self.assertEqual(result["MeasurementStage01"]["GenotypeB"], ("2026-07-15",))

    def test_scene_identity_is_exactly_six_by_ten(self) -> None:
        records = []
        row_genotypes = ("GenotypeA", "GenotypeA", "GenotypeB", "GenotypeB", "GenotypeC", "GenotypeC")
        for row, genotype in enumerate(row_genotypes):
            for column in range(10):
                records.append(
                    SimpleNamespace(
                        name=f"{genotype}_LSystem_R{row}_C{column}",
                        cultivar=genotype,
                        has_geometry=True,
                        seed=1000 + row * 10 + column,
                    )
                )
        validate_records("MeasurementStage01", records)

    def test_repeated_two_by_ten_spacing_contract(self) -> None:
        records = []
        row_z = (-5.31, -6.41, -8.61, -9.71, -11.91, -13.01)
        row_genotypes = ("GenotypeA", "GenotypeA", "GenotypeB", "GenotypeB", "GenotypeC", "GenotypeC")
        for row, (genotype, z_m) in enumerate(zip(row_genotypes, row_z)):
            for column in range(10):
                records.append(
                    SimpleNamespace(
                        name=f"{genotype}_LSystem_R{row}_C{column}",
                        global_position=SimpleNamespace(x=-0.84 + 0.76 * column, z=z_m),
                    )
                )
        validate_profile_geometry("MeasurementStage01", records)
        records[20].global_position.z += 0.2
        with self.assertRaisesRegex(RuntimeError, "row 2 is not straight"):
            validate_profile_geometry("MeasurementStage01", records)

    def test_parbar_contract_requires_three_complete_three_bar_rigs(self) -> None:
        scene_text = "\n".join(
            [f"  - n: PARBAR_{genotype}" for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")]
            + [
                f"  - n: PARBAR_{genotype}_{level}SensorBarMesh"
                for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
                for level in ("Top", "Middle", "Bottom")
            ]
        )
        validate_parbar_scene_text(scene_text)
        with self.assertRaisesRegex(RuntimeError, "expected exactly one"):
            validate_parbar_scene_text(scene_text.replace("PARBAR_GenotypeC_TopSensorBarMesh", "missing"))


if __name__ == "__main__":
    unittest.main()
