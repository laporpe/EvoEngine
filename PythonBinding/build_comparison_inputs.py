"""Build the input table for the panel C transmission-ratio figure."""

from pathlib import Path
import argparse

import pandas as pd

DAYTIME_MIN_PAR = 50.0


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    repo_root = repo_root_from_script()
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sim-file",
        type=Path,
        default=repo_root / "out" / "handoff" / "date_height_parbar_illumination" / "all_parbar_sensors_long.csv",
        help="Combined simulated PARBAR CSV.",
    )
    parser.add_argument(
        "--field-dir",
        type=Path,
        default=script_dir,
        help="Directory containing taX_cal.csv, taY_cal.csv, tbX_cal.csv, and tbY_cal.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "panelC_inputs.csv",
        help="Output CSV path.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    sim = pd.read_csv(args.sim_file)
    sim["genotype"] = sim["cultivar"].replace({"BTX": "BTx623"})
    illumination_column = (
        "illumination_total_simulated"
        if "illumination_total_simulated" in sim.columns
        else "illumination_total_simulated_mean"
    )

    bar_means = sim.groupby(["date", "genotype", "sensor_bar_level"])[illumination_column].mean()
    bar_means = bar_means.unstack("sensor_bar_level")
    bar_means["tau_sim"] = bar_means["bottom"] / bar_means["top"]
    tau_sim = bar_means["tau_sim"].reset_index()

    field_files = [
        ("taX_cal.csv", "Pawaga", "A-X"),
        ("taY_cal.csv", "Pawaga", "A-Y"),
        ("tbX_cal.csv", "BTx623", "B-X"),
        ("tbY_cal.csv", "BTx623", "B-Y"),
    ]
    missing = [str(args.field_dir / filename) for filename, _genotype, _unit in field_files if not (args.field_dir / filename).exists()]
    if missing:
        raise FileNotFoundError("Missing field PARbar CSV(s):\n" + "\n".join(missing))

    sensor_days = []
    for filename, genotype, unit in field_files:
        df = pd.read_csv(args.field_dir / filename, parse_dates=["timestamp"])
        df = df.rename(
            columns={
                f"PAR_{unit}-AboveCanopy (umol/m2s)": "above",
                f"PAR_{unit}-BelowCanopy (umol/m2s)": "below",
            }
        )
        df = df[(df["above"] >= DAYTIME_MIN_PAR) & (df["below"] <= df["above"])]
        df["date"] = df["timestamp"].dt.strftime("%Y-%m-%d")
        daily = df.groupby("date")[["above", "below"]].sum() / 1e6
        daily["genotype"] = genotype
        sensor_days.append(daily.reset_index())

    field = pd.concat(sensor_days, ignore_index=True).groupby(["date", "genotype"], as_index=False).sum()
    field = field.rename(
        columns={
            "above": "field_above_par_mol_m2_day",
            "below": "field_below_mol_m2_day",
        }
    )

    panel_c = tau_sim.merge(field, on=["date", "genotype"])
    panel_c = panel_c[
        [
            "date",
            "genotype",
            "tau_sim",
            "field_below_mol_m2_day",
            "field_above_par_mol_m2_day",
        ]
    ].round(4)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    panel_c.to_csv(args.output, index=False)
    print(panel_c.to_string(index=False))


if __name__ == "__main__":
    main()
