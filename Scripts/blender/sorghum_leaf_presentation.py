"""Pure policy helpers for presentation-only sorghum leaf deformation."""

from __future__ import annotations


ATLAS_ROWS = 3
DISTAL_REGION_MINIMUM = 0.50
BLADE_TIP_MINIMUM = 0.90
JUNCTION_WELD_DISTANCE_M = 1.0e-6


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def local_atlas_v(value: float, rows: int = ATLAS_ROWS) -> float:
    scaled = float(value) * rows
    return scaled - int(scaled)


def is_blade_component(local_minimum: float, local_maximum: float) -> bool:
    """Select only the blade, never the sheath or short neck component."""

    return local_minimum >= DISTAL_REGION_MINIMUM and local_maximum >= BLADE_TIP_MINIMUM


def global_component_is_blade(minimum: float, maximum: float, rows: int = ATLAS_ROWS) -> bool:
    return is_blade_component(local_atlas_v(minimum, rows), local_atlas_v(maximum, rows))


def blade_bend_weight(
    value: float,
    minimum: float,
    maximum: float,
    bend_start: float,
) -> float:
    span = max(1.0e-9, float(maximum) - float(minimum))
    longitudinal = (float(value) - float(minimum)) / span
    denominator = max(1.0e-9, 1.0 - float(bend_start))
    return smoothstep((longitudinal - float(bend_start)) / denominator)
