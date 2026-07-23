from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageStat

import sorghum_4x10_presentation as presentation


class PresentationCameraTest(unittest.TestCase):
    def test_fixed_camera_is_independent_of_growth_date(self) -> None:
        first = presentation.camera_for_style("field_perspective", 1920, 864)
        second = presentation.camera_for_style("field_perspective", 1920, 864)

        self.assertEqual(first, second)
        self.assertEqual("field_perspective", first["style"])
        self.assertLess(first["fov_degrees"], 50.0)

    def test_near_top_down_has_a_higher_camera_than_perspective(self) -> None:
        perspective = presentation.camera_for_style("field_perspective", 1920, 864)
        overhead = presentation.camera_for_style("near_top_down", 1920, 864)

        self.assertGreater(overhead["position"][1], perspective["position"][1])


class PresentationGradeTest(unittest.TestCase):
    def test_grade_is_deterministic_and_conservative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            first = root / "first.png"
            second = root / "second.png"
            Image.new("RGB", (32, 24), (220, 180, 130)).save(source)

            presentation.apply_photo_grade(source, first)
            presentation.apply_photo_grade(source, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with Image.open(source) as before, Image.open(first) as after:
                self.assertEqual(before.size, after.size)
                before_mean = ImageStat.Stat(before).mean
                after_mean = ImageStat.Stat(after).mean
                self.assertLess(sum(after_mean), sum(before_mean))
                self.assertLess(abs(after_mean[1] - before_mean[1]), 20.0)


class LeafPresentationTest(unittest.TestCase):
    def test_missing_optional_engine_api_is_a_no_op(self) -> None:
        self.assertEqual(0, presentation.set_ground_extension(SimpleNamespace(), True))


if __name__ == "__main__":
    unittest.main()
