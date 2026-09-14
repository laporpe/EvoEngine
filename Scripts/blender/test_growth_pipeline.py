"""Small end-to-end regressions; set BLENDER_EXECUTABLE and run with normal Python.

Requires NumPy, Pillow, imageio-ffmpeg and Blender with pxr. No engine build or
project assets required. All generated fixtures live in a temporary directory.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "PythonBinding"))
from sorghum_growth_export import GrowthGeometryExporter

BLENDER = os.environ.get("BLENDER_EXECUTABLE") or shutil.which("blender")
BUILDER = ROOT / "Scripts/blender/build_sorghum_growth_cache.py"
ENCODER = ROOT / "Scripts/blender/encode_sorghum_growth.py"


def run(command, success=True):
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=180, check=False
    )
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


@unittest.skipUnless(BLENDER, "Set BLENDER_EXECUTABLE to run Blender integration tests")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.export = cls.root / "export"
        writer = GrowthGeometryExporter(cls.export)
        writer.manifest["synthetic_only"] = True
        for frame in range(1, 6):
            plants = []
            for i in range(2):
                world = np.eye(4, dtype=np.float32)
                world[2, 3] = i * 2.2
                world[1, 1] = 1.2
                plant = {
                    "name": f"Test {i}",
                    "genotype": f"Custom {i}",
                    "seed": i,
                    "entity_handle": i + 1,
                    "world_transform": world,
                    "requested_gdd": frame * 100,
                    "evaluated_gdd": frame * 100,
                    "geometry_version": frame,
                    "organ_ranges": [],
                }
                for part in ("culm", "leaves", "panicle"):
                    points = [[0, 0, 0], [0, frame * 0.3, 0], [0, frame * 0.3, 0.4]]
                    indices = [
                        [0, 2, 1]
                    ]  # Deliberately inward, as in the native culm snapshot.
                    if frame > 2:
                        points.append([0, 0, 0.4])
                        indices.append([0, 3, 2])
                    if frame == 1 or (
                        part == "panicle" and (i == 0 or frame in (2, 4))
                    ):
                        points, indices = [], []
                    count = len(points)
                    plant[part] = {
                        "positions": np.array(points, np.float32).reshape(-1, 3),
                        "triangles": np.array(indices, np.uint32).reshape(-1, 3),
                        "normals": np.tile(np.array([1, 0, 0], np.float32), (count, 1)),
                        "uv": np.full((count, 2), frame * 0.1, np.float32),
                        "colors": np.tile(
                            np.array([0.1, frame * 0.15, 0.03, 1], np.float32),
                            (count, 1),
                        ),
                    }
                plants.append(plant)
            writer.write_frame(plants, frame * 100)
        cls.manifest = writer.finish()
        cls.output = cls.export / "blender"
        atlas = cls.root / "atlas"
        atlas.mkdir()
        Image.new("RGBA", (4, 4), (100, 180, 60, 255)).save(
            atlas / "sorghum_lsystem_leaf_variants_albedo.png"
        )
        cls.command = [
            BLENDER,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(BUILDER),
            "--",
            "--validate-all",
            "--manifest",
            str(cls.manifest),
        ]
        run(
            cls.command
            + [
                "--leaf-atlas",
                str(atlas),
                "--width",
                "320",
                "--height",
                "180",
                "--samples",
                "4",
                "--render",
            ]
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_geometry_and_fractional_hold(self):
        report = json.loads((self.output / "validation.json").read_text())
        self.assertTrue(report["passed"])
        self.assertFalse(report["native_geometry"])
        self.assertEqual(len(report["samples_checked"]), 30)
        shutil.copy2(
            self.output / "renders/growth_0005.png",
            self.output / "renders/growth_0006.png",
        )
        run(
            [
                sys.executable,
                str(ENCODER),
                "--manifest",
                str(self.manifest),
                "--hold-seconds",
                "0.1875",
            ]
        )
        report = json.loads((self.output / "render_report.json").read_text())
        self.assertEqual(report["frames"], 9)

    def test_invalid_frame_range(self):
        result = run(
            self.command + ["--reuse-scene", "--render", "--frame-start", "0"], False
        )
        self.assertIn("Render range must lie", result)

    def test_stale_manifest_and_encoding_are_rejected(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["frames"][2]["gdd"] += 1
        altered = self.export / "altered.json"
        altered.write_text(json.dumps(manifest))
        command = self.command.copy()
        command[-1] = str(altered)
        self.assertIn(
            "belongs to another export", run(command + ["--reuse-scene"], False)
        )
        self.assertIn(
            "another export/cache",
            run([sys.executable, str(ENCODER), "--manifest", str(altered)], False),
        )

    def test_texture_edits_require_a_new_render_directory(self):
        path = self.output / "textures/sorghum_lsystem_leaf_variants_albedo.png"
        original = path.read_bytes()
        try:
            Image.new("RGBA", (4, 4), (40, 90, 30, 255)).save(path)
            result = run(
                self.command
                + [
                    "--reuse-scene",
                    "--render",
                    "--frame-start",
                    "2",
                    "--frame-end",
                    "2",
                ],
                False,
            )
            self.assertIn("different export/presentation", result)
        finally:
            path.write_bytes(original)

    def test_tampered_snapshot_is_rejected_on_reuse(self):
        path = self.export / "frames/frame_0003.npz"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"tampered")
            self.assertIn(
                "Snapshot hash mismatch", run(self.command + ["--reuse-scene"], False)
            )
        finally:
            path.write_bytes(original)

    def test_beautified_scene_can_render_without_losing_edits(self):
        edited = self.output / "beautiful.blend"
        script = self.root / "beautify.py"
        script.write_text(
            "import bpy\n"
            f"bpy.ops.wm.open_mainfile(filepath={str(self.output / 'abc_growth.blend')!r})\n"
            "bpy.data.materials['Growth_leaves'].name='Colleague leaf material'\n"
            "bpy.context.scene.camera.location.z += .1\n"
            "bpy.context.scene.render.resolution_x=400\n"
            f"bpy.ops.wm.save_as_mainfile(filepath={str(edited)!r})\n"
        )
        run(
            [
                BLENDER,
                "--background",
                "--python-exit-code",
                "1",
                "--python",
                str(script),
            ]
        )
        command = self.command + [
            "--reuse-scene",
            "--scene",
            str(edited),
            "--render",
            "--frame-start",
            "2",
            "--frame-end",
            "2",
        ]
        self.assertIn("different export/presentation", run(command, False))
        frames = self.output / "beauty/renders"
        run(command + ["--render-output", str(frames)])
        with Image.open(frames / "growth_0002.png") as image:
            self.assertEqual(image.size, (400, 180))


if __name__ == "__main__":
    unittest.main()
