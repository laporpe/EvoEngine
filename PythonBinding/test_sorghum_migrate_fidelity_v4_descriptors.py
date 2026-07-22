from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from sorghum_migrate_fidelity_v4_descriptors import (
    LEAF_ROLL_DEVIATION_DEGREES,
    LEAF_MAX_LENGTH_M,
    LEAF_PROFILES,
    LEAF_WIDTH_RANK_PROFILE,
    LATERAL_AXIS_PLASTOCHRON_SCALE,
    MANUAL,
    MATURITY_GDD,
    BTX_TILLER_BRANCHING_SCALE,
    SECOND_HALF_BLADE_DROOP_SCALE,
    STAGES,
    TARGET_GDD_BY_STAGE,
    TILLER_AZIMUTH_JITTER_DEGREES,
    TILLER_SAME_SIDE_SPLAY_DEGREES,
    blade_droop_profile,
    migrate,
)


def field_block(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}:\n.*?(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)", text
    )
    if not match:
        raise AssertionError(f"missing field: {name}")
    return match.group(0)


class SorghumFidelityMigrationTest(unittest.TestCase):
    def test_stage_widths_follow_early_reference_and_mature_authored_values(
        self,
    ) -> None:
        self.assertEqual(STAGES["GrowthStage01"], (0.0120, 0.0800, 0.00030, 0.00015))
        self.assertEqual(
            STAGES["GrowthStage02"], (0.0135, 0.0950 * 1.25, 0.00035, 0.00020)
        )
        self.assertEqual(
            STAGES["GrowthStage03"], (0.0150, 0.1100 * 1.25, 0.00045, 0.00030)
        )
        self.assertEqual(STAGES["GrowthStage04"][1], 0.1260 * 1.25)
        self.assertEqual(STAGES["GrowthStage05"][1], 0.1260 * 1.25)
        self.assertEqual(max(value for _, value in LEAF_WIDTH_RANK_PROFILE), 1.0)
        self.assertGreater(LEAF_MAX_LENGTH_M["GrowthStage01"]["BTX"], 0.59)

    def test_migration_is_idempotent_and_materializes_leaf_mechanics(self) -> None:
        required = (
            "leaf_waviness_width_fraction",
            "leaf_waviness_wavelength_m",
            "leaf_centerline_waviness_fraction",
            "leaf_static_wind_deflection_fraction",
            "leaf_axial_twist_max_degrees",
            "leaf_axial_twist_frequency_ratio_min",
            "leaf_axial_twist_frequency_ratio_max",
            "leaf_gravity_droop_compliance",
            "leaf_gravity_droop_age_response",
            "leaf_flexural_stiffness_along_leaf",
            "leaf_damage_severity",
            "leaf_sheath_cross_section_ratio",
            "main_culm_lean_angle",
            "tiller_same_side_splay_angle",
        )
        with tempfile.TemporaryDirectory() as directory:
            for cultivar in LEAF_PROFILES:
                path = Path(directory) / f"{cultivar}.sorghumls"
                path.write_bytes((MANUAL / path.name).read_bytes())
                migrate(path, STAGES["GrowthStage01"])
                first = path.read_text(encoding="utf-8")
                migrate(path, STAGES["GrowthStage01"])
                self.assertEqual(path.read_text(encoding="utf-8"), first)
                for field in required:
                    self.assertEqual(len(re.findall(rf"(?m)^{field}:", first)), 1)
                self.assertIn(
                    "max_value: 0.08", field_block(first, "leaf_blade_max_width")
                )
                self.assertIn(
                    "- [0, 0.228]", field_block(first, "leaf_blade_max_width")
                )
                self.assertIn(
                    f"max_value: {LEAF_MAX_LENGTH_M['GrowthStage01'][cultivar]:.8g}",
                    field_block(first, "leaf_blade_length"),
                )
                self.assertIn(
                    "max_value: 0.0003", field_block(first, "leaf_blade_thickness")
                )
                self.assertIn(
                    "tangent_: false",
                    field_block(first, "leaf_gravity_droop_age_response"),
                )
                self.assertIn(
                    "mean: 0.02", field_block(first, "leaf_gravity_droop_compliance")
                )
                self.assertIn(
                    "mean: 0.008",
                    field_block(first, "leaf_centerline_waviness_fraction"),
                )
                self.assertIn(
                    "mean: 0.018",
                    field_block(first, "leaf_static_wind_deflection_fraction"),
                )
                self.assertIn(
                    "mean: 30", field_block(first, "leaf_axial_twist_max_degrees")
                )
                self.assertIn(
                    "mean: 0.35",
                    field_block(first, "leaf_axial_twist_frequency_ratio_min"),
                )
                self.assertIn(
                    "mean: 0.5",
                    field_block(first, "leaf_axial_twist_frequency_ratio_max"),
                )
                self.assertNotRegex(first, r"(?m)^leaf_static_twist_degrees:")
                self.assertIn(
                    "min_value: 0.02",
                    field_block(first, "leaf_flexural_stiffness_along_leaf"),
                )
                self.assertIn("mean: 0", field_block(first, "leaf_damage_severity"))
                self.assertIn(
                    "mean: 1.4", field_block(first, "leaf_sheath_cross_section_ratio")
                )
                self.assertIn("mean: 6.8", field_block(first, "main_culm_lean_angle"))
                self.assertIn(
                    f"mean: {TILLER_SAME_SIDE_SPLAY_DEGREES:.8g}",
                    field_block(first, "tiller_same_side_splay_angle"),
                )
                self.assertIn(
                    f"mean: {TARGET_GDD_BY_STAGE['GrowthStage01']:.8g}",
                    field_block(first, "target_gdd"),
                )
                self.assertIn(
                    f"mean: {MATURITY_GDD:.8g}", field_block(first, "maturity_gdd")
                )
                self.assertIn(
                    f"mean: {LATERAL_AXIS_PLASTOCHRON_SCALE:.8g}",
                    field_block(first, "lateral_axis_plastochron_scale"),
                )
                self.assertIn("finalize_snapshot_morphology: false", first)
                self.assertNotRegex(first, r"(?m)^- 1$")

    def test_migration_materializes_mechanics_missing_from_legacy_descriptor(
        self,
    ) -> None:
        required = (
            "leaf_waviness_width_fraction",
            "leaf_waviness_wavelength_m",
            "leaf_centerline_waviness_fraction",
            "leaf_static_wind_deflection_fraction",
            "leaf_axial_twist_max_degrees",
            "leaf_axial_twist_frequency_ratio_min",
            "leaf_axial_twist_frequency_ratio_max",
            "leaf_gravity_droop_compliance",
            "leaf_gravity_droop_age_response",
            "leaf_flexural_stiffness_along_leaf",
            "leaf_damage_severity",
            "leaf_sheath_cross_section_ratio",
            "main_culm_lean_angle",
            "tiller_same_side_splay_angle",
        )
        legacy_fields = required[:8] + ("tiller_same_side_splay_angle",)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BTX.sorghumls"
            legacy = (MANUAL / path.name).read_text(encoding="utf-8")
            for field in legacy_fields:
                if re.search(rf"(?m)^{field}:", legacy):
                    legacy = legacy.replace(field_block(legacy, field), "")
            path.write_text(legacy, encoding="utf-8")

            migrate(path, STAGES["GrowthStage01"])
            migrated = path.read_text(encoding="utf-8")

            for field in required:
                self.assertEqual(len(re.findall(rf"(?m)^{field}:", migrated)), 1)

    def test_cultivars_keep_distinct_rest_architecture_and_vertical_newest_leaf(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            migrated: dict[str, str] = {}
            for cultivar in LEAF_PROFILES:
                path = Path(directory) / f"{cultivar}.sorghumls"
                path.write_bytes((MANUAL / path.name).read_bytes())
                migrate(path, STAGES["GrowthStage05"])
                migrated[cultivar] = path.read_text(encoding="utf-8")

            self.assertIn(
                "max_value: 42", field_block(migrated["BTX"], "leaf_insertion_angle")
            )
            self.assertIn(
                "max_value: 70", field_block(migrated["Pawaga"], "leaf_insertion_angle")
            )
            self.assertIn(
                "max_value: 150", field_block(migrated["BTX"], "leaf_bending")
            )
            self.assertIn(
                "max_value: 100", field_block(migrated["Pawaga"], "leaf_bending")
            )
            self.assertIn(
                f"max_value: {LEAF_ROLL_DEVIATION_DEGREES:.8g}",
                field_block(migrated["BTX"], "leaf_roll_angle"),
            )
            self.assertIn(
                f"deviation: {TILLER_AZIMUTH_JITTER_DEGREES:.8g}",
                field_block(migrated["BTX"], "tiller_azimuth_jitter"),
            )
            self.assertIn(
                f"mean: {35.0 * BTX_TILLER_BRANCHING_SCALE:.8g}",
                field_block(migrated["BTX"], "tiller_insertion_angle"),
            )
            self.assertIn(
                "mean: 35",
                field_block(migrated["Pawaga"], "tiller_insertion_angle"),
            )
            for text in migrated.values():
                self.assertIn("- [1, 0]", field_block(text, "leaf_insertion_angle"))
                self.assertIn("- [1, 0]", field_block(text, "leaf_bending"))
            btx_bend_profile = field_block(migrated["BTX"], "bending_along_leaf")
            self.assertIn("- [0.5, 0.0225]", btx_bend_profile)
            self.assertIn("- [0.7, 0.27]", btx_bend_profile)
            self.assertIn("- [0.88, 0.9]", btx_bend_profile)
            pawaga_bend_profile = field_block(migrated["Pawaga"], "bending_along_leaf")
            self.assertIn("- [0.5, 0.039]", pawaga_bend_profile)
            self.assertIn("- [0.7, 0.3]", pawaga_bend_profile)
            self.assertIn("- [0.88, 0.93]", pawaga_bend_profile)
            for cultivar in LEAF_PROFILES:
                original = LEAF_PROFILES[cultivar]["bending_along"]
                updated = blade_droop_profile(cultivar)
                self.assertEqual(updated[:2], original[:2])
                self.assertEqual(
                    updated[2][1], original[2][1] * SECOND_HALF_BLADE_DROOP_SCALE
                )

    def test_posture_update_preserves_calibrated_growth_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BTX.sorghumls"
            path.write_bytes((MANUAL / path.name).read_bytes())
            migrate(path, STAGES["GrowthStage04"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("mean: 30", field_block(text, "plastochron_gdd"))
            self.assertIn("mean: 240", field_block(text, "maturity_gdd"))
            self.assertIn(
                "- [0.45, 0.05]", field_block(text, "leaf_bending_development_curve")
            )
            self.assertIn(
                "- [0.45, 0]", field_block(text, "leaf_gravity_droop_age_response")
            )

    def test_manual_descriptor_can_keep_legacy_snapshot_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BTX.sorghumls"
            path.write_bytes((MANUAL / path.name).read_bytes())
            migrate(
                path,
                (0.0210, 0.1260, 0.00050, 0.00040),
                "GrowthStage04",
                finalize_snapshot=True,
            )
            self.assertIn(
                "finalize_snapshot_morphology: true", path.read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
