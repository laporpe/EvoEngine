#!/usr/bin/env python3
"""Prove that optional 4x10 presentation capture leaves scientific CSVs unchanged."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCIENTIFIC_FILES = (
    "all_parbar_sensors_summary.csv",
    "all_individual_plants_long.csv",
    "all_clumps_long.csv",
    "replicate_seed_schedule.csv",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compare_scientific_outputs(
    science_only: Path, with_presentation: Path
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for name in SCIENTIFIC_FILES:
        first = science_only / name
        second = with_presentation / name
        if not first.is_file() or not second.is_file():
            missing = [str(path) for path in (first, second) if not path.is_file()]
            raise FileNotFoundError(f"missing scientific output: {', '.join(missing)}")
        first_hash = sha256(first)
        second_hash = sha256(second)
        files.append(
            {
                "file": name,
                "science_only_sha256": first_hash,
                "with_presentation_sha256": second_hash,
                "byte_identical": first_hash == second_hash,
            }
        )
    return {
        "validation": "sorghum_4x10_presentation_scientific_invariance",
        "science_only": str(science_only.resolve()),
        "with_presentation": str(with_presentation.resolve()),
        "passed": all(bool(record["byte_identical"]) for record in files),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("science_only", type=Path)
    parser.add_argument("with_presentation", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = compare_scientific_outputs(args.science_only, args.with_presentation)
    payload = json.dumps(result, indent=2)
    print(payload)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
