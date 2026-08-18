import tempfile
import unittest
from pathlib import Path

from sorghum_validate_4x10_presentation_invariance import (
    SCIENTIFIC_FILES,
    compare_scientific_outputs,
)


class PresentationInvarianceTests(unittest.TestCase):
    def test_identical_scientific_outputs_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "science", root / "presentation"
            first.mkdir()
            second.mkdir()
            for name in SCIENTIFIC_FILES:
                (first / name).write_text("header\nvalue\n", encoding="utf-8")
                (second / name).write_text("header\nvalue\n", encoding="utf-8")
            result = compare_scientific_outputs(first, second)
            self.assertTrue(result["passed"])
            self.assertTrue(all(row["byte_identical"] for row in result["files"]))

    def test_one_changed_scientific_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "science", root / "presentation"
            first.mkdir()
            second.mkdir()
            for name in SCIENTIFIC_FILES:
                (first / name).write_text("same\n", encoding="utf-8")
                (second / name).write_text("same\n", encoding="utf-8")
            (second / SCIENTIFIC_FILES[0]).write_text("changed\n", encoding="utf-8")
            result = compare_scientific_outputs(first, second)
            self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
