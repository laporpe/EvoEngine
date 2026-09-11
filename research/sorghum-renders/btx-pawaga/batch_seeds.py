#!/usr/bin/env python3
"""Long-running seed-ensemble batch runner (one GPU, sequential).

Each CONFIG names its own layout, output tag, sun table, seed base, and seed
count, so existing ensembles can be topped up without re-running old seeds
(the driver's output tag encodes the seed, and analysis scripts glob by tag).
Appends one line per finished run to batch_progress.txt and writes
BATCH_DONE.txt when complete. A failed run is retried once after 30 s
(transient GPU submit errors), then logged and skipped.

    python batch_seeds.py
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONDA = r"C:\Users\Brenda\.miniconda3\Scripts\conda.exe"

BTX = "BTX623_20210726_v6.sorghumls"
PAWAGA = "Pawaga_20210726_v8.sorghumls"

# (layout, tag_prefix, sun_csv, seed_base, n_seeds)
# Top-up plan to n=25 per estimate with the final v6/v8 pair:
CONFIGS = [
    ("small", "E11v6_small", "sun_positions_20210726.csv", 8001, 25),  # fresh: context fig panel (a)
    ("full", "E10v6_full", "sun_positions_20210726.csv", 7113, 13),    # 12 existing (7101-7112) -> 25
    ("full", "V0822v6", "sun_positions_20210822.csv", 7209, 17),       # 8 existing (7201-7208) -> 25
    ("full", "V0921v6", "sun_positions_20210921.csv", 7209, 17),       # 8 existing (7201-7208) -> 25
]


def main() -> int:
    progress = HERE / "batch_progress.txt"
    done = HERE / "BATCH_DONE.txt"
    done.unlink(missing_ok=True)

    with progress.open("a", encoding="utf-8") as log:
        log.write(f"# batch start {time.strftime('%Y-%m-%d %H:%M:%S')} "
                  f"configs={[(t, base, n) for _, t, _, base, n in CONFIGS]}\n")
        log.flush()
        for layout, tag_prefix, sun_csv, seed_base, n_seeds in CONFIGS:
            for seed in range(seed_base, seed_base + n_seeds):
                tag = f"{tag_prefix}_s{seed}"
                cmd = [CONDA, "run", "-n", "evoengine", "--no-capture-output", "python",
                       str(HERE / "run_tau_diurnal.py"), "--layout", layout,
                       "--leaf-vsub", "0.02", "--leaf-hsub", "4", "--seed", str(seed),
                       "--sun-csv", sun_csv,
                       "--btx-descriptor", BTX, "--pawaga-descriptor", PAWAGA,
                       "--tag", tag, "--valid-only"]
                start = time.time()
                result = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
                if result.returncode != 0:
                    time.sleep(30)  # transient GPU submit errors right after heavy runs
                    result = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
                status = "ok" if result.returncode == 0 else f"FAIL({result.returncode})"
                log.write(f"{time.strftime('%H:%M:%S')} {tag_prefix} seed={seed} {status} "
                          f"{time.time() - start:.0f}s\n")
                log.flush()
                if result.returncode != 0:
                    (HERE / f"batch_fail_{tag_prefix}_{seed}.log").write_text(
                        result.stdout[-3000:] + "\n---\n" + result.stderr[-3000:],
                        encoding="utf-8")
    done.write_text(f"done {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
