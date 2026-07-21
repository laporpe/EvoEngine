from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sorghum_4x10_parbar_sensor_illumination_handoff as handoff
from sorghum_asset_layout import (
    DATE_ORDER,
    DEFAULT_PROJECT_ASSETS,
    GENERATED_REPORT_ROOT,
)


class RunningStatsTest(unittest.TestCase):
    def test_matches_sample_statistics_and_uncertainty(self) -> None:
        values = [1.0, 2.0, 4.0, 8.0]
        stats = handoff.RunningStats()
        for value in values:
            stats.add(value)

        self.assertAlmostEqual(statistics.fmean(values), stats.mean)
        self.assertAlmostEqual(statistics.stdev(values), stats.std)
        self.assertAlmostEqual(stats.std / math.sqrt(len(values)), stats.sem)
        self.assertEqual(
            (stats.mean - 1.96 * stats.sem, stats.mean + 1.96 * stats.sem), stats.ci95
        )

    def test_rejects_non_finite_values(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                handoff.RunningStats().add(value)


class CampaignSeedTest(unittest.TestCase):
    def test_video_render_settings_are_independent_from_parbar_settings(self) -> None:
        args = handoff.build_parser().parse_args(
            [
                "--samples",
                "64",
                "--bounces",
                "4",
                "--video-samples",
                "2",
                "--video-bounces",
                "1",
            ]
        )

        self.assertEqual((64, 4), (args.samples, args.bounces))
        self.assertEqual((2, 1), (args.video_samples, args.video_bounces))

    def test_rejects_duplicate_dates(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            handoff.parse_dates(f"{DATE_ORDER[0]},{DATE_ORDER[0]}")

    def test_all_five_dates_and_plants_have_disjoint_stable_seeds(self) -> None:
        seed_base = 2_000_000
        stride = 40
        plant_count = 40
        seeds = set()
        for replicate in range(7):
            for date in DATE_ORDER:
                geometry_base = handoff.geometry_seed_for_replicate(
                    seed_base, stride, date, replicate
                )
                current = set(range(geometry_base, geometry_base + plant_count))
                self.assertTrue(seeds.isdisjoint(current))
                seeds.update(current)

        self.assertEqual(7 * len(DATE_ORDER) * plant_count, len(seeds))
        self.assertEqual(
            seed_base + len(DATE_ORDER) * stride,
            handoff.geometry_seed_for_replicate(seed_base, stride, DATE_ORDER[0], 1),
        )
        self.assertEqual(5, handoff.ray_seed_for_replicate(0, DATE_ORDER[0], 1))

    def test_seed_plan_rejects_overlap_and_signed_int_overflow(self) -> None:
        counts = {date: 40 for date in DATE_ORDER}
        with self.assertRaises(ValueError):
            handoff.validate_seed_plan(2_000_000, 39, 0, 10, counts)
        with self.assertRaises(ValueError):
            handoff.validate_seed_plan(2_000_000, 1000, 0, 1_000_000, counts)

    def test_written_schedule_has_one_disjoint_interval_per_date_and_replicate(
        self,
    ) -> None:
        args = argparse.Namespace(
            replicates=7,
            geometry_seed=2_000_000,
            geometry_seed_stride=1000,
            seed=0,
        )
        rows = handoff.seed_schedule_rows(args, {date: 40 for date in DATE_ORDER})

        self.assertEqual(7 * len(DATE_ORDER), len(rows))
        handoff.validate_seed_schedule(rows)


class CurrentAssetContractTest(unittest.TestCase):
    def test_manifest_has_one_rooted_plant_per_position(self) -> None:
        rows = handoff.load_height_manifest(
            DEFAULT_PROJECT_ASSETS / GENERATED_REPORT_ROOT, list(DATE_ORDER)
        )
        self.assertEqual(
            {date: 40 for date in DATE_ORDER},
            handoff.plant_counts_by_date(rows, list(DATE_ORDER)),
        )
        plants = handoff.plant_rows_from_manifest(rows)

        self.assertEqual(200, len(plants))
        for date in DATE_ORDER:
            for cultivar in handoff.CULTIVARS:
                selected = [
                    row
                    for row in plants
                    if row["date"] == date and row["cultivar"] == cultivar
                ]
                self.assertEqual(20, len(selected))
                self.assertTrue(
                    all(row["plants_at_original_position"] == 1 for row in selected)
                )
                self.assertTrue(
                    all(row["cluster_member_number"] == 1 for row in selected)
                )
                self.assertTrue(
                    all(3 <= row["primary_tiller_count"] <= 5 for row in selected)
                )

    def test_rejects_incomplete_or_duplicate_rooted_positions(self) -> None:
        rows = handoff.load_height_manifest(
            DEFAULT_PROJECT_ASSETS / GENERATED_REPORT_ROOT, [DATE_ORDER[0]]
        )
        with self.assertRaises(ValueError):
            handoff.plant_counts_by_date(rows[:-1], [DATE_ORDER[0]])

        duplicate = [dict(row) for row in rows]
        duplicate[-1]["base_plant_name"] = duplicate[0]["base_plant_name"]
        with self.assertRaises(ValueError):
            handoff.plant_counts_by_date(duplicate, [DATE_ORDER[0]])


class ProbeValidationTest(unittest.TestCase):
    @staticmethod
    def records(probes_per_panel: int) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(cultivar=cultivar, sensor_bar_level=level, column=column)
            for cultivar in handoff.CULTIVARS
            for level in handoff.BAR_LEVELS
            for column in range(probes_per_panel)
        ]

    def test_requires_every_probe_exactly_once(self) -> None:
        records = self.records(2)
        handoff.validate_sensor_records(records, 2)
        with self.assertRaises(ValueError):
            handoff.validate_sensor_records(records[:-1], 2)
        with self.assertRaises(ValueError):
            handoff.validate_sensor_records(records + records[:1], 2)


class CheckpointTest(unittest.TestCase):
    def test_directory_fingerprint_covers_nested_asset_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "materials" / "soil.bin"
            nested.parent.mkdir()
            nested.write_bytes(b"soil-v1")
            before = handoff.directory_sha256(root)
            nested.write_bytes(b"soil-v2")

            self.assertNotEqual(before, handoff.directory_sha256(root))

    def test_round_trip_and_fingerprint_guard(self) -> None:
        accumulator = handoff.SummaryAccumulator(
            {"date": DATE_ORDER[0], "cultivar": "BTX"}
        )
        accumulator.add(
            {
                column: float(index)
                for index, column in enumerate(handoff.SENSOR_NUMERIC_COLUMNS)
            }
        )
        fingerprint = {"date": DATE_ORDER[0], "replicates": 2}
        key = ("BTX", "top", 0)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            handoff.save_checkpoint(path, fingerprint, 1, {key: accumulator})
            next_replicate, restored = handoff.load_checkpoint(path, fingerprint)

            self.assertEqual(1, next_replicate)
            self.assertEqual(
                1, restored[key].stats["illumination_total_simulated"].count
            )
            with self.assertRaises(ValueError):
                handoff.load_checkpoint(path, {**fingerprint, "replicates": 3})

    def test_resume_statistics_equal_uninterrupted_statistics(self) -> None:
        values = [1.0, 2.5, 4.0, 9.0]
        key = ("BTX", "top", 0)
        direct = handoff.SummaryAccumulator({"date": DATE_ORDER[0]})
        interrupted = handoff.SummaryAccumulator({"date": DATE_ORDER[0]})

        for value in values:
            direct.add({column: value for column in handoff.SENSOR_NUMERIC_COLUMNS})
        for value in values[:2]:
            interrupted.add(
                {column: value for column in handoff.SENSOR_NUMERIC_COLUMNS}
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            handoff.save_checkpoint(path, {"campaign": 1}, 2, {key: interrupted})
            next_replicate, restored = handoff.load_checkpoint(path, {"campaign": 1})
            for value in values[next_replicate:]:
                restored[key].add(
                    {column: value for column in handoff.SENSOR_NUMERIC_COLUMNS}
                )

        for column in handoff.SENSOR_NUMERIC_COLUMNS:
            self.assertEqual(
                direct.stats[column].to_dict(), restored[key].stats[column].to_dict()
            )
            self.assertEqual(direct.stats[column].std, restored[key].stats[column].std)

    def test_rejects_incomplete_probe_checkpoint_before_engine_start(self) -> None:
        incomplete = {
            ("BTX", "top", 0): handoff.SummaryAccumulator({"date": DATE_ORDER[0]})
        }
        with self.assertRaises(ValueError):
            handoff.validate_checkpoint_accumulators(
                incomplete, 1, 100, Path("checkpoint.json")
            )


class EngineBatchTest(unittest.TestCase):
    def test_batch_stop_never_exceeds_campaign_total(self) -> None:
        self.assertEqual(10, handoff.replicate_batch_stop(0, 100, 10))
        self.assertEqual(100, handoff.replicate_batch_stop(90, 100, 10))
        self.assertEqual(100, handoff.replicate_batch_stop(10, 100, 0))

    def test_batch_stop_rejects_invalid_progress(self) -> None:
        with self.assertRaises(ValueError):
            handoff.replicate_batch_stop(101, 100, 10)

    def test_exclusive_file_lock_rejects_a_second_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.lock"
            with handoff.exclusive_file_lock(path, "busy"):
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    with handoff.exclusive_file_lock(path, "busy"):
                        pass

    def test_parent_restarts_worker_with_resume(self) -> None:
        date = DATE_ORDER[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(
                checkpoint_dir=root,
                dates=[date],
                resume=False,
                repo_root=root,
                engine_batch_size=2,
                replicates=3,
                probes_per_panel=1,
            )
            resumes = []
            calls = 0

            def command(_args, _date, _sensor_csv, _worker_lock, resume):
                resumes.append(resume)
                return ["worker"]

            def run(_command, _cwd, _log_path, _append, _date):
                nonlocal calls
                calls += 1
                (root / f"{date}.json").write_text(
                    json.dumps({"next_replicate": 2 if calls == 1 else 3}),
                    encoding="utf-8",
                )
                if calls == 2:
                    rows = [
                        {
                            "date": date,
                            "cultivar": cultivar,
                            "sensor_bar_level": level,
                            "probe_number": 1,
                        }
                        for cultivar in handoff.CULTIVARS
                        for level in handoff.BAR_LEVELS
                    ]
                    handoff.write_csv(
                        root / "workers" / f"{date}_sensors.csv",
                        [
                            "date",
                            "cultivar",
                            "sensor_bar_level",
                            "probe_number",
                        ],
                        rows,
                    )
                return 0

            with (
                mock.patch.object(handoff, "verify_campaign_fingerprints"),
                mock.patch.object(handoff, "worker_command", side_effect=command),
                mock.patch.object(handoff, "run_worker_process", side_effect=run),
            ):
                rows = handoff.sensor_rows_with_workers(args, {date: {}})

        self.assertEqual([False, True], resumes)
        self.assertEqual(6, len(rows))

    def test_video_parent_accepts_cuda_teardown_only_after_durable_outputs(self) -> None:
        date = DATE_ORDER[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(
                checkpoint_dir=root,
                dates=[date],
                resume=False,
                repo_root=root,
                engine_batch_size=1,
                replicates=2,
                probes_per_panel=1,
                video=True,
            )
            calls = 0

            def run(_command, _cwd, _log_path, _append, _date):
                nonlocal calls
                calls += 1
                (root / f"{date}.json").write_text(
                    json.dumps({"next_replicate": calls}), encoding="utf-8"
                )
                if calls == 2:
                    handoff.write_csv(
                        root / "workers" / f"{date}_sensors.csv",
                        ["date", "cultivar", "sensor_bar_level", "probe_number"],
                        [
                            {
                                "date": date,
                                "cultivar": cultivar,
                                "sensor_bar_level": level,
                                "probe_number": 1,
                            }
                            for cultivar in handoff.CULTIVARS
                            for level in handoff.BAR_LEVELS
                        ],
                    )
                return 0xC0000005

            with (
                mock.patch.object(handoff, "verify_campaign_fingerprints"),
                mock.patch.object(handoff, "worker_command", return_value=["worker"]),
                mock.patch.object(handoff, "run_worker_process", side_effect=run),
                mock.patch.object(handoff, "validate_staged_prefix") as validate,
            ):
                rows = handoff.sensor_rows_with_workers(args, {date: {}})

        self.assertEqual(6, len(rows))
        self.assertEqual([mock.call(root / "video_staging", date, 1, 1), mock.call(root / "video_staging", date, 2, 1)], validate.call_args_list)

    def test_parent_terminates_worker_when_log_streaming_is_interrupted(self) -> None:
        class InterruptedOutput:
            def __iter__(self):
                raise KeyboardInterrupt

        class Process:
            stdout = InterruptedOutput()
            terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        process = Process()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            handoff.subprocess, "Popen", return_value=process
        ):
            with self.assertRaises(KeyboardInterrupt):
                handoff.run_worker_process(
                    ["worker"],
                    Path(directory),
                    Path(directory) / "worker.log",
                    False,
                    DATE_ORDER[0],
                )
        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
