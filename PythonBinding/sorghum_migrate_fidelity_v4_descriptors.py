#!/usr/bin/env python3
"""Migrate the promoted sorghum descriptors to the current morphology contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Resources" / "DigitalAgricultureProject" / "Assets"
DESCRIPTORS = ASSETS / "GeneratedAssets" / "Descriptors"
MANUAL = ASSETS / "ManualAssets" / "Descriptors"

STAGES = {
    "GrowthStage01": (0.0120, 0.0800, 0.00030, 0.00015),
    "GrowthStage02": (0.0135, 0.0950, 0.00035, 0.00020),
    "GrowthStage03": (0.0150, 0.1100, 0.00045, 0.00030),
    "GrowthStage04": (0.0165, 0.1260, 0.00050, 0.00040),
    "GrowthStage05": (0.0165, 0.1260, 0.00045, 0.00045),
}

LEAF_MAX_LENGTH_M = {
    "GrowthStage01": {"BTX": 0.597166, "Pawaga": 0.423345},
    "GrowthStage02": {"BTX": 0.7520, "Pawaga": 0.6350},
    "GrowthStage03": {"BTX": 1.0872, "Pawaga": 1.1111},
    "GrowthStage04": {"BTX": 1.1869, "Pawaga": 1.4282},
    "GrowthStage05": {"BTX": 1.0865, "Pawaga": 1.2808},
}

PLASTOCHRON_GDD = 30.0
MATURITY_GDD = 240.0
LATERAL_AXIS_PLASTOCHRON_SCALE = 0.6
TILLER_SAME_SIDE_SPLAY_DEGREES = 12.0
TARGET_GDD_BY_STAGE = {
    "GrowthStage01": 512.0,
    "GrowthStage02": 580.0,
    "GrowthStage03": 642.0,
    "GrowthStage04": 660.0,
    "GrowthStage05": 666.0,
}
LEAF_DAMAGE_BY_STAGE = {
    "GrowthStage01": (0.0, 0.0),
    "GrowthStage02": (0.0, 0.0),
    "GrowthStage03": (0.015, 0.015),
    "GrowthStage04": (0.030, 0.020),
    "GrowthStage05": (0.040, 0.025),
}

LEAF_LENGTH_RANK_PROFILE = [
    (0.0, 0.366),
    (0.2, 0.504),
    (0.4, 0.742),
    (0.6, 0.952),
    (0.7, 1.0),
    (0.8, 0.84),
    (0.9, 0.58),
    (1.0, 0.30),
]

LEAF_WIDTH_RANK_PROFILE = [
    (0.0, 0.228),
    (0.2, 0.387),
    (0.4, 0.548),
    (0.6, 0.773),
    (0.7, 0.914),
    (0.8, 1.0),
    (0.9, 0.92),
    (1.0, 0.75),
]

LEAF_PROFILES = {
    "BTX": {
        "insertion": (0.0, 42.0, [(0.0, 0.65), (0.2, 0.57), (0.4, 0.47), (0.6, 0.34), (0.78, 0.20), (0.9, 0.08), (1.0, 0.0)], 5.0),
        "bending": (0.0, 150.0, [(0.0, 0.75), (0.2, 0.72), (0.45, 0.65), (0.68, 0.50), (0.86, 0.18), (1.0, 0.0)], 15.0),
        "bending_along": [(0.0, 0.0), (0.3, 0.0), (0.5, 0.015), (0.7, 0.18), (0.88, 0.60), (1.0, 1.0)],
    },
    "Pawaga": {
        "insertion": (0.0, 70.0, [(0.0, 0.82), (0.2, 0.78), (0.4, 0.67), (0.6, 0.52), (0.78, 0.34), (0.9, 0.14), (1.0, 0.0)], 8.0),
        "bending": (0.0, 100.0, [(0.0, 0.65), (0.2, 0.68), (0.45, 0.62), (0.68, 0.48), (0.86, 0.25), (1.0, 0.0)], 16.0),
        "bending_along": [(0.0, 0.0), (0.3, 0.0), (0.5, 0.026), (0.7, 0.20), (0.88, 0.62), (1.0, 1.0)],
    },
}


def plotted(name: str, value: float) -> str:
    formatted = f"{value:.8g}"
    return f"""{name}:
  mean:
    min_value: {formatted}
    max_value: {formatted}
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
        - [0, 0.5]
        - [1, 0.5]
  deviation:
    min_value: 0
    max_value: 0
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
        - [0, 0]
        - [1, 0]
