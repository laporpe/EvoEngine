from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import sorghum_4x10_illumination_video as video


class CampaignVideoTest(unittest.TestCase):
    def test_fixed_camera_accepts_remaining_generated_plants(self) -> None:
        def point(x: float, y: float, z: float) -> SimpleNamespace:
            return SimpleNamespace(x=x, y=y, z=z)

        evo = SimpleNamespace(
            GetSorghumLsPlantSceneMetadata=lambda _geometry: [
                SimpleNamespace(
                    has_geometry=True,
                    geometry_min_position=point(-1.0, 0.0, -2.0),
                    geometry_max_position=point(1.0, 2.0, 2.0),
                )
            ]
        )

        camera = video._camera_from_scene(evo, video.DEFAULT_SPEC)

        self.assertEqual(
            video.camera_for_style(
                video.DEFAULT_PROFILE.camera_style,
                video.DEFAULT_SPEC.width,
                video.DEFAULT_SPEC.scene_height,
            ),
            camera,
        )

    def test_one_hundred_realizations_receive_three_frames_each(self) -> None:
        allocations = video.frame_allocations(100)

        self.assertEqual([3] * 100, allocations)
        self.assertEqual(300, sum(allocations))

    def test_running_means_follow_the_visible_three_by_two_panel_order(self) -> None:
        accumulators = {}
        for panel, key in enumerate(video.PANEL_ORDER):
            for probe in range(2):
                accumulators[(*key, probe)] = SimpleNamespace(
                    stats={
                        "illumination_total_simulated": SimpleNamespace(
                            mean=panel * 10 + probe
                        )
                    }
                )

        self.assertEqual(
            [0.0, 1.0, 10.0, 11.0, 20.0, 21.0, 30.0, 31.0, 40.0, 41.0, 50.0, 51.0],
            video.running_means(accumulators, 2),
        )

    def test_composition_preserves_scene_pixels_and_exact_upper_fraction(self) -> None:
        spec = video.VideoSpec(width=640, height=360, fps=6, seconds_per_date=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene = root / "scene.png"
            output = root / "frame.png"
            Image.new("RGB", (spec.width, spec.scene_height), (13, 71, 129)).save(scene)

            video.compose_frame(
                scene, output, "2021-07-01", 1, 2, 2, None, 0.0, 1.0, spec
            )

            with Image.open(output) as frame:
                self.assertEqual((spec.width, spec.height), frame.size)
                self.assertEqual(
                    (13, 71, 129), frame.getpixel((10, spec.scene_height - 1))
                )
                self.assertNotEqual(
                    (13, 71, 129), frame.getpixel((10, spec.scene_height))
                )

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is unavailable"
    )
    def test_assembly_encodes_the_exact_frame_count_and_manifest(self) -> None:
        spec = video.VideoSpec(width=640, height=450, fps=6, seconds_per_date=1)
        date = "2021-07-01"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            staging = root / "staging"
            for replicate in (1, 2):
                scene = staging / date / "scenes" / f"{replicate:04d}.png"
                means = staging / date / "means" / f"{replicate:04d}.json"
                scene.parent.mkdir(parents=True, exist_ok=True)
                means.parent.mkdir(parents=True, exist_ok=True)
                Image.new(
                    "RGB",
                    (spec.width, spec.scene_height),
                    (20 * replicate, 80, 120),
                ).save(scene)
                means.write_text(
                    json.dumps(
                        {
                            "date": date,
                            "replicate_number": replicate,
                            "probes_per_panel": 2,
                            "render_samples": 2,
                            "render_bounces": 2,
                            "illumination_running_means": [
                                replicate + probe / 10.0 for probe in range(12)
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
            sensor_rows = [
                {"illumination_total_simulated_mean": 1.0 + probe / 10.0}
                for probe in range(12)
            ]

            video_path, manifest_path = video.assemble_video(
                output, staging, [date], 2, 2, sensor_rows, 2, 2, spec
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(video_path.is_file())
            self.assertEqual(6, manifest["frame_count"])
            self.assertEqual(1, manifest["duration_seconds"])
            self.assertEqual({"samples": 2, "bounces": 2}, manifest["camera_render"])
            self.assertFalse(staging.exists())
            opening = root / "opening.png"
            subprocess.run(
                [
                    shutil.which("ffmpeg"),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    str(opening),
                ],
                check=True,
            )
            with Image.open(opening) as frame:
                self.assertLess(max(frame.getpixel((50, 405))), 20)


if __name__ == "__main__":
    unittest.main()
