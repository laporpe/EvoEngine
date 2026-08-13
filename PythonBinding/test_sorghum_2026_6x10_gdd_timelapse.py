from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PythonBinding"))
SPEC = importlib.util.spec_from_file_location(
    "sorghum_2026_6x10_gdd_timelapse",
    ROOT / "PythonBinding/sorghum_2026_6x10_gdd_timelapse.py",
)
TIMELAPSE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TIMELAPSE)


class Sorghum2026GddTimelapseTest(unittest.TestCase):
    def test_target_gdd_schedule_is_one_based_and_complete(self) -> None:
        self.assertAlmostEqual(0.66, TIMELAPSE.state_gdd(1, 660.0))
        self.assertAlmostEqual(660.0, TIMELAPSE.state_gdd(1000, 660.0))

    def test_requested_state_parser_supports_smoke_rendering(self) -> None:
        self.assertEqual(
            (1, 500, 1000), TIMELAPSE.requested_states("1000,500,1,500", 1000)
        )
        with self.assertRaises(ValueError):
            TIMELAPSE.requested_states("0,1000", 1000)

    def test_abc_field_with_shared_btx_vegetative_morphology_is_default(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.DEFAULT_FIELD_PROFILE)
        self.assertEqual(("GenotypeA", "GenotypeB", "GenotypeC"), profile["labels"])
        self.assertEqual(
            (
                "GenotypeA",
                "GenotypeA",
                "GenotypeB",
                "GenotypeB",
                "GenotypeC",
                "GenotypeC",
            ),
            profile["row_labels"],
        )
        self.assertEqual(20, profile["plants_per_label"])
        self.assertEqual(
            "authoritative_measured_abc_field_with_shared_btx_vegetative_morphology",
            profile["ownership"],
        )
        btx = Path("ManualAssets/Descriptors/BTX.sorghumls")
        self.assertEqual(
            {genotype: btx for genotype in profile["labels"]},
            profile["descriptor_paths"],
        )
        self.assertEqual(1, len(set(profile["descriptor_paths"].values())))
        self.assertEqual(
            "explicit_shared_abc_reproductive_presentation_separate_from_btx_vegetative",
            profile["panicle_parameter_policy"],
        )
        self.assertEqual(0.82, profile["panicle_presentation"]["peduncle_length_m"])

    def test_previous_measured_vegetative_profile_remains_separate(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.MEASURED_VEGETATIVE_FIELD_PROFILE)
        self.assertEqual(
            "superseded_measured_abc_vegetative_reference", profile["ownership"]
        )
        self.assertEqual(3, len(set(profile["descriptor_paths"].values())))

    def test_compact_panicle_profile_preserves_btx_vegetative_source(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.COMPACT_PANICLE_FIELD_PROFILE)
        compact = profile["panicle_presentation"]
        standard = TIMELAPSE.PANICLE_PRESENTATION
        self.assertEqual(1, len(set(profile["descriptor_paths"].values())))
        self.assertLess(compact["rachis_length_m"], standard["rachis_length_m"])
        self.assertLess(compact["branch_length_m"], standard["branch_length_m"])
        self.assertGreater(
            compact["primary_branch_count"] * compact["spikelet_pairs_per_branch"],
            standard["primary_branch_count"]
            * standard["spikelet_pairs_per_branch"],
        )

    def test_btx_pawaga_is_an_explicit_reference_profile(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.REFERENCE_FIELD_PROFILE)
        self.assertEqual(("BTX", "Pawaga"), profile["labels"])
        self.assertEqual(
            "reference_demonstration_not_the_measured_abc_field", profile["ownership"]
        )
        self.assertTrue(profile["relabel_markers"])

    def test_multiple_full_lifetime_playback_scales_are_validated(self) -> None:
        self.assertEqual((12, 24, 48), TIMELAPSE.playback_rates("48,12,24,24"))
        with self.assertRaises(ValueError):
            TIMELAPSE.playback_rates("0,24")

    def test_final_panicle_emergence_requires_all_sixty_plants(self) -> None:
        complete = {
            genotype: {"plants": 20, "panicle_emerged_plants": 20}
            for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
        }
        TIMELAPSE.validate_full_panicle_emergence(complete)
        complete["GenotypeC"]["panicle_emerged_plants"] = 19
        with self.assertRaisesRegex(RuntimeError, "59/60"):
            TIMELAPSE.validate_full_panicle_emergence(complete)

    def test_maturity_floor_adds_the_largest_sampled_organ_delay(self) -> None:
        records = [
            SimpleNamespace(
                vegetative_maturity_gdd=240.0,
                panicle_initiation_gdd=1.0,
                panicle_maturity_gdd=260.0,
            ),
            SimpleNamespace(
                vegetative_maturity_gdd=250.0,
                panicle_initiation_gdd=2.0,
                panicle_maturity_gdd=255.0,
            ),
        ]
        endpoint, delay = TIMELAPSE.maturity_floor_gdd(660.0, records)
        self.assertEqual(921.0, endpoint)
        self.assertEqual(261.0, delay)

    def test_final_organ_maturity_requires_all_sixty_plants(self) -> None:
        complete = {
            genotype: {
                "plants": 20,
                "panicle_emerged_plants": 20,
                "vegetative_mature_plants": 20,
                "panicle_mature_plants": 20,
                "all_organs_mature_plants": 20,
            }
            for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
        }
        TIMELAPSE.validate_full_organ_maturity(complete)
        complete["GenotypeC"]["panicle_mature_plants"] = 19
        with self.assertRaisesRegex(RuntimeError, "panicle 59/60"):
            TIMELAPSE.validate_full_organ_maturity(complete)

    def test_final_panicle_visibility_requires_every_group_to_clear_canopy(self) -> None:
        summary = {
            genotype: {"minimum_panicle_canopy_clearance_m": 0.12}
            for genotype in ("GenotypeA", "GenotypeB", "GenotypeC")
        }
        TIMELAPSE.validate_full_panicle_visibility(summary)
        summary["GenotypeC"]["minimum_panicle_canopy_clearance_m"] = 0.04
        with self.assertRaisesRegex(RuntimeError, "GenotypeC"):
            TIMELAPSE.validate_full_panicle_visibility(summary)

    def test_pre_emergence_field_allows_records_without_geometry(self) -> None:
        profile = TIMELAPSE.field_profile(TIMELAPSE.DEFAULT_FIELD_PROFILE)
        records = []
        for row_index, cultivar in enumerate(profile["row_labels"]):
            for column_index in range(10):
                records.append(
                    SimpleNamespace(
                        cultivar=cultivar,
                        evaluation_gdd=0.66,
                        has_geometry=False,
                        name=(f"{cultivar}_LSystem_R{row_index}_C{column_index}"),
                    )
                )

        TIMELAPSE.validate_field(records, 0.66, profile)
        with self.assertRaisesRegex(RuntimeError, "rendered geometry"):
            TIMELAPSE.validate_field(records, 0.66, profile, require_geometry=True)

    def test_runtime_asset_restoration_reverts_engine_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "Assets"
            metadata = assets / "Descriptors" / "source.evefoldermeta"
            project = root / "test.eveproj"
            existing_side_effect = assets / "New Scene.evescene"
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"metadata\n")
            project.write_bytes(b"project\r\n")
            existing_side_effect.write_bytes(b"keep\n")
            snapshot = TIMELAPSE.runtime_asset_snapshot(root, project)

            metadata.unlink()
            project.write_bytes(b"project\n")
            new_side_effect = assets / "New Scene 1.evescene"
            new_side_effect.write_bytes(b"remove\n")
            TIMELAPSE.restore_runtime_assets(snapshot, root, {existing_side_effect})

            self.assertEqual(b"metadata\n", metadata.read_bytes())
            self.assertEqual(b"project\r\n", project.read_bytes())
            self.assertTrue(existing_side_effect.is_file())
            self.assertFalse(new_side_effect.exists())

    def test_worker_flag_is_internal_and_defaults_off(self) -> None:
        args = TIMELAPSE.build_parser().parse_args([])
        self.assertFalse(args.worker)


if __name__ == "__main__":
    unittest.main()
