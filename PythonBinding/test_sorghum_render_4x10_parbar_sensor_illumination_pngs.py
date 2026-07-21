from __future__ import annotations

import argparse
import csv
import tempfile
import unittest
from pathlib import Path

import sorghum_render_4x10_parbar_sensor_illumination_pngs as renderer


def summary_rows(replicates: int = 7) -> list[dict[str, object]]:
    return [
        {
            "date": date,
            "cultivar": cultivar,
            "sensor_bar_level": level,
            "probe_number": probe,
            "replicate_count": replicates,
            renderer.VALUE_COLUMN: date_index + panel_index / 10.0 + probe / 1000.0,
        }
        for date_index, date in enumerate(renderer.DATE_ORDER)
        for panel_index, (cultivar, level, _label) in enumerate(renderer.PANEL_ORDER)
        for probe in range(1, 101)
    ]


class SummaryValidationTest(unittest.TestCase):
    def test_requires_complete_five_date_campaign(self) -> None:
        rows = summary_rows()
        self.assertEqual(7, renderer.validate_summary_rows(rows))
        with self.assertRaises(ValueError):
            renderer.validate_summary_rows(rows[:-600])

    def test_rejects_inconsistent_replicate_counts_and_duplicate_probes(self) -> None:
        rows = summary_rows()
        rows[0]["replicate_count"] = 8
        with self.assertRaises(ValueError):
            renderer.validate_summary_rows(rows)

        rows = summary_rows()
        rows.append(dict(rows[0]))
        with self.assertRaises(ValueError):
            renderer.validate_summary_rows(rows)

        rows = summary_rows()
        rows[0][renderer.VALUE_COLUMN] = float("nan")
        with self.assertRaises(ValueError):
            renderer.validate_summary_rows(rows)

    def test_renders_exactly_five_mean_heatmaps(self) -> None:
        rows = summary_rows(3)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = root / "handoff"
            handoff.mkdir()
            with (handoff / "all_parbar_sensors_summary.csv").open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            count, output = renderer.render_all(
                argparse.Namespace(
                    handoff_dir=handoff, output_dir=None, expected_replicates=3
                )
            )

            self.assertEqual(5, count)
            self.assertEqual((handoff / "labeled_pngs").resolve(), output)
            pngs = sorted((output / "4x10_parbar_probe_heatmaps").glob("*.png"))
            self.assertEqual(5, len(pngs))
            self.assertTrue(all(path.stat().st_size > 0 for path in pngs))
            with (output / "visualization_manifest.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                manifest = list(csv.DictReader(stream))
            self.assertEqual(5, len(manifest))
            self.assertTrue(all(row["replicate_count"] == "3" for row in manifest))


if __name__ == "__main__":
    unittest.main()
