from __future__ import annotations

from types import SimpleNamespace

from sorghum_validate_gpu_field_geometry import counter_delta, scene_snapshot, snapshot_digest


def record(name: str, height: float, grow_seconds: float) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        cultivar="BTX",
        local_position=(0.0, 0.0, 0.0),
        global_position=(0.0, 0.0, 0.0),
        geometry_min_position=(-1.0, 0.0, -1.0),
        geometry_max_position=(1.0, height, 1.0),
        leaf_count=2,
        main_culm_leaf_count=2,
        tiller_leaf_count=0,
        primary_tiller_count=0,
        geometry_snapshot_schema_version=1,
        geometry_snapshot_organ_count=3,
        leaf_vertex_count=100,
        leaf_triangle_count=50,
        culm_vertex_count=20,
        culm_triangle_count=10,
        leaf_width_scale=1.0,
        leaf_thickness_m=0.001,
        plant_height_m=height,
        leaf_area_m2=0.5,
        has_geometry=True,
        last_grow_seconds=grow_seconds,
        axes=[
            SimpleNamespace(
                axis_id=0,
                origin_rank=0,
                leaf_count=2,
                internode_count=2,
                origin_height_m=0.0,
                culm_tip_height_m=height,
            )
        ],
    )


def test_snapshot_is_ordered_and_excludes_timing() -> None:
    first = scene_snapshot([record("plant-b", 2.0, 9.0), record("plant-a", 1.0, 1.0)])
    second = scene_snapshot([record("plant-a", 1.0, 99.0), record("plant-b", 2.0, 0.0)])
    assert first == second
    assert snapshot_digest(first) == snapshot_digest(second)


def test_digest_changes_with_geometry() -> None:
    assert snapshot_digest(scene_snapshot([record("plant", 1.0, 0.0)])) != snapshot_digest(
        scene_snapshot([record("plant", 1.1, 0.0)])
    )


def test_counter_delta_is_named() -> None:
    assert counter_delta([2, 3, 5, 7], [11, 16, 21, 27]) == {
        "gas_builds": 9,
        "gas_updates": 13,
        "ias_builds": 16,
        "ias_updates": 20,
    }
