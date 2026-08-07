import argparse
import json
import random
import secrets
import subprocess
import sys
from pathlib import Path


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def nonnegative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def scene_is_complete(scene_directory, scene_name, scene_seed, require_geometry_sampling, expected_settings):
    generation_path = scene_directory / f"{scene_name}_generation.json"
    try:
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    required_paths = [
        scene_directory / f"{scene_name}.obj",
        scene_directory / f"{scene_name}_trees.obj",
        scene_directory / f"{scene_name}_ground.obj",
        scene_directory / f"{scene_name}_object_ids.json",
        scene_directory / f"{scene_name}_view.png",
        scene_directory / f"{scene_name}_depth.png",
    ]
    station_count = generation.get("tls", {}).get("station_count", 0)
    required_paths.extend(
        scene_directory / f"{scene_name}_tls_scan_{index:02d}.ply"
        for index in range(1, station_count + 1)
    )
    if require_geometry_sampling:
        required_paths.append(scene_directory / f"{scene_name}_geometry_sampled.ply")
    tls_settings = generation.get("tls", {})
    settings_match = (
        station_count > 0
        and generation.get("bush_count_range") == expected_settings["bush_count_range"]
        and generation.get("bush_visible_height_range") == expected_settings["bush_visible_height_range"]
        and generation.get("large_spruce_count_range") == expected_settings["large_spruce_count_range"]
        and generation.get("tall_conifer_target_height") == expected_settings["tall_conifer_target_height"]
        and generation.get("double_tree_pair_count_range") == expected_settings["double_tree_pair_count_range"]
        and generation.get("double_tree_distance_range") == expected_settings["double_tree_distance_range"]
        and all(tls_settings.get(key) == value for key, value in expected_settings["tls"].items())
    )
    return (
        generation.get("scene_seed") == scene_seed
        and settings_match
        and all(path.is_file() and path.stat().st_size > 0 for path in required_paths)
    )


