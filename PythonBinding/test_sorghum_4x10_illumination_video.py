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
import sorghum_recompose_4x10_solar_video as recompose


class CampaignVideoTest(unittest.TestCase):
    def test_recomposition_final_values_follow_visible_panel_order(self) -> None:
        rows = []
        for panel, (cultivar, level) in enumerate(video.PANEL_ORDER):
            for probe in range(1, 3):
                rows.append(
                    {
                        "date": "2021-07-01",
                        "cultivar": cultivar,
                        "sensor_bar_level": level,
                        "probe_number": str(probe),
                        "illumination_total_simulated_mean": str(panel * 10 + probe),
                    }
                )
        rows.reverse()

        self.assertEqual(
            [1.0, 2.0, 11.0, 12.0, 21.0, 22.0, 31.0, 32.0, 41.0, 42.0, 51.0, 52.0],
            recompose.final_values(rows, "2021-07-01", 2),
        )

    def test_arizona_solar_sweep_has_sunrise_noon_and_sunset(self) -> None:
        peak_elevations = []
        for date in ("2021-07-01", "2021-08-18", "2021-09-02"):
            frames = video.solar_sweep_for_date(date, 100)
            peak_elevations.append(max(frame.elevation_degrees for frame in frames))
            self.assertEqual(100, len(frames))
            self.assertAlmostEqual(-0.833, frames[0].elevation_degrees, places=3)
            self.assertAlmostEqual(-0.833, frames[-1].elevation_degrees, places=3)
            self.assertTrue(
                all(
                    earlier.local_minutes < later.local_minutes
                    for earlier, later in zip(frames, frames[1:])
                )
            )
            self.assertLess(frames[0].azimuth_degrees, 120.0)
            self.assertGreater(frames[-1].azimuth_degrees, 240.0)
            self.assertLess(
                abs(
                    (frames[49].azimuth_degrees + frames[50].azimuth_degrees)
                    * 0.5
                    - 180.0
                ),
                0.1,
            )
        self.assertGreater(peak_elevations[0], peak_elevations[1])
        self.assertGreater(peak_elevations[1], peak_elevations[2])

    def test_solar_capture_restores_reference_scientific_sun(self) -> None:
        class Vector:
            x = 0.0
            y = 0.0
            z = 0.0

        class Evo:
            Vec3 = Vector

            def __init__(self) -> None:
                self.sun_angles = []

            def SetSunDirection(self, value) -> None:
                self.sun_angles.append((value.x, value.y, value.z))

            def LoopFrames(self, _count: int) -> None:
                pass

            def CaptureCurrentSceneRayTraced(
                self, width, height, output, _samples, _bounces, _gamma
            ) -> bool:
                Image.new("RGB", (width, height), (40, 90, 130)).save(output)
                return True

        spec = video.VideoSpec(width=64, height=80, fps=20, seconds_per_date=5)
        solar = video.solar_frame_for_replicate("2021-08-18", 50, 100)
        with tempfile.TemporaryDirectory() as directory:
            evo = Evo()
            root = Path(directory)
            video.capture_realization(
                evo,
                root,
                "2021-08-18",
                50,
                [1.0] * len(video.PANEL_ORDER),
                1,
                1,
                0,
                spec,
                solar,
            )
            payload = json.loads(
                (root / "2021-08-18" / "means" / "0050.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(solar.sun_angles_degrees, evo.sun_angles[0])
        self.assertEqual(video.REFERENCE_SUN_ANGLES_DEGREES, evo.sun_angles[-1])
        self.assertEqual(solar.to_dict(), payload["solar_sweep"])

    def test_partial_resume_validates_against_full_solar_schedule(self) -> None:
        date = "2021-07-01"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for replicate in (1, 2):
                scene = root / date / "scenes" / f"{replicate:04d}.png"
                means = root / date / "means" / f"{replicate:04d}.json"
                scene.parent.mkdir(parents=True, exist_ok=True)
                means.parent.mkdir(parents=True, exist_ok=True)
                scene.touch()
                means.write_text(
                    json.dumps(
                        {
                            "date": date,
                            "replicate_number": replicate,
                            "probes_per_panel": 1,
                            "illumination_running_means": [1.0]
                            * len(video.PANEL_ORDER),
                            "solar_sweep": video.solar_frame_for_replicate(
                                date, replicate, 100
                            ).to_dict(),
                        }
                    ),
                    encoding="utf-8",
                )

            video.validate_staged_prefix(root, date, 2, 1, True, 100)

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
