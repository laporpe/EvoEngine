#!/usr/bin/env python3
"""Render the 2026 6x10 SorghumLS field through 1,000 full-lifecycle states."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from sorghum_2026_6x10_data import EXPERIMENT_ID, ROW_GENOTYPES, repo_root_from_script
from sorghum_2026_6x10_scene import (
    GENOTYPES,
    SEEDS,
    TEMPLATE_SCENE,
    configure_engine_imports,
)
from sorghum_4x10_presentation import (
    DEFAULT_PROFILE,
    apply_photo_grade,
    configure_lighting,
    set_ground_extension,
)
from sorghum_render_2026_6x10 import (
    camera_for_view,
    geometry_bounds,
    image_metrics,
    sha256,
)


STATE_COUNT = 1000
FPS = 24
FRAME_PATTERN = "field_%04d.png"
DESCRIPTOR_SESSION = "MeasurementStage02"
FIELD_LEAF_VERTICAL_SUBDIVISION_M = 0.04
FIELD_LEAF_HORIZONTAL_SUBDIVISIONS = 3
PANICLE_CANOPY_CLEARANCE_M = 0.08
PANICLE_PRESENTATION = {
    "peduncle_length_m": 0.82,
    "rachis_length_m": 0.34,
    "branch_length_m": 0.18,
    "primary_branch_count": 20,
    "spikelet_pairs_per_branch": 7,
    "spikelet_length_m": 0.010,
    "spikelet_radius_m": 0.0045,
    "immature_color": (0.45, 0.62, 0.12),
    "mature_color": (0.58, 0.20, 0.055),
}
COMPACT_PANICLE_PRESENTATION = {
    "peduncle_length_m": 0.90,
    "rachis_length_m": 0.26,
    "branch_length_m": 0.11,
    "primary_branch_count": 22,
    "spikelet_pairs_per_branch": 8,
    "spikelet_length_m": 0.009,
    "spikelet_radius_m": 0.005,
    "immature_color": (0.45, 0.62, 0.12),
    "mature_color": (0.58, 0.20, 0.055),
}
DEFAULT_FIELD_PROFILE = "abc-btx-vegetative"
COMPACT_PANICLE_FIELD_PROFILE = "abc-btx-vegetative-compact-panicle"
MEASURED_VEGETATIVE_FIELD_PROFILE = "abc-measured-vegetative-reference"
REFERENCE_FIELD_PROFILE = "btx-pawaga-reference"
CAMERA_VIEWS = ("perspective", "near_top_down")
PLAYBACK_FPS = (12, 24, 48)
MILESTONE_STATES = (1, 100, 250, 500, 750, 1000)
FIELD_PROFILES = {
    DEFAULT_FIELD_PROFILE: {
        "labels": GENOTYPES,
        "row_labels": ROW_GENOTYPES,
        "plots": tuple(
            {
                "plot": index + 1,
                "rows": (index * 2, index * 2 + 1),
                "genotype": genotype,
            }
            for index, genotype in enumerate(GENOTYPES)
        ),
        "plants_per_label": 20,
        "descriptor_paths": {
            genotype: Path("ManualAssets/Descriptors/BTX.sorghumls")
            for genotype in GENOTYPES
        },
        "descriptor_session": "manual_btx_vegetative_reuse",
        "vegetative_descriptor_source": "ManualAssets/Descriptors/BTX.sorghumls",
        "panicle_parameter_policy": "explicit_shared_abc_reproductive_presentation_separate_from_btx_vegetative",
        "panicle_presentation": PANICLE_PRESENTATION,
        "minimum_panicle_canopy_clearance_m": PANICLE_CANOPY_CLEARANCE_M,
        "relabel_markers": False,
        "ownership": "authoritative_measured_abc_field_with_shared_btx_vegetative_morphology",
        "basis": "Measured A/A/B/B/C/C 2026 field identities with the manual BTX descriptor reused for all vegetative growth",
        "slug": "abc_btx_vegetative",
    },
    COMPACT_PANICLE_FIELD_PROFILE: {
        "labels": GENOTYPES,
        "row_labels": ROW_GENOTYPES,
        "plots": tuple(
            {
                "plot": index + 1,
                "rows": (index * 2, index * 2 + 1),
                "genotype": genotype,
            }
            for index, genotype in enumerate(GENOTYPES)
        ),
        "plants_per_label": 20,
        "descriptor_paths": {
            genotype: Path("ManualAssets/Descriptors/BTX.sorghumls")
            for genotype in GENOTYPES
        },
        "descriptor_session": "manual_btx_vegetative_reuse",
        "vegetative_descriptor_source": "ManualAssets/Descriptors/BTX.sorghumls",
        "panicle_parameter_policy": "compact_shared_abc_reproductive_presentation_separate_from_btx_vegetative",
        "panicle_presentation": COMPACT_PANICLE_PRESENTATION,
        "minimum_panicle_canopy_clearance_m": PANICLE_CANOPY_CLEARANCE_M,
        "relabel_markers": False,
        "ownership": "measured_abc_field_with_shared_btx_vegetative_and_compact_panicle_presentation",
        "basis": "Measured A/A/B/B/C/C 2026 field identities with shared BTX vegetative growth and a compact shared reproductive presentation",
        "slug": "abc_btx_vegetative_compact_panicle",
    },
    MEASURED_VEGETATIVE_FIELD_PROFILE: {
        "labels": GENOTYPES,
        "row_labels": ROW_GENOTYPES,
        "plots": tuple(
            {
                "plot": index + 1,
                "rows": (index * 2, index * 2 + 1),
                "genotype": genotype,
            }
            for index, genotype in enumerate(GENOTYPES)
        ),
        "plants_per_label": 20,
        "descriptor_paths": {
            genotype: Path("GeneratedAssets/Experiments")
            / EXPERIMENT_ID
            / "Descriptors"
            / DESCRIPTOR_SESSION
            / f"{genotype}.sorghumls"
            for genotype in GENOTYPES
        },
        "descriptor_session": DESCRIPTOR_SESSION,
        "vegetative_descriptor_source": "measured_stage2_per_genotype_descriptors",
        "panicle_parameter_policy": "native_defaults_unchanged_no_serialized_panicle_fields",
        "relabel_markers": False,
        "ownership": "superseded_measured_abc_vegetative_reference",
        "basis": "Measured A/A/B/B/C/C 2026 marker scene instantiated with the Stage-2 A/B/C descriptors",
        "slug": "abc_measured_vegetative_reference",
    },
    REFERENCE_FIELD_PROFILE: {
        "labels": ("BTX", "Pawaga"),
        "row_labels": ("BTX", "BTX", "Pawaga", "Pawaga", "BTX", "Pawaga"),
        "plots": (
            {"plot": 1, "rows": (0, 1), "cultivars": ("BTX", "BTX")},
            {"plot": 2, "rows": (2, 3), "cultivars": ("Pawaga", "Pawaga")},
            {"plot": 3, "rows": (4, 5), "cultivars": ("BTX", "Pawaga")},
        ),
        "plants_per_label": 30,
        "descriptor_paths": {
            cultivar: Path("ManualAssets/Descriptors") / f"{cultivar}.sorghumls"
            for cultivar in ("BTX", "Pawaga")
        },
        "descriptor_session": "manual_reference_descriptors",
        "vegetative_descriptor_source": "manual_per_cultivar_reference_descriptors",
        "panicle_parameter_policy": "native_defaults_unchanged_no_serialized_panicle_fields",
        "relabel_markers": True,
        "ownership": "reference_demonstration_not_the_measured_abc_field",
        "basis": "2026 marker positions relabeled as a 30/30 BTx/Pawaga reference demonstration",
        "slug": "btx_pawaga_reference",
    },
}
TARGET_GDD_PATTERN = re.compile(
    r"(?m)^target_gdd:\s*\r?\n\s*mean:\s*([-+0-9.eE]+)\s*\r?\n\s*deviation:\s*([-+0-9.eE]+)"
)


def field_profile(name: str) -> dict[str, object]:
    try:
        return FIELD_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown field profile: {name}") from exc


def state_gdd(state: int, target_gdd: float, state_count: int = STATE_COUNT) -> float:
    if not 1 <= state <= state_count or target_gdd <= 0.0:
        raise ValueError("state and target GDD are invalid")
    return target_gdd * state / state_count


def requested_states(value: str | None, state_count: int) -> tuple[int, ...]:
    if not value:
        return tuple(range(1, state_count + 1))
    states = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    if not states or states[0] < 1 or states[-1] > state_count:
        raise ValueError("requested states must be within the configured timeline")
    return states


def playback_rates(value: str | None) -> tuple[int, ...]:
    rates = (
        tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
        if value
        else PLAYBACK_FPS
    )
    if not rates or any(rate <= 0 for rate in rates):
        raise ValueError("playback FPS values must be positive integers")
    return rates


def descriptor_paths(project_root: Path, profile: dict[str, object]) -> dict[str, Path]:
    paths = {
        label: project_root / "Assets" / relative
        for label, relative in profile["descriptor_paths"].items()
    }
    if any(not path.is_file() for path in paths.values()):
        raise FileNotFoundError(
            f"missing descriptor asset for field profile {profile['slug']}"
        )
    return paths


def shared_target_gdd(paths: dict[str, Path]) -> float:
    values = []
    for path in paths.values():
        match = TARGET_GDD_PATTERN.search(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"{path} has no readable target_gdd distribution")
        mean, deviation = (float(value) for value in match.groups())
        if deviation != 0.0:
            raise ValueError(
                "the time-lapse requires a fixed target GDD for every 2026 plant"
            )
        values.append(mean)
    if any(abs(value - values[0]) > 1.0e-6 for value in values[1:]):
        raise ValueError(
            f"the field descriptors have different target GDD values: {values}"
        )
    return values[0]


def maturity_floor_gdd(descriptor_target_gdd: float, records: list[object]) -> tuple[float, float]:
    if not records:
        raise ValueError("cannot calculate a maturity endpoint without plants")
    maximum_organ_delay_gdd = max(
        max(
            float(record.vegetative_maturity_gdd),
            float(record.panicle_initiation_gdd) + float(record.panicle_maturity_gdd),
        )
        for record in records
    )
    return descriptor_target_gdd + maximum_organ_delay_gdd, maximum_organ_delay_gdd


def frame_path(output_dir: Path, state: int) -> Path:
    return output_dir / "frames" / (FRAME_PATTERN % state)


def state_path(output_dir: Path, state: int) -> Path:
    return output_dir / "states" / f"field_{state:04d}.json"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized_text_sha256(path: Path) -> str:
    """Hash text semantically so engine-only newline rewrites do not fail provenance."""
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def runtime_asset_snapshot(project_root: Path, project: Path) -> dict[Path, bytes]:
    metadata = (project_root / "Assets").rglob("*.evefoldermeta")
    return {path: path.read_bytes() for path in (project, *metadata)}


def restore_runtime_assets(
    snapshot: dict[Path, bytes], project_root: Path, initial_side_effects: set[Path]
) -> None:
    assets = project_root / "Assets"
    for path in set(assets.glob("New Scene*.evescene*")) - initial_side_effects:
        path.unlink(missing_ok=True)
    for path, content in snapshot.items():
        if not path.is_file() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def valid_cached_state(path: Path, frame: Path, expected: dict[str, object]) -> bool:
    if not path.is_file() or not frame.is_file():
        return False
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
        return all(
            actual.get(key) == value for key, value in expected.items()
        ) and actual.get("frame_sha256") == sha256(frame)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def validate_field(
    records: list[object],
    expected_gdd: float,
    profile: dict[str, object],
    *,
    require_geometry: bool = False,
) -> None:
    if len(records) != 60:
        raise RuntimeError("expected a 60-plant field")
    if require_geometry and any(not record.has_geometry for record in records):
        raise RuntimeError("expected all 60 plants to have rendered geometry")
    observed = Counter(str(record.cultivar) for record in records)
    expected = Counter(
        {label: profile["plants_per_label"] for label in profile["labels"]}
    )
    if observed != expected or any(
        abs(float(record.evaluation_gdd) - expected_gdd) > 1.0e-3 for record in records
    ):
        raise RuntimeError("field plants do not match the requested profile/GDD state")
    for record in records:
        match = re.search(r"_LSystem_R([0-5])_C([0-9])$", str(record.name))
        if (
            not match
            or str(record.cultivar) != profile["row_labels"][int(match.group(1))]
        ):
            raise RuntimeError(f"field row assignment mismatch: {record.name}")


def summarize_phenology(
    records: list[object], profile: dict[str, object]
) -> dict[str, dict[str, float | int]]:
    """Return a compact, renderer-independent reproductive audit by genotype."""
    summary: dict[str, dict[str, float | int]] = {}
    for label in profile["labels"]:
        group = [record for record in records if record.cultivar == label]
        if len(group) != profile["plants_per_label"]:
            raise RuntimeError(
                f"{label}: expected {profile['plants_per_label']} plants in phenology audit"
            )
        summary[label] = {
            "plants": len(group),
            "panicle_emerged_plants": sum(
                bool(record.panicle_emerged) for record in group
            ),
            "panicle_vertex_count": sum(
                int(record.panicle_vertex_count) for record in group
            ),
            "panicle_triangle_count": sum(
                int(record.panicle_triangle_count) for record in group
            ),
            "panicle_branch_count": sum(
                int(record.panicle_branch_count) for record in group
            ),
            "panicle_spikelet_count": sum(
                int(record.panicle_spikelet_count) for record in group
            ),
            "vegetative_mature_plants": sum(
                bool(record.vegetative_organs_mature) for record in group
            ),
            "panicle_mature_plants": sum(bool(record.panicle_mature) for record in group),
            "all_organs_mature_plants": sum(
                bool(record.all_organs_mature) for record in group
            ),
            "immature_vegetative_organ_count": sum(
                int(record.immature_vegetative_organ_count) for record in group
            ),
            "immature_panicle_organ_count": sum(
                int(record.immature_panicle_organ_count) for record in group
            ),
            "developmental_module_count": sum(
                int(record.developmental_module_count) for record in group
            ),
            "minimum_vegetative_growth_progress": min(
                float(record.minimum_vegetative_growth_progress) for record in group
            ),
            "minimum_panicle_growth_progress": min(
                float(record.minimum_panicle_growth_progress) for record in group
            ),
            "mean_height_m": sum(float(record.plant_height_m) for record in group)
            / len(group),
            "mean_vegetative_canopy_height_m": sum(
                float(record.vegetative_canopy_height_m) for record in group
            )
            / len(group),
            "mean_panicle_tip_height_m": sum(
                float(record.panicle_tip_height_m) for record in group
            )
            / len(group),
            "minimum_panicle_canopy_clearance_m": min(
                float(record.panicle_canopy_clearance_m) for record in group
            ),
        }
    return summary


def validate_full_panicle_emergence(summary: dict[str, dict[str, float | int]]) -> None:
    emerged = sum(int(row["panicle_emerged_plants"]) for row in summary.values())
    plants = sum(int(row["plants"]) for row in summary.values())
    if plants != 60 or emerged != plants:
        raise RuntimeError(
            f"final-state panicle emergence failed: {emerged}/{plants}; required 60/60"
        )


def validate_full_organ_maturity(summary: dict[str, dict[str, float | int]]) -> None:
    validate_full_panicle_emergence(summary)
    plants = sum(int(row["plants"]) for row in summary.values())
    vegetative = sum(int(row["vegetative_mature_plants"]) for row in summary.values())
    panicles = sum(int(row["panicle_mature_plants"]) for row in summary.values())
    complete = sum(int(row["all_organs_mature_plants"]) for row in summary.values())
    if plants != 60 or vegetative != plants or panicles != plants or complete != plants:
        raise RuntimeError(
            "final-state organ maturity failed: "
            f"vegetative {vegetative}/{plants}, panicle {panicles}/{plants}, "
            f"whole-plant {complete}/{plants}; required 60/60 for each"
        )


def validate_full_panicle_visibility(
    summary: dict[str, dict[str, float | int]],
    minimum_clearance_m: float = PANICLE_CANOPY_CLEARANCE_M,
) -> None:
    failures = {
        label: float(row["minimum_panicle_canopy_clearance_m"])
        for label, row in summary.items()
        if float(row["minimum_panicle_canopy_clearance_m"]) < minimum_clearance_m
    }
    if failures:
        raise RuntimeError(
            "final-state panicle visibility failed: "
            f"minimum clearance {minimum_clearance_m:.3f} m required; observed {failures}"
        )


def initialize_field(
    evo: object,
    args: argparse.Namespace,
    descriptors: dict[str, Path],
    profile: dict[str, object],
) -> None:
    if not evo.RunLSystemSorghumProject(
        args.project, args.runtime_package_dir, TEMPLATE_SCENE
    ):
        raise RuntimeError(f"failed to load {TEMPLATE_SCENE}")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError("2026 marker scene did not become idle")
    if (
        profile["relabel_markers"]
        and int(evo.RelabelSorghumLsPlantingMarkersByRow(list(profile["row_labels"])))
        != 60
    ):
        raise RuntimeError("failed to apply the reference 6x10 planting plan")
    if int(evo.InstantiateSorghumLsPlantsFromPlantingMarkers()) != 60:
        raise RuntimeError("failed to instantiate the 60 SorghumLS planting markers")
    if int(evo.ConformSorghumLsPlantsToGroundMesh()) != 60:
        raise RuntimeError(
            "failed to conform the 60 SorghumLS plants to the field soil"
        )
    asset_descriptors = {
        genotype: path.relative_to(args.project_root / "Assets")
        for genotype, path in descriptors.items()
    }
    if int(evo.SetSorghumLsGenotypeDescriptors(asset_descriptors, False, -1)) != 60:
        raise RuntimeError("failed to assign the field descriptors")
    presentation = profile.get("panicle_presentation")
    if presentation and int(
        evo.ConfigureSorghumLsPaniclePresentation(
            presentation["peduncle_length_m"],
            presentation["rachis_length_m"],
            presentation["branch_length_m"],
            presentation["primary_branch_count"],
            presentation["spikelet_pairs_per_branch"],
            presentation["spikelet_length_m"],
            presentation["spikelet_radius_m"],
            *presentation["immature_color"],
            *presentation["mature_color"],
        )
    ) != 60:
        raise RuntimeError("failed to apply the separate A/B/C panicle presentation")
    if (
        int(
            evo.ConfigureSorghumLsLeafMeshQuality(
                FIELD_LEAF_VERTICAL_SUBDIVISION_M,
                FIELD_LEAF_HORIZONTAL_SUBDIVISIONS,
                False,
                True,
                False,
            )
        )
        != 60
    ):
        raise RuntimeError("failed to apply the render-only SorghumLS field leaf LOD")
    unique_descriptor_count = len(set(descriptors.values()))
    if (
        int(evo.SetSorghumLsFinalizeSnapshotMorphology(False))
        != unique_descriptor_count
    ):
        raise RuntimeError(
            "failed to disable static-snapshot finalization for the dynamic GDD timeline"
        )
    if not evo.EnsureIlluminationSoilContext() or not evo.ValidateIlluminationContext():
        raise RuntimeError("the established 2026 soil/illumination context is invalid")
    configure_lighting(evo)
    if set_ground_extension(evo, True) != 1:
        raise RuntimeError("failed to create the render-only field ground extension")


def configure_camera(
    evo: object,
    args: argparse.Namespace,
    descriptor_target_gdd: float,
    profile: dict[str, object],
) -> tuple[dict[str, object], float, float, float, dict[str, dict[str, float | int]]]:
    endpoint_gdd = descriptor_target_gdd
    first_evaluation = True
    maturity_floor = descriptor_target_gdd
    maximum_organ_delay_gdd = 0.0
    while endpoint_gdd <= descriptor_target_gdd * args.max_endpoint_multiplier + 1.0e-6:
        grow_to_gdd = (
            evo.GrowSorghumLsPlantsToGdd
            if first_evaluation
            else evo.AdvanceSorghumLsPlantsToGdd
        )
        if int(grow_to_gdd(endpoint_gdd, SEEDS[DESCRIPTOR_SESSION], True)) != 60:
            raise RuntimeError("failed to generate the final-state SorghumLS field")
        first_evaluation = False
        if not evo.WaitForProjectIdle(args.max_wait_frames):
            raise RuntimeError("final-state field did not become idle")
        records = list(evo.GetSorghumLsPlantSceneMetadata(True))
        validate_field(records, endpoint_gdd, profile, require_geometry=True)
        maturity_floor, maximum_organ_delay_gdd = maturity_floor_gdd(
            descriptor_target_gdd, records
        )
        phenology = summarize_phenology(records, profile)
        write_json(
            args.output_dir / "endpoint_preflight.json",
            {
                "gdd": endpoint_gdd,
                "maturity_floor_gdd": maturity_floor,
                "maximum_organ_delay_gdd": maximum_organ_delay_gdd,
                "phenology": phenology,
            },
        )
        try:
            validate_full_organ_maturity(phenology)
            if "minimum_panicle_canopy_clearance_m" in profile:
                validate_full_panicle_visibility(
                    phenology, float(profile["minimum_panicle_canopy_clearance_m"])
                )
            break
        except RuntimeError:
            endpoint_gdd = (
                maturity_floor
                if endpoint_gdd + 1.0e-6 < maturity_floor
                else endpoint_gdd + args.endpoint_gdd_step
            )
    else:
        validate_full_organ_maturity(phenology)
        if "minimum_panicle_canopy_clearance_m" in profile:
            validate_full_panicle_visibility(
                phenology, float(profile["minimum_panicle_canopy_clearance_m"])
            )
    print(
        json.dumps(
            {
                "gdd": endpoint_gdd,
                "maturity_floor_gdd": maturity_floor,
                "maximum_organ_delay_gdd": maximum_organ_delay_gdd,
                "phenology": phenology,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    camera = camera_for_view(
        geometry_bounds(records), args.camera_view, args.width / args.height
    )
    camera["view"] = args.camera_view
    position, target, up = (evo.Vec3(), evo.Vec3(), evo.Vec3())
    for vector, values in zip(
        (position, target, up), (camera["position"], camera["target"], camera["up"])
    ):
        vector.x, vector.y, vector.z = values
    if not evo.SetMainCameraLookAt(position, target, up, float(camera["fov_degrees"])):
        raise RuntimeError("failed to apply the fixed 6x10 field camera")
    return camera, endpoint_gdd, maturity_floor, maximum_organ_delay_gdd, phenology


def capture_state(
    evo: object,
    args: argparse.Namespace,
    output_dir: Path,
    state: int,
    target_gdd: float,
    profile: dict[str, object],
) -> dict[str, object]:
    gdd = state_gdd(state, target_gdd, args.state_count)
    frame = frame_path(output_dir, state)
    metadata = state_path(output_dir, state)
    expected = {
        "state": state,
        "state_count": args.state_count,
        "gdd": gdd,
        "target_gdd": target_gdd,
        "camera_view": args.camera_view,
        "panicle_parameter_policy": profile["panicle_parameter_policy"],
        "render_width": args.width,
        "render_height": args.height,
        "render_samples": args.samples,
        "render_bounces": args.bounces,
        "denoiser_strength": args.denoiser_strength,
    }
    if valid_cached_state(metadata, frame, expected):
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        if set(payload.get("phenology", {})) == set(profile["labels"]):
            payload["field_profile"] = profile["slug"]
            payload["frame"] = str(frame.resolve())
            write_json(metadata, payload)
            return payload

    if int(evo.AdvanceSorghumLsPlantsToGdd(gdd, SEEDS[DESCRIPTOR_SESSION], True)) != 60:
        raise RuntimeError(f"state {state}: failed to advance all 60 SorghumLS plants")
    if not evo.WaitForProjectIdle(args.max_wait_frames):
        raise RuntimeError(f"state {state}: geometry did not become idle")
    records = list(evo.GetSorghumLsPlantSceneMetadata(True))
    validate_field(records, gdd, profile)
    evo.LoopFrames(args.warmup_frames)
    raw = frame.with_name(f".{frame.stem}.raw.png")
    graded = frame.with_name(f".{frame.stem}.graded.png")
    frame.parent.mkdir(parents=True, exist_ok=True)
    capture_succeeded = False
    try:
        if not evo.CaptureCurrentSceneRayTraced(
            args.width,
            args.height,
            raw,
            args.samples,
            args.bounces,
            DEFAULT_PROFILE.gamma,
            args.denoiser_strength,
        ):
            raise RuntimeError(f"state {state}: OptiX capture failed")
        apply_photo_grade(raw, graded)
        metrics = image_metrics(graded)
        if metrics["luminance_stddev"] < 3.0:
            raise RuntimeError(f"state {state}: render appears blank or flat")
        graded.replace(frame)
        capture_succeeded = True
    finally:
        if capture_succeeded:
            raw.unlink(missing_ok=True)
            graded.unlink(missing_ok=True)
    payload = {
        **expected,
        "field_profile": profile["slug"],
        "frame": str(frame.resolve()),
        "frame_sha256": sha256(frame),
        "metrics": image_metrics(frame),
        "phenology": summarize_phenology(records, profile),
    }
    write_json(metadata, payload)
    return payload


def verify_state_outputs(
    output_dir: Path,
    states: tuple[int, ...],
    args: argparse.Namespace,
    target_gdd: float,
    profile: dict[str, object],
) -> list[dict[str, object]]:
    rows = []
    for state in states:
        gdd = state_gdd(state, target_gdd, args.state_count)
        frame = frame_path(output_dir, state)
        metadata = state_path(output_dir, state)
        expected = {
            "state": state,
            "state_count": args.state_count,
            "gdd": gdd,
            "target_gdd": target_gdd,
            "camera_view": args.camera_view,
            "panicle_parameter_policy": profile["panicle_parameter_policy"],
            "render_width": args.width,
            "render_height": args.height,
            "render_samples": args.samples,
            "render_bounces": args.bounces,
            "denoiser_strength": args.denoiser_strength,
        }
        if not valid_cached_state(metadata, frame, expected):
            raise RuntimeError(f"invalid state output: {state}")
        metrics = image_metrics(frame)
        if (
            metrics["size"] != [args.width, args.height]
            or metrics["luminance_stddev"] < 3.0
        ):
            raise RuntimeError(
                f"state {state}: rendered frame failed image verification"
            )
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        if set(payload.get("phenology", {})) != set(profile["labels"]):
            raise RuntimeError(
                f"state {state}: cached field profile does not match {profile['slug']}"
            )
        rows.append(payload)
    if args.state_count in states:
        validate_full_organ_maturity(rows[-1]["phenology"])
        if "minimum_panicle_canopy_clearance_m" in profile:
            validate_full_panicle_visibility(
                rows[-1]["phenology"],
                float(profile["minimum_panicle_canopy_clearance_m"]),
            )
    return rows


def require_video_tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required to assemble the time-lapse")
    return ffmpeg, ffprobe


def encode_video(
    output_dir: Path, args: argparse.Namespace, profile: dict[str, object], fps: int
) -> tuple[Path, dict[str, object]]:
    ffmpeg, ffprobe = require_video_tools()
    video = (
        output_dir / f"sorghum_2026_6x10_{profile['slug']}_full_lifecycle_{fps}fps.mp4"
    )
    temporary = video.with_name(f".{video.stem}.tmp.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-framerate",
            str(fps),
            "-i",
            str(output_dir / "frames" / FRAME_PATTERN),
            "-frames:v",
            str(args.state_count),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        check=True,
    )
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(temporary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    if (
        int(stream["width"]) != args.width
        or int(stream["height"]) != args.height
        or int(stream["nb_read_frames"]) != args.state_count
        or stream["r_frame_rate"] != f"{fps}/1"
    ):
        raise RuntimeError(
            "encoded time-lapse does not match the requested video specification"
        )
    temporary.replace(video)
    return video, info


def encode_videos(
    output_dir: Path, args: argparse.Namespace, profile: dict[str, object]
) -> list[dict[str, object]]:
    videos = []
    for fps in playback_rates(args.playback_fps):
        video, probe = encode_video(output_dir, args, profile, fps)
        videos.append(
            {
                "fps": fps,
                "duration_seconds": args.state_count / fps,
                "path": str(video.resolve()),
                "sha256": sha256(video),
                "probe": probe,
            }
        )
    return videos


def run(args: argparse.Namespace) -> Path:
    (args.output_dir / "failure.json").unlink(missing_ok=True)
    if args.state_count != STATE_COUNT:
        raise ValueError("the published 2026 timeline is fixed at 1,000 field states")
    if args.width <= 0 or args.height <= 0 or args.width % 2 or args.height % 2:
        raise ValueError("video dimensions must be positive and even")
    if (
        args.endpoint_gdd_step <= 0.0
        or args.max_endpoint_multiplier < 1.0
        or not 0.0 <= args.denoiser_strength <= 1.0
    ):
        raise ValueError(
            "endpoint GDD step, maximum multiplier, or denoiser strength is invalid"
        )
    profile = field_profile(args.field_profile)
    playback_rates(args.playback_fps)
    states = requested_states(args.states, args.state_count)
    if not args.no_video and states != tuple(range(1, args.state_count + 1)):
        raise ValueError("video assembly requires every state from 1 through 1,000")
    descriptors = descriptor_paths(args.project_root, profile)
    descriptor_target_gdd = shared_target_gdd(descriptors)
    source_hashes = {
        "project": sha256(args.project),
        "template_scene": sha256(args.project_root / "Assets" / TEMPLATE_SCENE),
        **{
            f"descriptor_{genotype}": sha256(path)
            for genotype, path in descriptors.items()
        },
    }
    source_semantic_hashes = {"project": normalized_text_sha256(args.project)}
    asset_snapshot = runtime_asset_snapshot(args.project_root, args.project)
    initial_side_effects = set(
        (args.project_root / "Assets").glob("New Scene*.evescene*")
    )
    build_dir = args.build_dir.resolve()
    configure_engine_imports(build_dir, args.config)
    os.chdir(build_dir / "PythonBinding" / args.config)
    import PyDigitalAgriculture as evo

    # The PyDigitalAgriculture runtime unloads its own package during
    # ``Terminate``.  Persist the self-contained deliverable before that
    # teardown; otherwise a successful render can leave frames on disk without
    # its manifest or assembled mobile video.
    try:
        initialize_field(evo, args, descriptors, profile)
        camera, target_gdd, maturity_floor, maximum_organ_delay_gdd, final_phenology = configure_camera(
            evo, args, descriptor_target_gdd, profile
        )
        for offset, state in enumerate(states, start=1):
            capture_state(evo, args, args.output_dir, state, target_gdd, profile)
            if offset % 25 == 0 or offset == len(states):
                print(
                    f"captured {offset}/{len(states)} SorghumLS field states",
                    flush=True,
                )
        rows = verify_state_outputs(args.output_dir, states, args, target_gdd, profile)

        for name, digest in source_hashes.items():
            source = (
                args.project
                if name == "project"
                else (
                    args.project_root / "Assets" / TEMPLATE_SCENE
                    if name == "template_scene"
                    else descriptors[name.removeprefix("descriptor_")]
                )
            )
            actual = (
                normalized_text_sha256(source) if name == "project" else sha256(source)
            )
            expected = source_semantic_hashes.get(name, digest)
            if actual != expected:
                raise RuntimeError(
                    f"rendering changed a scientific source asset: {source}"
                )
        videos = (
            encode_videos(args.output_dir, args, profile) if not args.no_video else []
        )
        report = {
            "schema_version": 3,
            "renderer": "EvoEngine_OptiX",
            "basis": profile["basis"],
            "field_profile": args.field_profile,
            "ownership": profile["ownership"],
            "experiment_id": EXPERIMENT_ID,
            "layout": {
                "rows": 6,
                "columns": 10,
                "row_labels": list(profile["row_labels"]),
                "plots": list(profile["plots"]),
                "plants_per_label": profile["plants_per_label"],
            },
            "descriptor_session": profile["descriptor_session"],
            "vegetative_descriptor_source": profile["vegetative_descriptor_source"],
            "panicle_parameter_policy": profile["panicle_parameter_policy"],
            "panicle_presentation": profile.get("panicle_presentation"),
            "descriptor_target_gdd": descriptor_target_gdd,
            "timeline_end_gdd": target_gdd,
            "endpoint_extension_gdd": target_gdd - descriptor_target_gdd,
            "maturity_floor_gdd": maturity_floor,
            "maximum_organ_delay_gdd": maximum_organ_delay_gdd,
            "final_panicle_emergence": {
                "required": 60,
                "observed": sum(
                    int(row["panicle_emerged_plants"])
                    for row in final_phenology.values()
                ),
                "status": "pass",
                "by_label": final_phenology,
            },
            "final_organ_maturity": {
                "required": 60,
                "vegetative_observed": sum(
                    int(row["vegetative_mature_plants"])
                    for row in final_phenology.values()
                ),
                "panicle_observed": sum(
                    int(row["panicle_mature_plants"])
                    for row in final_phenology.values()
                ),
                "whole_plant_observed": sum(
                    int(row["all_organs_mature_plants"])
                    for row in final_phenology.values()
                ),
                "status": "pass",
                "by_label": final_phenology,
            },
            "final_panicle_visibility": {
                "minimum_required_canopy_clearance_m": PANICLE_CANOPY_CLEARANCE_M,
                "minimum_observed_canopy_clearance_m": min(
                    float(row["minimum_panicle_canopy_clearance_m"])
                    for row in final_phenology.values()
                ),
                "status": "pass",
                "by_label": final_phenology,
            },
            "timeline": {
                "state_count": args.state_count,
                "state_1_gdd": state_gdd(1, target_gdd),
                "state_1000_gdd": state_gdd(args.state_count, target_gdd),
            },
            "render": {
                "width": args.width,
                "height": args.height,
                "samples": args.samples,
                "bounces": args.bounces,
                "denoiser_strength": args.denoiser_strength,
                "fixed_midday_profile": DEFAULT_PROFILE.to_dict(),
                "camera": camera,
                "field_leaf_lod": {
                    "vertical_subdivision_m": FIELD_LEAF_VERTICAL_SUBDIVISION_M,
                    "horizontal_subdivisions": FIELD_LEAF_HORIZONTAL_SUBDIVISIONS,
                    "bottom_face": False,
                    "leaf_sheath": True,
                },
            },
            "growth_execution": "camera framing replays the final state once; ordered field states advance from the prior GDD state",
            "captured_states": list(states),
            "milestone_frames": [
                str(frame_path(args.output_dir, state).resolve())
                for state in MILESTONE_STATES
                if state in states
            ],
            "states": rows,
            "source_sha256": source_hashes,
            "source_semantic_sha256": source_semantic_hashes,
            "scientific_scene_assets_modified": False,
            "videos": videos,
        }
        report_path = (
            args.output_dir / f"sorghum_2026_6x10_{profile['slug']}_full_lifecycle.json"
        )
        write_json(report_path, report)
        return report_path
    except Exception as error:
        write_json(
            args.output_dir / "failure.json",
            {
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        raise
    finally:
        set_ground_extension(evo, False)
        restore_runtime_assets(asset_snapshot, args.project_root, initial_side_effects)


def build_parser() -> argparse.ArgumentParser:
    root = repo_root_from_script()
    project_root = root / "Resources" / "DigitalAgricultureProject"
    build_dir = root / "out" / "build" / "vs2026-x64"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument(
        "--project", type=Path, default=project_root / "test_lsystem_sorghum.eveproj"
    )
    parser.add_argument("--build-dir", type=Path, default=build_dir)
    parser.add_argument("--config", default="Debug")
    parser.add_argument(
        "--runtime-package-dir",
        type=Path,
        default=build_dir / "EvoEngine_App/Debug/Packages",
    )
    parser.add_argument(
        "--field-profile", choices=FIELD_PROFILES, default=DEFAULT_FIELD_PROFILE
    )
    parser.add_argument(
        "--camera-view",
        choices=CAMERA_VIEWS,
        default="perspective",
        help="fixed lifecycle camera; the default shows mature, exserted panicles above the canopy",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root
        / "out/panicle_timelapse/sorghum_2026_6x10_abc_btx_vegetative_full_lifecycle_1000_native_1080p",
    )
    parser.add_argument("--state-count", type=int, default=STATE_COUNT)
    parser.add_argument(
        "--states", help="comma-separated state numbers for a no-video smoke render"
    )
    # Match the established mobile-ready 4x10 delivery format.  The lower
    # resolution mode remains available explicitly for smoke tests.
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument(
        "--playback-fps", default=",".join(str(value) for value in PLAYBACK_FPS)
    )
    parser.add_argument("--endpoint-gdd-step", type=float, default=20.0)
    parser.add_argument("--max-endpoint-multiplier", type=float, default=2.0)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--bounces", type=int, default=2)
    parser.add_argument("--denoiser-strength", type=float, default=0.0)
    parser.add_argument("--warmup-frames", type=int, default=1)
    parser.add_argument("--max-wait-frames", type=int, default=30000)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def valid_worker_report(
    args: argparse.Namespace, started_at: float
) -> tuple[Path, dict[str, object]] | None:
    profile = field_profile(args.field_profile)
    report_path = (
        args.output_dir / f"sorghum_2026_6x10_{profile['slug']}_full_lifecycle.json"
    )
    if not report_path.is_file() or report_path.stat().st_mtime < started_at - 1.0:
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    states = requested_states(args.states, args.state_count)
    final = report.get("final_panicle_emergence", {})
    maturity = report.get("final_organ_maturity", {})
    visibility = report.get("final_panicle_visibility", {})
    required_clearance = profile.get("minimum_panicle_canopy_clearance_m")
    if (
        report.get("field_profile") != args.field_profile
        or report.get("captured_states") != list(states)
        or final.get("observed") != 60
        or final.get("status") != "pass"
        or maturity.get("vegetative_observed") != 60
        or maturity.get("panicle_observed") != 60
        or maturity.get("whole_plant_observed") != 60
        or maturity.get("status") != "pass"
        or (
            required_clearance is not None
            and (
                visibility.get("status") != "pass"
                or float(visibility.get("minimum_observed_canopy_clearance_m", -1.0))
                < float(required_clearance)
            )
        )
    ):
        return None
    try:
        verify_state_outputs(
            args.output_dir,
            states,
            args,
            float(report["timeline_end_gdd"]),
            profile,
        )
        descriptors = descriptor_paths(args.project_root, profile)
        sources = {
            "project": args.project,
            "template_scene": args.project_root / "Assets" / TEMPLATE_SCENE,
            **{f"descriptor_{label}": path for label, path in descriptors.items()},
        }
        if any(
            sha256(path) != report.get("source_sha256", {}).get(name)
            for name, path in sources.items()
        ):
            return None
    except (KeyError, OSError, TypeError, ValueError, RuntimeError):
        return None
    videos = report.get("videos", [])
    if not args.no_video and {
        int(video.get("fps", -1))
        for video in videos
        if Path(str(video.get("path", ""))).is_file()
        and sha256(Path(str(video["path"]))) == video.get("sha256")
    } != set(playback_rates(args.playback_fps)):
        return None
    return report_path, report


def main() -> None:
    args = build_parser().parse_args()
    args.project_root = args.project_root.resolve()
    args.project = args.project.resolve()
    args.build_dir = args.build_dir.resolve()
    args.runtime_package_dir = args.runtime_package_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.worker:
        print(run(args))
        sys.stdout.flush()
        sys.stderr.flush()
        return

    asset_snapshot = runtime_asset_snapshot(args.project_root, args.project)
    initial_side_effects = set(
        (args.project_root / "Assets").glob("New Scene*.evescene*")
    )
    started_at = time.time()
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", *sys.argv[1:]],
            check=False,
        )
    finally:
        restore_runtime_assets(asset_snapshot, args.project_root, initial_side_effects)
    result = valid_worker_report(args, started_at)
    if result is None:
        raise RuntimeError(
            f"native render worker exited {completed.returncode} without a valid report"
        )
    report_path, report = result
    report["worker_exit_status"] = completed.returncode
    if completed.returncode:
        report["worker_teardown_warning"] = (
            "OptiX worker exited after the completed report was flushed; all states, "
            "panicles, source hashes, and videos were validated by the parent process."
        )
    write_json(report_path, report)
    print(report_path.resolve())


if __name__ == "__main__":
    main()
