from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sorghum_4x10_scene as scenes
from sorghum_asset_layout import (
    DATE_ORDER,
    DEFAULT_PROJECT_ASSETS,
    GENERATED_DESCRIPTOR_ROOT,
    GENERATED_REPORT_ROOT,
)


MANIFEST = DEFAULT_PROJECT_ASSETS / GENERATED_REPORT_ROOT / "field_manifest.csv"


class SceneQueryTest(unittest.TestCase):
    def test_resolves_current_published_scene(self) -> None:
        scene = scenes.query_4x10_scene(
            MANIFEST, GENERATED_DESCRIPTOR_ROOT, DATE_ORDER[3]
        )

        self.assertEqual(
            "GeneratedAssets/Scenes/Sorghum_4x10_GrowthStage04.evescene",
            scene.scene_asset_path,
        )
        self.assertEqual(
            Path("GeneratedAssets/Descriptors/GrowthStage04/BTX.sorghumls"),
            scene.btx_descriptor,
        )
        self.assertEqual(40, scene.plant_count)
        self.assertEqual("EvoEngine Y-up", scene.coordinate_system)

    def test_version_policy_rejects_major_and_warns_on_newer_minor(self) -> None:
        with self.assertRaises(RuntimeError):
            scenes.check_compatibility((2, 0))
        with self.assertWarns(UserWarning):
            scenes.check_compatibility((1, 1))


class ScenePreparationTest(unittest.TestCase):
    def test_prepares_scene_without_creating_or_estimating_probes(self) -> None:
        scene = scenes.query_4x10_scene(
            MANIFEST, GENERATED_DESCRIPTOR_ROOT, DATE_ORDER[0]
        )
        evo = mock.Mock()
        evo.RunLSystemSorghumProject.return_value = True
        evo.WaitForProjectIdle.return_value = True
        evo.EnsureIlluminationSoilContext.return_value = True
        evo.ValidateIlluminationContext.return_value = True
        evo.SetSorghumLsCultivarDescriptors.return_value = 40
        evo.SetSorghumLsLeafThickness.return_value = 40
        evo.SetSorghumLsLeafWidthScale.return_value = 40
        evo.GrowSorghumLsPlantsToAdulthood.return_value = 40
        evo.MoveParbarMiddlePanelsToPlantHeightFraction.return_value = 2

        scenes.prepare_4x10_scene(
            evo,
            Path("field.eveproj"),
            Path("Packages"),
            scene,
            2_000_000,
            2.0 / 3.0,
            2,
            30000,
        )

        evo.GrowSorghumLsPlantsToAdulthood.assert_called_once_with(2_000_000, "", True, False)
        evo.MoveParbarMiddlePanelsToPlantHeightFraction.assert_called_once_with(
            2.0 / 3.0
        )
        self.assertFalse(evo.CreateParbarTopFaceSensorGroup.called)
        self.assertFalse(evo.EstimatePARSensors.called)

    def test_grows_one_requested_morphology_realization(self) -> None:
        scene = scenes.query_4x10_scene(
            MANIFEST, GENERATED_DESCRIPTOR_ROOT, DATE_ORDER[0]
        )
        evo = mock.Mock()
        evo.GrowSorghumLsPlantsToAdulthood.return_value = 40
        evo.WaitForProjectIdle.return_value = True

        scenes.grow_4x10_scene(evo, scene, 2_005_000, 30000)

        evo.GrowSorghumLsPlantsToAdulthood.assert_called_once_with(2_005_000, "", True, False)
        evo.LoopFrames.assert_called_once_with(1)


class OrganIdTest(unittest.TestCase):
    def test_builds_stable_culm_tiller_and_leaf_ids(self) -> None:
        records = [
            SimpleNamespace(
                name="BTX_LSystem_0",
                axes=[
                    SimpleNamespace(axis_id=0, leaf_count=2),
                    SimpleNamespace(axis_id=3, leaf_count=1),
                ],
            )
        ]

        ids = scenes.plant_organ_ids(records)[0]

        self.assertEqual("BTX_LSystem_0/culm/0", ids.main_culm_id)
        self.assertEqual(("BTX_LSystem_0/tiller/3",), ids.tiller_ids)
        self.assertEqual(
            (
                "BTX_LSystem_0/axis/0/leaf/1",
                "BTX_LSystem_0/axis/0/leaf/2",
                "BTX_LSystem_0/axis/3/leaf/1",
            ),
            ids.leaf_ids,
        )


if __name__ == "__main__":
    unittest.main()
