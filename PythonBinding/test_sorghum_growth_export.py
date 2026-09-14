import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from sorghum_growth_export import (
    GrowthGeometryExporter,
    aligned_triangles,
    validate_manifest,
    validate_mesh,
)


class SnapshotValidationTest(unittest.TestCase):
    def mesh(self, count=3):
        return {
            "positions": np.zeros((count, 3), np.float32),
            "normals": np.zeros((count, 3), np.float32),
            "uv": np.zeros((count, 2), np.float32),
            "colors": np.ones((count, 4), np.float32),
            "triangles": np.array([[0, 1, 2]], np.uint32)
            if count
            else np.empty((0, 3), np.uint32),
        }

    def test_empty_organ_and_live_mesh(self):
        validate_mesh(self.mesh(0))
        validate_mesh(self.mesh())

    def test_rejects_out_of_range_and_negative_indices(self):
        for indices in ([[0, 1, 3]], [[-1, 1, 2]]):
            mesh = self.mesh()
            mesh["triangles"] = np.array(indices, np.int32)
            with self.assertRaises(ValueError):
                validate_mesh(mesh)

    def test_rejects_nonfinite_geometry(self):
        for key in ("positions", "normals", "uv", "colors"):
            mesh = self.mesh()
            mesh[key][0, 0] = np.nan
            with self.assertRaises(ValueError):
                validate_mesh(mesh)

    def test_rejects_mismatched_attribute_count(self):
        mesh = self.mesh()
        mesh["uv"] = np.zeros((2, 2), np.float32)
        with self.assertRaises(ValueError):
            validate_mesh(mesh)

    def test_winding_preserves_vertices_and_source_indices(self):
        positions = np.array([[0, 0, 0], [0, 1, 0], [0, 1, 1]], np.float32)
        normals = np.tile([1, 0, 0], (3, 1))
        triangles = np.array([[0, 2, 1], [0, 1, 2]], np.uint32)
        np.testing.assert_array_equal(
            aligned_triangles(positions, normals, triangles), [[0, 1, 2], [0, 1, 2]]
        )
        np.testing.assert_array_equal(triangles, [[0, 2, 1], [0, 1, 2]])
        self.assertEqual(
            aligned_triangles(positions[:0], normals[:0], triangles[:0]).shape, (0, 3)
        )


class CaptureTest(unittest.TestCase):
    mesh = SnapshotValidationTest.mesh

    def test_example_rejects_unsafe_numeric_inputs_before_loading_engine(self):
        script = Path(__file__).with_name("export_sorghum_growth.py")
        for arguments in (
            ("--end-gdd", "inf"),
            ("--spacing", "nan"),
            ("--vertical-step", "0.0001"),
        ):
            result = subprocess.run(
                [sys.executable, str(script), *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("error:", result.stderr)

    def plant(self, handle=42, empty=False):
        mesh = self.mesh(0 if empty else 3)
        if not empty:
            mesh["positions"] = np.array([[0, 0, 0], [0, 1, 0], [0, 1, 1]], np.float32)
        return {
            "name": "My cultivar",
            "entity_handle": handle,
            "genotype": "Custom cultivar",
            "seed": 5,
            "world_transform": np.eye(4, dtype=np.float32),
            "requested_gdd": 100.0,
            "evaluated_gdd": 100.0,
            "geometry_version": 1,
            "organ_ranges": [],
            "culm": mesh,
            "leaves": self.mesh(0),
            "panicle": self.mesh(0),
        }

    def test_custom_roster_empty_organs_and_one_frame_export(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = GrowthGeometryExporter(directory)
            exporter.write_frame([self.plant(42), self.plant(8)], 100)
            manifest = json.loads(exporter.finish().read_text())
            validate_manifest(manifest)
            self.assertEqual([p["entity_handle"] for p in manifest["plants"]], [8, 42])
            with np.load(Path(directory) / manifest["frames"][0]["file"]) as data:
                np.testing.assert_array_equal(
                    data["plant_000/culm/positions"], self.plant()["culm"]["positions"]
                )
            with self.assertRaises(FileExistsError):
                GrowthGeometryExporter(directory)
            with self.assertRaises(RuntimeError):
                exporter.capture(None, 200)

    def test_rejects_invalid_schedule_and_changing_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = GrowthGeometryExporter(directory)
            for gdd in (float("nan"), float("inf"), -1):
                with self.assertRaises(ValueError):
                    exporter.write_frame([self.plant()], gdd)
            exporter.write_frame([self.plant()], 100)
            for plants, gdd in (
                ([self.plant()], 90),
                ([self.plant(7)], 200),
                ([], 200),
            ):
                with self.assertRaises(ValueError):
                    exporter.write_frame(plants, gdd)
            exporter.write_frame([self.plant()], 100)
            self.assertEqual(
                len(json.loads(exporter.finish().read_text())["frames"]), 2
            )

    def test_detects_borrowed_buffer_mutation_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = GrowthGeometryExporter(directory)
            plant = self.plant()
            exporter.write_frame([plant], 100)
            plant["culm"]["positions"][0, 0] = 9
            with self.assertRaises(RuntimeError):
                exporter.write_frame([self.plant()], 200)
            self.assertFalse((Path(directory) / "manifest.json").exists())

    def test_empty_recording_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = GrowthGeometryExporter(directory)
            exporter.write_frame([self.plant(empty=True)], 0)
            with self.assertRaises(RuntimeError):
                exporter.finish()

    def test_rejected_frame_can_be_corrected_and_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = GrowthGeometryExporter(directory)
            first, second = self.plant(1), self.plant(2)
            second["culm"]["uv"] = np.zeros((2, 2), np.float32)
            with self.assertRaises(ValueError):
                exporter.write_frame([first, second], 100)
            first["culm"]["positions"][0, 0] = 0.5
            exporter.write_frame([first, self.plant(2)], 100)
            self.assertEqual(
                len(json.loads(exporter.finish().read_text())["frames"]), 1
            )


if __name__ == "__main__":
    unittest.main()
