from __future__ import annotations

import csv
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sorghum_4x10_saved_scene as saved


def vector(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y, z=z)


def plant(index: int) -> SimpleNamespace:
    cultivar = "BTX" if index < 20 else "Pawaga"
    return SimpleNamespace(
        name=f"{cultivar}_LSystem_{index}",
        cultivar=cultivar,
        descriptor_asset_path="GeneratedAssets/Descriptors/GrowthStage03/BTX.sorghumls",
        descriptor_version=1,
        seed=2_000_000 + index,
        evaluation_gdd=725.0,
        local_position=vector(index, 0, 0),
        global_position=vector(index, 0, 0),
        geometry_min_position=vector(index, 0, 0),
        geometry_max_position=vector(index + 1, 2, 1),
        plant_height_m=2.0,
        leaf_area_m2=1.0,
        leaf_count=2,
        main_culm_leaf_count=2,
        tiller_leaf_count=0,
        primary_tiller_count=0,
        leaf_width_scale=1.0,
        leaf_thickness_m=0.001,
        middle_parbar_top_elevation_m=1.3,
        geometry_snapshot_schema_version=1,
        geometry_snapshot_version=1,
        geometry_snapshot_organ_count=3,
        leaf_vertex_count=12,
        leaf_triangle_count=8,
        culm_vertex_count=6,
        culm_triangle_count=4,
        has_geometry=True,
        axes=[SimpleNamespace(axis_id=0, leaf_count=2)],
    )


def probes(per_panel: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            cultivar=cultivar,
            model="PARBAR",
            sensor_bar_level=level,
            column=column,
            height_rule="fixed" if level != "middle" else "two_thirds_height",
            position=vector(column, 1, 0),
            normal=vector(0, 1, 0),
            energy=vector(1, 2, 3),
            direction=vector(0, -1, 0),
            scalar=6.0,
            normalized=0.5,
            represented_plant_count=10,
            average_represented_root_elevation_m=0.0,
            average_represented_plant_height_m=2.0,
            sensor_top_elevation_m=1.3,
            height_fraction_of_average_height=2.0 / 3.0,
        )
        for cultivar in ("BTX", "Pawaga")
        for level in ("top", "middle", "bottom")
        for column in range(per_panel)
    ]


class SavedSceneAnalysisTest(unittest.TestCase):
    def test_loaded_scene_restores_engine_metadata_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "CMakeLists.txt").write_text("project(test)", encoding="utf-8")
            project = root / "field.eveproj"
            project.write_text("project", encoding="utf-8")
            assets = root / "Assets"
            scene = Path("Frozen.evescene")
            (assets / scene).parent.mkdir(parents=True)
            (assets / scene).write_text("scene", encoding="utf-8")
            metadata = assets / "Materials.evefoldermeta"
            metadata.write_text("metadata", encoding="utf-8")
            evo = mock.Mock()
            evo.RunLSystemSorghumProject.return_value = True
            evo.WaitForProjectIdle.return_value = True
            evo.ValidateIlluminationContext.return_value = True

            with (
                mock.patch.object(saved, "_ENGINE_SESSION_USED", False),
                mock.patch.object(saved.importlib, "import_module", return_value=evo),
            ):
                with saved._loaded_scene(
                    project, scene, None, None, "RelWithDebInfo", 10
                ):
                    project.write_text("changed", encoding="utf-8")
                    metadata.unlink()
                    (assets / "New Scene.evescene").write_text(
                        "side effect", encoding="utf-8"
                    )
                with self.assertRaisesRegex(RuntimeError, "fresh Python process"):
                    with saved._loaded_scene(
                        project, scene, None, None, "RelWithDebInfo", 10
                    ):
                        pass

            self.assertEqual("project", project.read_text(encoding="utf-8"))
            self.assertEqual("metadata", metadata.read_text(encoding="utf-8"))
            self.assertFalse((assets / "New Scene.evescene").exists())
            evo.Terminate.assert_called_once()

    def test_analysis_materializes_saved_state_and_writes_raw_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "field.eveproj"
            project.write_text("project", encoding="utf-8")
            scene = Path("GeneratedAssets/Scenes/Frozen.evescene")
            scene_file = root / "Assets" / scene
            scene_file.parent.mkdir(parents=True)
            scene_file.write_text("scene", encoding="utf-8")
            descriptor = (
                root / "Assets/GeneratedAssets/Descriptors/GrowthStage03/BTX.sorghumls"
            )
            descriptor.parent.mkdir(parents=True)
            descriptor.write_text("descriptor", encoding="utf-8")
            output = root / "output"

            evo = mock.Mock()
            evo.GetSorghumLsPlantSceneMetadata.return_value = [
                plant(index) for index in (0, 1, 20)
            ]
            evo.MaterializeSorghumLsPlantGeometry.return_value = 3
            evo.WaitForProjectIdle.return_value = True
            evo.CreateParbarTopFaceSensorGroup.return_value = "sensors"
            evo.GetParbarTopFaceSensorResults.return_value = probes(2)

            def capture(_width, _height, path, *_settings):
                Path(path).write_bytes(b"png")
                return True

            evo.CaptureCurrentSceneRayTraced.side_effect = capture

            @contextmanager
            def loaded(*_args, **_kwargs):
                yield evo

            with (
                mock.patch.object(saved, "_loaded_scene", loaded),
                mock.patch.object(
                    saved,
                    "_apply_capture_camera",
                    return_value={"position": [0, 1, 2]},
                ),
                self.assertWarns(UserWarning),
            ):
                result = saved.analyze_saved_4x10_scene(
                    project=project,
                    scene=scene,
                    output_dir=output,
                    probes_per_panel=2,
                    illumination_samples=4,
                    render_samples=4,
                )

            self.assertTrue(result.render.is_file())
            self.assertTrue(result.manifest.is_file())
            with result.parbar_probes_csv.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(12, len(list(csv.DictReader(stream))))
            with result.plants_csv.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(3, len(list(csv.DictReader(stream))))
            evo.GrowSorghumLsPlantsToGdd.assert_not_called()
            evo.GrowSorghumLsPlantsToAdulthood.assert_not_called()
            evo.SetSorghumLsCultivarDescriptors.assert_not_called()
            evo.MaterializeSorghumLsPlantGeometry.assert_called_once_with(False)
            evo.EstimatePARSensors.assert_called_once_with("sensors", 4, 4, 0.001, 0)
            evo.DeleteRuntimeAsset.assert_called_once_with("sensors")


if __name__ == "__main__":
    unittest.main()