def main():
    parser = argparse.ArgumentParser(description="Generate multiple EcoSysLab tree scenes and both point-cloud cases.")
    parser.add_argument("--count", type=positive_int, default=5, help="Scenes per configuration.")
    parser.add_argument(
        "--scenes",
        nargs="+",
        choices=("alley", "dense_park", "sparse_park"),
        default=("alley", "dense_park", "sparse_park"),
    )
    parser.add_argument("--seed", type=int, help="Master seed; omitted means a new randomized batch.")
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--skip-geometry-sampling", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip complete scenes whose stored seed matches.")
    parser.add_argument("--bush-count-min", type=positive_int, default=5)
    parser.add_argument("--bush-count-max", type=positive_int, default=8)
    parser.add_argument("--bush-visible-height-min", type=positive_float, default=1.0)
    parser.add_argument("--bush-visible-height-max", type=positive_float, default=1.625)
    parser.add_argument("--large-spruce-min", type=nonnegative_int, default=2)
    parser.add_argument("--large-spruce-max", type=nonnegative_int, default=3)
    parser.add_argument("--tall-conifer-height", type=positive_float, default=10.0)
    parser.add_argument("--double-tree-pair-min", type=nonnegative_int, default=1)
    parser.add_argument("--double-tree-pair-max", type=nonnegative_int, default=2)
    parser.add_argument("--double-tree-distance-min", type=positive_float, default=0.25)
    parser.add_argument("--double-tree-distance-max", type=positive_float, default=0.45)
    parser.add_argument("--tls-station-count", type=positive_int)
    parser.add_argument("--tls-height", type=positive_float, default=1.6)
    parser.add_argument("--tls-angular-step", type=positive_float, default=0.04)
    parser.add_argument("--tls-sector-width", type=positive_float, default=30.0)
    parser.add_argument("--tls-max-depth", type=positive_float, default=70.0)
    args = parser.parse_args()
    if args.bush_count_min > args.bush_count_max:
        parser.error("--bush-count-min cannot exceed --bush-count-max")
    if args.bush_visible_height_min > args.bush_visible_height_max:
        parser.error("--bush-visible-height-min cannot exceed --bush-visible-height-max")
    if args.large_spruce_min > args.large_spruce_max:
        parser.error("--large-spruce-min cannot exceed --large-spruce-max")
    if args.large_spruce_min == 0:
        parser.error("--large-spruce-min must be at least 1 when generating a tall conifer")
    if args.double_tree_pair_min > args.double_tree_pair_max:
        parser.error("--double-tree-pair-min cannot exceed --double-tree-pair-max")
    if args.double_tree_distance_min > args.double_tree_distance_max:
        parser.error("--double-tree-distance-min cannot exceed --double-tree-distance-max")
    if args.tls_sector_width > 360.0:
        parser.error("--tls-sector-width cannot exceed 360 degrees")

    root = Path(__file__).resolve().parents[2]
    script_directory = Path(__file__).resolve().parent
    master_seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    seed_generator = random.Random(master_seed)
    base_names = {
        "alley": "AlleyTreeScene",
        "dense_park": "DenseParkScene",
        "sparse_park": "SparseParkScene",
    }
    manifest = {
        "master_seed": master_seed,
        "count_per_configuration": args.count,
        "bush_count_range": [args.bush_count_min, args.bush_count_max],
        "bush_visible_height_range": [args.bush_visible_height_min, args.bush_visible_height_max],
        "large_spruce_count_range": [args.large_spruce_min, args.large_spruce_max],
        "tall_conifer_target_height": args.tall_conifer_height,
        "double_tree_pair_count_range": [args.double_tree_pair_min, args.double_tree_pair_max],
        "double_tree_distance_range": [args.double_tree_distance_min, args.double_tree_distance_max],
        "tls": {
            "mode": "fixed_origin_spherical",
            "station_count_requested": args.tls_station_count,
            "capture_height": args.tls_height,
            "angular_step_degrees": args.tls_angular_step,
            "sector_width_degrees": args.tls_sector_width,
            "max_capture_depth": args.tls_max_depth,
        },
        "scenes": [],
    }
    manifest_path = root / "out" / f"tree_scene_batch_{master_seed}.json"

    print(f"Batch seed: {master_seed}", flush=True)
    for scene_kind in args.scenes:
        for scene_index in range(1, args.count + 1):
            scene_seed = seed_generator.randrange(2**31)
            scene_name = f"{base_names[scene_kind]}_{scene_index:03d}"
            scene_directory = root / "out" / base_names[scene_kind] / scene_name
            expected_settings = {
                "bush_count_range": [args.bush_count_min, args.bush_count_max],
                "bush_visible_height_range": [args.bush_visible_height_min, args.bush_visible_height_max],
                "large_spruce_count_range": [args.large_spruce_min, args.large_spruce_max],
                "tall_conifer_target_height": args.tall_conifer_height,
                "double_tree_pair_count_range": [args.double_tree_pair_min, args.double_tree_pair_max],
                "double_tree_distance_range": [args.double_tree_distance_min, args.double_tree_distance_max],
                "tls": {
                    "mode": "fixed_origin_spherical",
                    "station_count_requested": args.tls_station_count,
                    "capture_height": args.tls_height,
                    "angular_step_degrees": args.tls_angular_step,
                    "sector_width_degrees": args.tls_sector_width,
                    "max_capture_depth": args.tls_max_depth,
                },
            }
            command = [
                sys.executable,
                str(script_directory / f"generate_{scene_kind}_scene.py"),
                "--seed",
                str(scene_seed),
                "--scene-index",
                str(scene_index),
                "--bush-count-min",
                str(args.bush_count_min),
                "--bush-count-max",
                str(args.bush_count_max),
                "--bush-visible-height-min",
                str(args.bush_visible_height_min),
                "--bush-visible-height-max",
                str(args.bush_visible_height_max),
                "--large-spruce-min",
                str(args.large_spruce_min),
                "--large-spruce-max",
                str(args.large_spruce_max),
                "--tall-conifer-height",
                str(args.tall_conifer_height),
                "--double-tree-pair-min",
                str(args.double_tree_pair_min),
                "--double-tree-pair-max",
                str(args.double_tree_pair_max),
                "--double-tree-distance-min",
                str(args.double_tree_distance_min),
                "--double-tree-distance-max",
                str(args.double_tree_distance_max),
                "--tls-height",
                str(args.tls_height),
                "--tls-angular-step",
                str(args.tls_angular_step),
                "--tls-sector-width",
                str(args.tls_sector_width),
                "--tls-max-depth",
                str(args.tls_max_depth),
            ]
            if args.tls_station_count is not None:
                command.extend(("--tls-station-count", str(args.tls_station_count)))
            if args.timing:
                command.append("--timing")
            scene_record = {
                "configuration": scene_kind,
                "index": scene_index,
                "seed": scene_seed,
                "output_directory": str(scene_directory),
            }
            if args.resume and scene_is_complete(
                scene_directory,
                scene_name,
                scene_seed,
                not args.skip_geometry_sampling,
                expected_settings,
            ):
                print(f"Skipping complete {scene_name} with seed {scene_seed}.", flush=True)
                manifest["scenes"].append(scene_record)
                manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                continue
            print(f"Generating {scene_name} with seed {scene_seed}...", flush=True)
            subprocess.run(command, cwd=root, check=True)
            if not args.skip_geometry_sampling:
                sample_command = [
                    sys.executable,
                    str(script_directory / "sample_scene_geometry.py"),
                    "--scene",
                    str(scene_directory),
                    "--seed",
                    str(scene_seed),
                ]
                if args.timing:
                    sample_command.append("--timing")
                subprocess.run(sample_command, cwd=root, check=True)
            manifest["scenes"].append(scene_record)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Batch complete. Manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
