import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import open3d as o3d


def obj_face_groups(path):
    groups = []
    current = "branch"
    count = 0
    with path.open("r", encoding="ascii", errors="ignore") as source:
        for line in source:
            if line.startswith("o "):
                if count:
                    groups.append((current, count))
                current = line.split(maxsplit=1)[1].strip().split()[0].lower()
                count = 0
            elif line.startswith("f "):
                count += 1
    if count:
        groups.append((current, count))
    return groups


def sample_mesh_parts(path, point_count):
    mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=False)
    triangles = np.asarray(mesh.triangles)
    groups = obj_face_groups(path)
    if sum(count for _, count in groups) != len(triangles):
        raise ValueError(f"OBJ triangle count changed while loading {path}")

    parts = []
    offset = 0
    for name, face_count in groups:
        part = o3d.geometry.TriangleMesh()
        part.vertices = mesh.vertices
        part.triangles = o3d.utility.Vector3iVector(triangles[offset : offset + face_count])
        part.remove_unreferenced_vertices()
        area = part.get_surface_area()
        if area > 0:
            parts.append((name, part, area))
        offset += face_count

    total_area = sum(area for _, _, area in parts)
    sampled = []
    remaining = point_count
    for index, (name, part, area) in enumerate(parts):
        count = remaining if index == len(parts) - 1 else max(1, round(point_count * area / total_area))
        remaining -= count
        points = np.asarray(part.sample_points_uniformly(number_of_points=count).points, dtype=np.float32)
        sampled.append((name, points))
    return sampled


def write_scanner_ply(path, point_blocks, type_blocks, instance_blocks):
    points = np.concatenate(point_blocks).astype("<f4", copy=False)
    types = np.concatenate(type_blocks).astype("<i4", copy=False)
    instances = np.concatenate(instance_blocks).astype("<i4", copy=False)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        f"element type_index {len(points)}\nproperty int type_index\n"
        f"element instance_index {len(points)}\nproperty int instance_index\n"
        "end_header\n"
    ).encode("ascii")
    with path.open("wb") as output:
        output.write(header)
        output.write(points.tobytes())
        output.write(types.tobytes())
        output.write(instances.tobytes())


def ground_height_filter(points, raycasting_scene, ray_origin_y):
    rays = np.zeros((len(points), 6), dtype=np.float32)
    rays[:, 0] = points[:, 0]
    rays[:, 1] = ray_origin_y
    rays[:, 2] = points[:, 2]
    rays[:, 4] = -1.0
    hit_distance = raycasting_scene.cast_rays(o3d.core.Tensor(rays))["t_hit"].numpy()
    ground_height = ray_origin_y - hit_distance
    return np.isinf(hit_distance) | (points[:, 1] >= ground_height - 0.005)


def main():
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(description="Uniformly sample scene OBJ surfaces without visibility occlusion.")
    parser.add_argument("--scene", default="AlleyTreeScene", help="Scene name under out/, or an output directory.")
    parser.add_argument("--tree-points", type=int, default=100_000, help="Points sampled per tree.")
    parser.add_argument("--bush-points", type=int, default=75_000, help="Points sampled per bush.")
    parser.add_argument("--ground-points", type=int, default=500_000)
    parser.add_argument("--building-points", type=int, default=100_000, help="Points sampled per building.")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--timing", action="store_true", help="Print the total sampling runtime.")
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[2]
    scene_directory = Path(args.scene)
    if not scene_directory.is_dir():
        scene_directory = repository / "out" / args.scene
    scene_directory = scene_directory.resolve()
    maps = list(scene_directory.glob("*_object_ids.json"))
    if len(maps) != 1:
        raise FileNotFoundError(f"Expected one *_object_ids.json in {scene_directory}")
    object_map = json.loads(maps[0].read_text(encoding="utf-8"))
    scene_name = maps[0].name.removesuffix("_object_ids.json")
    ground_path = scene_directory / f"{scene_name}_ground.obj"
    if not ground_path.exists():
        raise FileNotFoundError(f"{ground_path} is missing; rerun the scene generator with the rebuilt binding.")
    ground_mesh = o3d.io.read_triangle_mesh(str(ground_path), enable_post_processing=False)
    raycasting_scene = o3d.t.geometry.RaycastingScene()
    raycasting_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(ground_mesh))
    ray_origin_y = float(np.asarray(ground_mesh.vertices)[:, 1].max() + 1.0)

    o3d.utility.random.seed(args.seed)
    point_blocks, type_blocks, instance_blocks = [], [], []
    plant_files = sorted((scene_directory / "individual_plants").glob("ID*.obj"))
    for path in plant_files:
        object_id = int(re.match(r"ID(\d+)", path.name).group(1))
        metadata = object_map[str(object_id)]
        kind = metadata.get("kind", "bush" if "Bush" in metadata["name"] else "tree")
        count = args.bush_points if kind == "bush" else args.tree_points
        translation = np.array(
            [metadata.get("x", 0.0), metadata.get("y", 0.0), metadata.get("z", 0.0)], dtype=np.float32
        )
        print(f"Sampling {path.name}: {count:,} points")
        for part_name, points in sample_mesh_parts(path, count):
            points += translation
            if kind == "bush":
                points = points[ground_height_filter(points, raycasting_scene, ray_origin_y)]
            type_index = 1 if part_name.startswith("foliage") else 0
            point_blocks.append(points)
            type_blocks.append(np.full(len(points), type_index, dtype=np.int32))
            instance_blocks.append(np.full(len(points), object_id, dtype=np.int32))

    for _, points in sample_mesh_parts(ground_path, args.ground_points):
        point_blocks.append(points)
        type_blocks.append(np.full(len(points), 2, dtype=np.int32))
        instance_blocks.append(np.full(len(points), 1000, dtype=np.int32))

    for path in sorted((scene_directory / "buildings").glob("ID*.obj")):
        object_id = int(re.match(r"ID(\d+)", path.name).group(1))
        for _, points in sample_mesh_parts(path, args.building_points):
            point_blocks.append(points)
            type_blocks.append(np.full(len(points), 3, dtype=np.int32))
            instance_blocks.append(np.full(len(points), object_id, dtype=np.int32))

    output_path = scene_directory / f"{scene_name}_geometry_sampled.ply"
    write_scanner_ply(output_path, point_blocks, type_blocks, instance_blocks)
    print(f"Wrote {sum(map(len, point_blocks)):,} unoccluded points to {output_path}")
    if args.timing:
        print(f"Geometry sampling finished in {(time.perf_counter() - start_time) / 60.0:.2f} minutes.")


if __name__ == "__main__":
    main()
