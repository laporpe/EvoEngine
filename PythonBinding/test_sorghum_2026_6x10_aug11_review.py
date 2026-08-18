#!/usr/bin/env python3

from __future__ import annotations

import unittest
from dataclasses import dataclass

from sorghum_2026_6x10_aug11_review import EYE_HEIGHT_M, VIEW_NAMES, parse_marker, plan_cameras


@dataclass
class Vec3:
    x: float
    y: float
    z: float


@dataclass
class Record:
    name: str
    cultivar: str
    global_position: Vec3
    geometry_min_position: Vec3
    geometry_max_position: Vec3
    plant_height_m: float
    seed: int


def field_records() -> list[Record]:
    records = []
    for row, genotype in enumerate(("GenotypeA", "GenotypeA", "GenotypeB", "GenotypeB", "GenotypeC", "GenotypeC")):
        for column in range(10):
            x, y, z = column * 0.76 - 3.42, 0.01 * (row % 2), row * 0.76 - 1.90
            height = 1.3 + 0.35 * (row // 2) + 0.01 * column
            records.append(
                Record(
                    f"{genotype}_LSystem_R{row}_C{column}",
                    genotype,
                    Vec3(x, y, z),
                    Vec3(x - 0.24, y, z - 0.23),
                    Vec3(x + 0.24, y + height, z + 0.23),
                    height,
                    row * 10 + column,
                )
            )
    return records


class CameraPlanningTests(unittest.TestCase):
    def test_marker_parser(self) -> None:
        self.assertEqual(parse_marker(field_records()[23]), ("GenotypeB", 2, 3))

    def test_exactly_eighteen_unique_bbox_derived_views(self) -> None:
        records = field_records()
        cameras = plan_cameras(records, 1280, 720)
        self.assertEqual(tuple(cameras), VIEW_NAMES)
        self.assertEqual(len(set(cameras)), 18)
        self.assertTrue(all(camera["camera_to_nearest_plant_aabb_m"] >= 0.0 for camera in cameras.values()))

    def test_walking_cameras_use_real_world_eye_height_and_measured_aisles(self) -> None:
        records = field_records()
        cameras = plan_cameras(records, 1280, 720)
        for genotype, row_pair in (("a", (0, 1)), ("b", (2, 3)), ("c", (4, 5))):
            expected_z = sum((row * 0.76 - 1.90) for row in row_pair) / 2
            for direction in ("positive_x", "negative_x"):
                camera = cameras[f"genotype_{genotype}_inter_row_{direction}"]
                self.assertAlmostEqual(camera["position"][1], 0.005 + EYE_HEIGHT_M)
                self.assertAlmostEqual(camera["position"][2], expected_z)

    def test_intra_row_cameras_are_in_an_observed_root_gap(self) -> None:
        cameras = plan_cameras(field_records(), 1280, 720)
        root_x = {column * 0.76 - 3.42 for column in range(10)}
        for genotype in "abc":
            x = cameras[f"genotype_{genotype}_intra_row"]["position"][0]
            self.assertNotIn(x, root_x)
            self.assertTrue(any(left < x < right for left, right in zip(sorted(root_x), sorted(root_x)[1:])))


if __name__ == "__main__":
    unittest.main()