"""


def curve_plotted(
    name: str,
    minimum: float,
    maximum: float,
    points: list[tuple[float, float]],
    deviation_maximum: float = 0.0,
    deviation_points: list[tuple[float, float]] | None = None,
) -> str:
    deviation_points = deviation_points or [(0.0, 0.5), (0.85, 0.35), (1.0, 0.0)]

    def values(items: list[tuple[float, float]]) -> str:
        return "\n".join(f"        - [{x:.8g}, {y:.8g}]" for x, y in items)

    return f"""{name}:
  mean:
    min_value: {minimum:.8g}
    max_value: {maximum:.8g}
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
{values(points)}
  deviation:
    min_value: 0
    max_value: {deviation_maximum:.8g}
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
{values(deviation_points)}
"""


def tapered_plotted(name: str, basal: float, tip: float) -> str:
    return f"""{name}:
  mean:
    min_value: {tip:.8g}
    max_value: {basal:.8g}
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
        - [0, 1]
        - [0.6, 1]
        - [1, 0]
  deviation:
    min_value: 0
    max_value: 0
    curve:
      tangent_: false
      min_: [0, 0]
      max_: [1, 1]
      values_:
        - [0, 0]
        - [1, 0]
"""


def single(name: str, mean: float, deviation: float = 0.0) -> str:
    return f"{name}:\n  mean: {mean:.8g}\n  deviation: {deviation:.8g}\n"


def replace_block(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(name)}:.*?(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)")
    if not pattern.search(text):
        raise ValueError(f"missing descriptor field: {name}")
    return pattern.sub(replacement, text, count=1)


def insert_after(text: str, name: str, addition: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(name)}:\n.*?(?=^[A-Za-z_][A-Za-z0-9_]*:|\Z)")
    match = pattern.search(text)
    if not match:
        match = re.search(rf"(?m)^{re.escape(name)}:.*\n", text)
    if not match:
        raise ValueError(f"missing descriptor field: {name}")
    return text[: match.end()] + addition + text[match.end() :]


def upsert_after(text: str, name: str, field: str, block: str) -> str:
    return replace_block(text, field, block) if re.search(rf"(?m)^{re.escape(field)}:", text) else insert_after(text, name, block)


def scalar(text: str, name: str, value: str, after: str) -> str:
    line = f"{name}: {value}\n"
    if re.search(rf"(?m)^{re.escape(name)}:", text):
        return re.sub(rf"(?m)^{re.escape(name)}:.*$", line.rstrip(), text)
    return insert_after(text, after, line)


def asset_ref(name: str, handle: int) -> str:
    return f'{name}:\n  asset_handle_: {handle}\n  type_name_: Texture2D\n'


def migrate(
    path: Path,
    values: tuple[float, float, float, float],
    stage: str | None = None,
    finalize_snapshot: bool = False,
    leaf_length_mean_scale: float = 1.0,
    leaf_length_deviation_scale: float = 1.0,
) -> None:
    diameter, blade_width, blade_thickness, sheath_thickness = values
    stage = stage or next(name for name, stage_values in STAGES.items() if stage_values == values)
    cultivar = path.stem
    text = path.read_text(encoding="utf-8")
    text = replace_block(text, "internode_thickness", tapered_plotted("internode_thickness", diameter, diameter * 0.8))
    blade_length = LEAF_MAX_LENGTH_M[stage][cultivar] * leaf_length_mean_scale
    text = replace_block(
        text,
        "leaf_blade_length",
        curve_plotted(
            "leaf_blade_length",
            0.0,
            blade_length,
            LEAF_LENGTH_RANK_PROFILE,
            blade_length * 0.2 * leaf_length_deviation_scale,
            [(0.0, 0.5), (1.0, 0.5)],
        ),
    )
    text = replace_block(
        text,
        "leaf_blade_max_width",
        curve_plotted(
            "leaf_blade_max_width",
            0.0,
            blade_width,
            LEAF_WIDTH_RANK_PROFILE,
            blade_width * 0.18,
            [(0.0, 0.5), (1.0, 0.5)],
        ),
    )
    text = upsert_after(
        text,
        "leaf_blade_max_width",
        "leaf_blade_thickness",
        plotted("leaf_blade_thickness", blade_thickness),
    )
    text = upsert_after(text, "leaf_blade_thickness", "leaf_sheath_thickness", plotted("leaf_sheath_thickness", sheath_thickness))
    text = re.sub(r"(?m)^leaf_width_scale:.*$", "leaf_width_scale: 1", text)
    profile = LEAF_PROFILES[cultivar]
    text = replace_block(text, "leaf_insertion_angle", curve_plotted("leaf_insertion_angle", *profile["insertion"]))
    text = replace_block(text, "leaf_bending", curve_plotted("leaf_bending", *profile["bending"]))
    text = replace_block(
        text,
        "leaf_waviness",
        curve_plotted(
            "leaf_waviness",
            0.0,
            0.0025,
            [(0.0, 0.55), (0.25, 0.8), (0.55, 1.0), (0.8, 0.85), (1.0, 0.5)],
            0.0008,
            [(0.0, 0.5), (1.0, 0.5)],
        ),
    )
    text = replace_block(text, "leaf_waviness_frequency", single("leaf_waviness_frequency", 3.0, 0.75))
    text = upsert_after(
        text,
        "leaf_waviness_frequency",
        "leaf_waviness_width_fraction",
        curve_plotted(
            "leaf_waviness_width_fraction",
            0.0,
            0.24,
            [(0.0, 0.45), (0.25, 0.75), (0.55, 0.85), (0.8, 0.65), (1.0, 0.35)],
            0.04,
            [(0.0, 0.5), (1.0, 0.5)],
        ),
    )
    text = upsert_after(text, "leaf_waviness_width_fraction", "leaf_waviness_wavelength_m", single("leaf_waviness_wavelength_m", 0.16, 0.02))
    text = upsert_after(
        text,
        "leaf_waviness_wavelength_m",
        "leaf_centerline_waviness_fraction",
        single("leaf_centerline_waviness_fraction", 0.008, 0.003),
    )
    text = upsert_after(
        text,
        "leaf_centerline_waviness_fraction",
        "leaf_static_wind_deflection_fraction",
        single("leaf_static_wind_deflection_fraction", 0.018, 0.006),
    )
    if re.search(r"(?m)^leaf_static_twist_degrees:", text):
        text = replace_block(text, "leaf_static_twist_degrees", "")
    text = upsert_after(
        text,
        "leaf_static_wind_deflection_fraction",
        "leaf_axial_twist_max_degrees",
        single("leaf_axial_twist_max_degrees", 30.0),
    )
    text = upsert_after(
        text,
        "leaf_axial_twist_max_degrees",
        "leaf_axial_twist_frequency_ratio_min",
        single("leaf_axial_twist_frequency_ratio_min", 0.35),
    )
    text = upsert_after(
        text,
        "leaf_axial_twist_frequency_ratio_min",
        "leaf_axial_twist_frequency_ratio_max",
        single("leaf_axial_twist_frequency_ratio_max", 0.5),
    )
    text = upsert_after(
        text,
        "leaf_axial_twist_frequency_ratio_max",
        "leaf_gravity_droop_compliance",
        single("leaf_gravity_droop_compliance", 0.02),
    )
    text = upsert_after(
        text,
        "leaf_gravity_droop_compliance",
        "leaf_gravity_droop_age_response",
        curve_plotted(
            "leaf_gravity_droop_age_response",
            0.0,
            1.0,
            [(0.0, 0.0), (0.45, 0.0), (0.65, 0.15), (0.82, 0.55), (1.0, 1.0)],
            0.0,
            [(0.0, 0.0), (1.0, 0.0)],
        ),
    )
    text = upsert_after(
        text,
        "leaf_gravity_droop_age_response",
            "leaf_flexural_stiffness_along_leaf",
            curve_plotted(
                "leaf_flexural_stiffness_along_leaf",
            0.02,
            1.0,
            [(0.0, 1.0), (0.3, 0.90), (0.6, 0.60), (0.82, 0.30), (1.0, 0.0)],
            0.0,
            [(0.0, 0.0), (1.0, 0.0)],
        ),
    )
    damage_mean, damage_deviation = LEAF_DAMAGE_BY_STAGE[stage]
    text = upsert_after(
        text,
        "leaf_flexural_stiffness_along_leaf",
        "leaf_damage_severity",
        single("leaf_damage_severity", damage_mean, damage_deviation),
    )
    text = replace_block(text, "leaf_sheath_radius_ratio", single("leaf_sheath_radius_ratio", 1.05))
    text = upsert_after(
        text,
        "leaf_sheath_radius_ratio",
        "leaf_sheath_cross_section_ratio",
        single("leaf_sheath_cross_section_ratio", 1.40, 0.08),
    )
    text = upsert_after(text, "leaf_sheath_radius_ratio", "leaf_sheath_wrap_angle", single("leaf_sheath_wrap_angle", 390.0))
    text = upsert_after(
        text,
        "branch_azimuth_offset",
        "main_culm_lean_angle",
        single("main_culm_lean_angle", 6.8, 4.0),
    )
    text = re.sub(r"(?m)^tiller_model_version:.*$", "tiller_model_version: 4", text)
    text = replace_block(text, "tiller_final_lean_angle", single("tiller_final_lean_angle", 10.0, 4.0))
    text = replace_block(text, "tiller_azimuth_jitter", single("tiller_azimuth_jitter", 0.0, 10.0))
    text = upsert_after(
        text,
        "tiller_azimuth_jitter",
        "tiller_same_side_splay_angle",
        single("tiller_same_side_splay_angle", TILLER_SAME_SIDE_SPLAY_DEGREES),
    )
    text = re.sub(r"(?m)^tiller_recovery_phytomer_count:.*\n", "", text)
    text = scalar(text, "tiller_recovery_axis_fraction", "1", "tiller_same_side_splay_angle")
    text = scalar(text, "culm_radial_segments", "24", "stem_material_specular")
    text = scalar(text, "culm_node_radius_scale", "1.08", "culm_radial_segments")
    text = scalar(text, "culm_texture_repeat_m", "0.25", "culm_node_radius_scale")
    text = replace_block(text, "target_gdd", single("target_gdd", TARGET_GDD_BY_STAGE[stage]))
    text = replace_block(text, "plastochron_gdd", single("plastochron_gdd", PLASTOCHRON_GDD))
    text = replace_block(text, "maturity_gdd", single("maturity_gdd", MATURITY_GDD))
    text = replace_block(
        text,
        "lateral_axis_plastochron_scale",
        single("lateral_axis_plastochron_scale", LATERAL_AXIS_PLASTOCHRON_SCALE),
    )
    text = replace_block(text, "reference_maturity_gdd", single("reference_maturity_gdd", MATURITY_GDD))
    text = scalar(
        text,
        "finalize_snapshot_morphology",
        str(finalize_snapshot).lower(),
        "reference_maturity_gdd",
    )
    text = replace_block(
        text,
        "bending_along_leaf",
        curve_plotted(
            "bending_along_leaf",
            0.0,
            1.0,
            profile["bending_along"],
            0.0,
            [(0.0, 0.0), (1.0, 0.0)],
        ),
    )
    text = replace_block(
        text,
        "waviness_along_leaf",
        curve_plotted(
            "waviness_along_leaf",
            0.0,
            1.0,
            [(0.0, 0.0), (0.08, 0.45), (0.25, 0.9), (0.55, 1.0), (0.8, 0.9), (1.0, 0.45)],
            0.0,
            [(0.0, 0.0), (1.0, 0.0)],
        ),
    )
    text = replace_block(text, "leaf_material_albedo_color", "leaf_material_albedo_color: [1, 1, 1]\n")
    text = scalar(text, "leaf_material_subsurface_factor", "0", "leaf_material_specular")
    text = scalar(text, "leaf_material_subsurface_color", "[0.26, 0.52, 0.18]", "leaf_material_subsurface_factor")
    text = scalar(text, "leaf_material_subsurface_radius", "[0.001, 0.001, 0.001]", "leaf_material_subsurface_color")
    text = replace_block(text, "stem_material_albedo_color", "stem_material_albedo_color: [1, 1, 1]\n")
    handles = {
        "stem_albedo_texture": 11677113829394799981,
        "stem_normal_texture": 15939859271237366179,
        "stem_roughness_texture": 13467941576064353144,
        "stem_metallic_texture": 7946515516638111996,
        "stem_ao_texture": 9007124116920053463,
    }
    anchor = "leaf_material_specular"
    for field, handle in handles.items():
        text = upsert_after(text, anchor, field, asset_ref(field, handle))
        anchor = field
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    for stage, values in STAGES.items():
        for cultivar in ("BTX", "Pawaga"):
            migrate(DESCRIPTORS / stage / f"{cultivar}.sorghumls", values, stage, finalize_snapshot=True)
    manual_values = (0.0210, 0.1260, 0.00050, 0.00040)
    for cultivar in ("BTX", "Pawaga"):
        migrate(MANUAL / f"{cultivar}.sorghumls", manual_values, "GrowthStage04", finalize_snapshot=True)
    for root in (ASSETS / "ManualAssets" / "Scenes", ASSETS / "GeneratedAssets" / "Scenes"):
        for scene in root.glob("*.evescene"):
            text = re.sub(r"(?m)^\s+leaf_thickness:.*\n", "", scene.read_text(encoding="utf-8"))
            scene.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
