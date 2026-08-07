import argparse
import ctypes
import json
import os
import random
import secrets
import sys
import sysconfig
import time
from pathlib import Path

from _tree_scene_layout import place_double_tree_pairs, select_large_spruce_indices

total_start_time = time.perf_counter()
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentProcess.restype = ctypes.c_void_p
kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
kernel32.TerminateProcess.restype = ctypes.c_int

file_path = Path(__file__).resolve()
file_folder = file_path.parent
evoengine_directory = file_path.parents[2]
scene_kind = os.environ.get("ECOSYSLAB_SCENE_KIND")
if scene_kind not in {"alley", "dense_park", "sparse_park"}:
    raise ValueError("ECOSYSLAB_SCENE_KIND must be alley, dense_park, or sparse_park.")


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


argument_parser = argparse.ArgumentParser()
argument_parser.add_argument("--seed", type=int, help="Reproduce scene geometry; omitted means a new random scene.")
argument_parser.add_argument("--scene-index", type=int, help="Batch scene index used to create a distinct output folder.")
argument_parser.add_argument("--timing", action="store_true", help="Print and save detailed stage runtimes.")
argument_parser.add_argument("--bush-count-min", type=positive_int, default=5)
argument_parser.add_argument("--bush-count-max", type=positive_int, default=8)
argument_parser.add_argument("--bush-visible-height-min", type=positive_float, default=1.0)
argument_parser.add_argument("--bush-visible-height-max", type=positive_float, default=1.625)
argument_parser.add_argument("--large-spruce-min", type=nonnegative_int, default=2)
argument_parser.add_argument("--large-spruce-max", type=nonnegative_int, default=3)
argument_parser.add_argument("--tall-conifer-height", type=positive_float, default=10.0)
argument_parser.add_argument("--double-tree-pair-min", type=nonnegative_int, default=1)
argument_parser.add_argument("--double-tree-pair-max", type=nonnegative_int, default=2)
argument_parser.add_argument("--double-tree-distance-min", type=positive_float, default=0.25)
argument_parser.add_argument("--double-tree-distance-max", type=positive_float, default=0.45)
argument_parser.add_argument(
    "--tls-station-count",
    type=positive_int,
    help="Fixed TLS scan count; omitted randomly selects 5-10 stations.",
)
argument_parser.add_argument("--tls-height", type=positive_float, default=1.6)
argument_parser.add_argument("--tls-angular-step", type=positive_float, default=0.04)
argument_parser.add_argument("--tls-sector-width", type=positive_float, default=30.0)
argument_parser.add_argument("--tls-max-depth", type=positive_float, default=70.0)
arguments = argument_parser.parse_args()
if arguments.bush_count_min > arguments.bush_count_max:
    argument_parser.error("--bush-count-min cannot exceed --bush-count-max")
if arguments.bush_visible_height_min > arguments.bush_visible_height_max:
    argument_parser.error("--bush-visible-height-min cannot exceed --bush-visible-height-max")
if arguments.large_spruce_min > arguments.large_spruce_max:
    argument_parser.error("--large-spruce-min cannot exceed --large-spruce-max")
if arguments.large_spruce_min == 0:
    argument_parser.error("--large-spruce-min must be at least 1 when generating a tall conifer")
if arguments.double_tree_pair_min > arguments.double_tree_pair_max:
    argument_parser.error("--double-tree-pair-min cannot exceed --double-tree-pair-max")
if arguments.double_tree_distance_min > arguments.double_tree_distance_max:
    argument_parser.error("--double-tree-distance-min cannot exceed --double-tree-distance-max")
if arguments.tls_sector_width > 360.0:
    argument_parser.error("--tls-sector-width cannot exceed 360 degrees")
scene_seed = arguments.seed if arguments.seed is not None else secrets.randbelow(2**31)
scene_random = random.Random(scene_seed)
tls_random = random.Random(scene_seed ^ 0x544C53)

scene_base_names = {
    "alley": "AlleyTreeScene",
    "dense_park": "DenseParkScene",
    "sparse_park": "SparseParkScene",
}
scene_base_name = scene_base_names[scene_kind]
scene_name = (
    f"{scene_base_name}_{arguments.scene_index:03d}" if arguments.scene_index is not None else scene_base_name
)
output_root = (
    evoengine_directory / "out" / scene_base_name / scene_name
    if arguments.scene_index is not None
    else evoengine_directory / "out" / scene_name
)

build_root = evoengine_directory / "out" / "build"
extension_suffix = sysconfig.get_config_var("EXT_SUFFIX")
pyd_files = sorted(
    (p for p in build_root.glob("**/PyEcoSysLab*.pyd") if extension_suffix is None or p.name.endswith(extension_suffix)),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)
if not pyd_files:
    raise FileNotFoundError(
        f"A PyEcoSysLab module matching this Python ({extension_suffix}) was not found under {build_root}."
    )

library_directory = pyd_files[0].parent
build_directory = next(p for p in library_directory.parents if p.parent == build_root)

if hasattr(os, "add_dll_directory"):
    for dll_directory in [
        library_directory,
        build_directory / "EvoEngine_SDK" / "RelWithDebInfo",
        build_directory / "EvoEngine_Services" / "CudaModule" / "RelWithDebInfo",
        build_directory / "EvoEngine_App" / "RelWithDebInfo",
        build_directory / "EvoEngine_App" / "RelWithDebInfo" / "Packages",
        build_directory / "Extern" / "3rdParty" / "assimp" / "bin",
        build_directory / "Extern" / "3rdParty" / "assimp" / "assimp" / "bin" / "RelWithDebInfo",
        build_directory / "Extern" / "3rdParty" / "zlib" / "zlib" / "RelWithDebInfo",
        evoengine_directory / "Extern" / "3rdParty" / "zlib" / "zlib",
    ]:
        if dll_directory.exists():
            os.add_dll_directory(str(dll_directory))

os.chdir(library_directory)
sys.path.insert(0, str(library_directory))

import PyEcoSysLab as tree_framework

PROJECT_PATH = str(evoengine_directory / "Resources" / "EcoSysLabProject" / "test.eveproj")
SCENE_PATH = "DigitalForestry.evescene"
TREE_DESCRIPTORS = {
    "oak": "./TreeDescriptors/Basic/Oak.tree",
    "maple": "./TreeDescriptors/Basic/Maple.tree",
    "acacia": "./TreeDescriptors/Basic/Acacia.tree",
    "apple": "./TreeDescriptors/Basic/Apple.tree",
    "corkscrew": "./TreeDescriptors/Basic/Corkscrew.tree",
    "dropping_spruce": "./TreeDescriptors/Basic/DroppingSpruce.tree",
    "elm": "./TreeDescriptors/Basic/Elm.tree",
    "hazel": "./TreeDescriptors/Basic/Hazel.tree",
    "joshua": "./TreeDescriptors/Basic/Joshua.tree",
    "poplar": "./TreeDescriptors/Basic/Poplar.tree",
    "spruce": "./TreeDescriptors/Basic/Spruce.tree",
    "bush_acacia": "./TreeDescriptors/Basic/BushAcacia.tree",
}

output_root.mkdir(parents=True, exist_ok=True)

tree_framework.PushRenderLayer()
tree_framework.RegisterClasses()
tree_framework.PushEcoSysLabLayer()
tree_framework.RunWithScene(PROJECT_PATH, SCENE_PATH)
timings = {"engine_initialization_seconds": time.perf_counter() - total_start_time}


def terminate_after_unhandled_exception(exc_type, exc_value, traceback):
    sys.__excepthook__(exc_type, exc_value, traceback)
    sys.stderr.flush()
    kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 1)


sys.excepthook = terminate_after_unhandled_exception

params = tree_framework.TreeDataGenerationParameters()
params.output_folder = str(output_root)
params.output_file_name = scene_name
params.tree_descriptor_path = TREE_DESCRIPTORS["oak"]
params.seed = scene_seed
params.max_iteration = 84
params.max_depth = 70.0
params.generate_ground_mesh = True
params.export_mesh = True
params.export_point_cloud = True
params.export_rendering = True
params.export_depth = True
params.export_statistics = False
params.export_flow_graph = False
params.export_node_graph = False

point_settings = params.tree_point_cloud_point_settings
point_settings.ball_rand_radius = 0.0
point_settings.bounding_box_limit = 0.25
point_settings.instance_index = True
point_settings.type_index = True
point_settings.capture_ground = True

mesh_settings = params.tree_mesh_generator_settings
mesh_settings.enable_foliage = True
if hasattr(mesh_settings, "foliage_instancing"):
    mesh_settings.foliage_instancing = False
mesh_settings.enable_root_branch = False
mesh_settings.enable_fine_root = False
if hasattr(mesh_settings, "vertex_color_mode"):
    mesh_settings.vertex_color_mode = 0
mesh_settings.x_subdivision = 0.08
mesh_settings.trunk_y_subdivision = 0.10
mesh_settings.branch_y_subdivision = 0.10

camera_settings = tree_framework.CameraCaptureSettings()
camera_settings.camera_settings.fov = 65
camera_settings.camera_settings.background_intensity = 8
camera_settings.pivot_position.x = 0
camera_settings.pivot_position.y = max(
    11 if scene_kind != "sparse_park" else 13,
    arguments.tall_conifer_height * 1.4,
)
camera_settings.pivot_position.z = -max(
    18 if scene_kind == "alley" else (21 if scene_kind == "dense_park" else 24),
    arguments.tall_conifer_height * 3.0,
)
camera_settings.pivot_euler_rotation.x = -22
camera_settings.pivot_euler_rotation.y = 180
camera_settings.pivot_euler_rotation.z = 0
camera_settings.render_resolution.x = 2048
camera_settings.render_resolution.y = 1536
camera_settings.output_resolution.x = 1600
camera_settings.output_resolution.y = 1200

tls_settings = tree_framework.TreePointCloudSphericalCaptureSettings()
tls_settings.capture_mode = tree_framework.PointCloudCaptureMode.Gpu
tls_settings.vertical_angle_start = -90.0
tls_settings.vertical_angle_end = 90.0
tls_settings.angular_step = arguments.tls_angular_step
tls_settings.max_capture_depth = arguments.tls_max_depth

tree_framework.scene_light_settings(0.2, 4)
tree_framework.prepare_tree_scene(
    params,
    clear_existing_trees=True,
    soil_descriptor_path="Soils/DigitalForestryFlat.soil",
)

active_trees = []
tree_exports = []
object_map = {
    "1000": {
        "name": "ground",
        "kind": "artificial",
        "soil_descriptor": "Soils/DigitalForestryFlat.soil",
        "mesh": f"{scene_name}_ground.obj",
    }
}


def write_box_obj(path, box_specs):
    lines = [f"# {scene_name} building boxes"]
    vertex_offset = 1
    for object_id, name, x, z, width, height, depth, base_y in box_specs:
        x0, x1 = x - width * 0.5, x + width * 0.5
        z0, z1 = z - depth * 0.5, z + depth * 0.5
        lines.extend(
            [
                f"o ID{object_id}_{name}",
                f"v {x0} {base_y} {z0}",
                f"v {x1} {base_y} {z0}",
                f"v {x1} {base_y + height} {z0}",
                f"v {x0} {base_y + height} {z0}",
                f"v {x0} {base_y} {z1}",
                f"v {x1} {base_y} {z1}",
                f"v {x1} {base_y + height} {z1}",
                f"v {x0} {base_y + height} {z1}",
            ]
        )
        for a, b, c in (
            (1, 2, 3),
            (1, 3, 4),
            (5, 7, 6),
            (5, 8, 7),
            (1, 5, 6),
            (1, 6, 2),
            (4, 3, 7),
            (4, 7, 8),
            (1, 4, 8),
            (1, 8, 5),
            (2, 6, 7),
            (2, 7, 3),
        ):
            lines.append(f"f {vertex_offset + a - 1} {vertex_offset + b - 1} {vertex_offset + c - 1}")
        vertex_offset += 8
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def scale_obj_vertices(path, scale):
    if scale == 1.0:
        return
    lines = []
    with path.open("r", encoding="ascii", errors="ignore") as source:
        for line in source:
            if line.startswith("v "):
                values = line.split()
                values[1:4] = [str(float(value) * scale) for value in values[1:4]]
                line = " ".join(values) + "\n"
            lines.append(line)
    path.write_text("".join(lines), encoding="ascii", newline="\n")


def merge_scene_obj(output_path, sources):
    vertex_offset = texture_offset = normal_offset = 0
    with output_path.open("w", encoding="ascii", newline="\n") as output:
        output.write(f"# Complete world-space geometry for {scene_name}\n")
        for source_path, translation in sources:
            counts = {"v": 0, "vt": 0, "vn": 0}
            with source_path.open("r", encoding="ascii", errors="ignore") as source:
                for line in source:
                    key = line.split(maxsplit=1)[0] if line.strip() else ""
                    if key in counts:
                        counts[key] += 1

            prefix = source_path.stem
            with source_path.open("r", encoding="ascii", errors="ignore") as source:
                for line in source:
                    if line.startswith("v "):
                        values = line.split()
                        values[1] = str(float(values[1]) + translation[0])
                        values[2] = str(float(values[2]) + translation[1])
                        values[3] = str(float(values[3]) + translation[2])
                        output.write(" ".join(values) + "\n")
                    elif line.startswith(("vt ", "vn ")):
                        output.write(line)
                    elif line.startswith(("o ", "g ")):
                        part = line.split(maxsplit=1)[1].strip().split()[0]
                        output.write(f"o {part}\n" if part.startswith("ID") else f"o {prefix}_{part}\n")
                    elif line.startswith("f "):
                        adjusted = []
                        for token in line.split()[1:]:
                            indices = token.split("/")
                            indices[0] = str(int(indices[0]) + vertex_offset)
                            if len(indices) > 1 and indices[1] and counts["vt"]:
                                indices[1] = str(int(indices[1]) + texture_offset)
                            elif len(indices) > 1:
                                indices = indices[:1]
                            if len(indices) > 2 and indices[2] and counts["vn"]:
                                indices[2] = str(int(indices[2]) + normal_offset)
                            elif len(indices) > 2:
                                indices = indices[:2]
                            adjusted.append("/".join(indices))
                        output.write("f " + " ".join(adjusted) + "\n")
            vertex_offset += counts["v"]
            texture_offset += counts["vt"]
            normal_offset += counts["vn"]


def merge_scanner_ply(input_paths, output_path):
    point_blocks, type_blocks, instance_blocks = [], [], []
    total_points = 0
    for path in input_paths:
        data = path.read_bytes()
        header_end = data.index(b"end_header\n") + len(b"end_header\n")
        header = data[:header_end].decode("ascii")
        point_count = int(next(line.split()[2] for line in header.splitlines() if line.startswith("element vertex ")))
        payload = data[header_end:]
        point_blocks.append(payload[: point_count * 12])
        type_blocks.append(payload[point_count * 12 : point_count * 16])
        instance_blocks.append(payload[point_count * 16 : point_count * 20])
        total_points += point_count
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {total_points}\n"
        "property float x\nproperty float y\nproperty float z\n"
        f"element type_index {total_points}\nproperty int type_index\n"
        f"element instance_index {total_points}\nproperty int instance_index\n"
        "end_header\n"
    ).encode("ascii")
    output_path.write_bytes(
        header + b"".join(point_blocks) + b"".join(type_blocks) + b"".join(instance_blocks)
    )


def generate_buildings():
    specs = []
    for index in range(scene_random.randint(1, 3)):
        width = scene_random.uniform(1.6, 3.0)
        height = scene_random.uniform(2.5, 5.0)
        depth = scene_random.uniform(1.5, 2.8)
        for _ in range(1000):
            if scene_kind == "alley":
                x = scene_random.uniform(-5.0, 5.0)
                z = scene_random.choice((-1.0, 1.0)) * scene_random.uniform(4.7, 5.2)
            else:
                x = scene_random.uniform(-4.9, 4.9)
                z = scene_random.uniform(-4.9, 4.9)
            if all(abs(x - other[2]) > (width + other[4]) * 0.5 + 0.4 or
                   abs(z - other[3]) > (depth + other[6]) * 0.5 + 0.4 for other in specs):
                break
        specs.append((1001 + index, f"Building_{index}", x, z, width, height, depth))
    return specs


def sample_positions(count, minimum_distance, extent, buildings, occupied_positions=()):
    positions = []
    occupied_positions = list(occupied_positions)
    for _ in range(100_000):
        if scene_kind == "alley":
            side = -1.0 if len(positions) % 2 == 0 else 1.0
            candidate = (scene_random.uniform(-5.7, 5.7), side * scene_random.uniform(1.8, 2.7))
        else:
            candidate = (scene_random.uniform(-extent, extent), scene_random.uniform(-extent, extent))
        outside_buildings = all(
            abs(candidate[0] - x) > width * 0.5 + 0.2 or abs(candidate[1] - z) > depth * 0.5 + 0.2
            for _, _, x, z, width, _, depth in buildings
        )
        if outside_buildings and all(
            (candidate[0] - x) ** 2 + (candidate[1] - z) ** 2 >= minimum_distance**2
            for x, z in occupied_positions + positions
        ):
            positions.append(candidate)
            if len(positions) == count:
                return positions
    raise RuntimeError(f"Could not place {count} plants for {scene_name}.")


def sample_tls_positions(count, extent, buildings, plant_positions):
    positions = []
    for _ in range(100_000):
        if scene_kind == "alley":
            candidate = (tls_random.uniform(-extent + 0.5, extent - 0.5), tls_random.uniform(-0.6, 0.6))
        else:
            candidate = (
                tls_random.uniform(-extent + 0.5, extent - 0.5),
                tls_random.uniform(-extent + 0.5, extent - 0.5),
            )
        outside_buildings = all(
            abs(candidate[0] - x) > width * 0.5 + 0.4 or abs(candidate[1] - z) > depth * 0.5 + 0.4
            for _, _, x, z, width, _, depth in buildings
        )
        clear_of_plants = all(
            (candidate[0] - x) ** 2 + (candidate[1] - z) ** 2 >= 0.75**2 for x, z in plant_positions
        )
        separated = all(
            (candidate[0] - x) ** 2 + (candidate[1] - z) ** 2 >= 0.75**2 for x, z in positions
        )
        if outside_buildings and clear_of_plants and separated:
            positions.append(candidate)
            if len(positions) == count:
                return positions
    raise RuntimeError(f"Could not place {count} TLS stations inside {scene_name}.")


building_specs = generate_buildings()
bush_count = scene_random.randint(arguments.bush_count_min, arguments.bush_count_max)
if scene_kind == "alley":
    tree_count = scene_random.randint(10, 16)
    minimum_distance, bush_minimum_distance, extent = 0.8, 0.6, 5.7
elif scene_kind == "dense_park":
    tree_count = scene_random.randint(15, 20)
    minimum_distance, bush_minimum_distance, extent = 0.75, 0.6, 4.5
else:
    tree_count = scene_random.randint(10, 14)
    minimum_distance, bush_minimum_distance, extent = 2.6, 0.9, 5.9

large_spruce_count = scene_random.randint(arguments.large_spruce_min, arguments.large_spruce_max)
double_tree_pair_count = scene_random.randint(arguments.double_tree_pair_min, arguments.double_tree_pair_max)
required_big_tree_count = large_spruce_count + double_tree_pair_count * 2
if required_big_tree_count > tree_count - 2:
    raise ValueError(
        f"{large_spruce_count} large spruces and {double_tree_pair_count} double-tree pairs require "
        f"{required_big_tree_count} big trees, but this scene can have at most {tree_count - 2}."
    )
big_tree_count = scene_random.randint(max(3, tree_count // 2, required_big_tree_count), tree_count - 2)

tree_positions = sample_positions(tree_count, minimum_distance, extent, building_specs)
tree_positions, double_tree_pairs = place_double_tree_pairs(
    tree_positions,
    double_tree_pair_count,
    big_tree_count,
    arguments.double_tree_distance_min,
    arguments.double_tree_distance_max,
    minimum_distance,
    extent,
    scene_kind,
    building_specs,
    scene_random,
)
bush_positions = sample_positions(
    bush_count,
    bush_minimum_distance,
    extent,
    building_specs,
    occupied_positions=tree_positions,
)
tls_station_count = arguments.tls_station_count or tls_random.randint(5, 10)
tls_station_positions = sample_tls_positions(
    tls_station_count,
    extent,
    building_specs,
    tree_positions + bush_positions,
)
tls_stations = tuple(
    (f"scan_{index:02d}", x, z) for index, (x, z) in enumerate(tls_station_positions, 1)
)

big_start_steps = [scene_random.randint(0, 6) for _ in range(big_tree_count)]
oldest_start = min(big_start_steps)
big_start_steps = [step - oldest_start for step in big_start_steps]
small_start_steps = [scene_random.randint(28, 40) for _ in range(tree_count - big_tree_count)]
tree_start_steps = big_start_steps + small_start_steps
species = tuple(name for name in TREE_DESCRIPTORS if name != "bush_acacia")
tree_species = scene_random.sample(species, 3) + [scene_random.choice(species) for _ in range(tree_count - 3)]
scene_random.shuffle(tree_species)
large_spruce_indices = select_large_spruce_indices(
    big_tree_count,
    double_tree_pairs,
    large_spruce_count,
    scene_random,
)
for index in large_spruce_indices:
    tree_species[index] = "spruce"
    tree_start_steps[index] = 0
large_spruce_ids = {index + 1 for index in large_spruce_indices}
tall_conifer_id = scene_random.choice(sorted(large_spruce_ids))
double_tree_by_id = {}
for pair in double_tree_pairs:
    first_id, second_id = pair["tree_ids"]
    double_tree_by_id[first_id] = (pair["pair_id"], second_id, pair["distance"])
    double_tree_by_id[second_id] = (pair["pair_id"], first_id, pair["distance"])
plant_specs = []
for index, ((x, z), start_step, tree_species_name) in enumerate(
    zip(tree_positions, tree_start_steps, tree_species), 1
):
    level = "big_tree" if index <= big_tree_count else "small_tree"
    level_name = "Big" if level == "big_tree" else "Small"
    plant_specs.append(
        (
            start_step,
            index,
            f"{level_name}_{tree_species_name.title()}_Start{start_step}_{index}",
            tree_species_name,
            x,
            z,
            "tree",
            level,
            scene_random.randrange(2**31),
        )
    )
for index, (x, z) in enumerate(bush_positions, tree_count + 1):
    start_step = scene_random.randint(8, 18)
    plant_specs.append(
        (
            start_step,
            index,
            f"Bush_Acacia_Start{start_step}_{index}",
            "bush_acacia",
            x,
            z,
            "bush",
            "bush",
            scene_random.randrange(2**31),
        )
    )

building_export_specs = []
for object_id, name, x, z, width, height, depth in building_specs:
    entity = tree_framework.create_building_box(object_id, name, x, z, width, height, depth)
    position = tree_framework.get_entity_position(entity)
    base_y = position.y - height * 0.5
    building_export_specs.append((object_id, name, x, z, width, height, depth, base_y))
    object_map[str(object_id)] = {
        "name": f"ID{object_id}_{name}",
        "kind": "artificial",
        "shape": "box",
        "x": x,
        "z": z,
        "width": width,
        "height": height,
        "depth": depth,
        "y": base_y,
        "affects_tree_growth": True,
        "tree_growth_shadow": 1.0,
        "tree_growth_biomass": 1.0,
    }


def create_plant(object_id, name, species_name, x, z, kind, level, tree_seed, start_step):
    params.tree_descriptor_path = TREE_DESCRIPTORS[species_name]
    entity_name = f"ID{object_id:03d}_{name}"
    growth_scale = 3.0 if kind == "bush" else (2.0 if object_id == tall_conifer_id else 1.0)
    entity = tree_framework.create_tree(params, x, z, tree_seed, entity_name, growth_scale)
    position = tree_framework.get_entity_position(entity)
    active_trees.append(entity)
    tree_exports.append((object_id, entity_name, entity))
    object_map[str(object_id)] = {
        "name": entity_name,
        "kind": kind,
        "level": level,
        "species": species_name,
        "seed": tree_seed,
        "start_step": start_step,
        "growth_scale": growth_scale,
        "x": position.x,
        "y": position.y,
        "z": position.z,
    }
    if object_id in large_spruce_ids:
        object_map[str(object_id)]["large_spruce"] = True
    if object_id == tall_conifer_id:
        object_map[str(object_id)].update(
            {
                "tall_conifer": True,
                "target_height": arguments.tall_conifer_height,
            }
        )
    if object_id in double_tree_by_id:
        pair_id, partner_id, pair_distance = double_tree_by_id[object_id]
        object_map[str(object_id)].update(
            {
                "double_tree_pair_id": pair_id,
                "double_tree_partner_id": partner_id,
                "double_tree_distance": pair_distance,
            }
        )
    return entity


def grow_steps(start_step, count):
    for local_step in range(count):
        step = start_step + local_step
        if step % 8 == 0:
            print(f"Growth step {step}/{params.max_iteration}", flush=True)
        time = (step + 1) * params.simulation_settings.delta_time
        tree_framework.grow_tree_scene_step(active_trees, params.simulation_settings, time, pruning=True)


print(
    f"Generating {scene_name} with seed {scene_seed}: "
    f"{tree_count} trees ({large_spruce_count} large spruces, one {arguments.tall_conifer_height:g} m conifer, "
    f"{double_tree_pair_count} double-tree pairs), "
    f"{bush_count} bushes, {len(building_specs)} buildings.",
    flush=True,
)
stage_start_time = time.perf_counter()
for step in range(params.max_iteration):
    additions = [spec for spec in plant_specs if spec[0] == step]
    for start_step, object_id, name, species_name, x, z, kind, level, tree_seed in additions:
        create_plant(object_id, name, species_name, x, z, kind, level, tree_seed, start_step)
    if additions:
        tree_framework.Loop()
    grow_steps(step, 1)
timings["growth_seconds"] = time.perf_counter() - stage_start_time

for object_id, _, tree in tree_exports:
    metadata = object_map[str(object_id)]
    if object_id == tall_conifer_id:
        metadata["height_scale_factor"] = tree_framework.scale_tree_to_height(
            tree,
            arguments.tall_conifer_height,
        )
        metadata["final_scale"] = metadata["growth_scale"] * metadata["height_scale_factor"]
        metadata["calibrated_height"] = arguments.tall_conifer_height
    if metadata["kind"] != "bush":
        continue
    target_visible_height = scene_random.uniform(
        arguments.bush_visible_height_min,
        arguments.bush_visible_height_max,
    )
    target_total_height = target_visible_height / 0.5
    metadata["height_scale_factor"] = tree_framework.scale_tree_to_height(tree, target_total_height)
    metadata["final_scale"] = metadata["growth_scale"] * metadata["height_scale_factor"]
    sink_depth = tree_framework.lower_tree_by_height_ratio(tree, 0.5)
    position = tree_framework.get_entity_position(tree)
    metadata["height_before_sink"] = sink_depth / 0.5
    metadata["target_visible_height"] = target_visible_height
    metadata["visible_height_after_sink"] = metadata["height_before_sink"] - sink_depth
    metadata["sink_ratio"] = 0.5
    metadata["sink_depth"] = sink_depth
    metadata["y"] = position.y

with open(output_root / f"{scene_name}_object_ids.json", "w", encoding="utf-8") as f:
    json.dump(object_map, f, indent=2)
with open(output_root / f"{scene_name}_generation.json", "w", encoding="utf-8") as f:
    json.dump(
        {
            "configuration": scene_kind,
            "scene_index": arguments.scene_index,
            "scene_seed": scene_seed,
            "tree_count": tree_count,
            "big_tree_count": big_tree_count,
            "small_tree_count": tree_count - big_tree_count,
            "large_spruce_count": large_spruce_count,
            "large_spruce_count_range": [arguments.large_spruce_min, arguments.large_spruce_max],
            "large_spruce_ids": sorted(large_spruce_ids),
            "tall_conifer_id": tall_conifer_id,
            "tall_conifer_target_height": arguments.tall_conifer_height,
            "double_tree_pair_count": double_tree_pair_count,
            "double_tree_pair_count_range": [arguments.double_tree_pair_min, arguments.double_tree_pair_max],
            "double_tree_distance_range": [
                arguments.double_tree_distance_min,
                arguments.double_tree_distance_max,
            ],
            "double_tree_pairs": double_tree_pairs,
            "bush_count": bush_count,
            "building_count": len(building_specs),
            "max_iteration": params.max_iteration,
            "soil_descriptor": "Soils/DigitalForestryFlat.soil",
            "ground_mesh": f"{scene_name}_ground.obj",
            "bush_sink_ratio": 0.5,
            "bush_count_range": [arguments.bush_count_min, arguments.bush_count_max],
            "bush_visible_height_range": [
                arguments.bush_visible_height_min,
                arguments.bush_visible_height_max,
            ],
            "tree_minimum_distance": minimum_distance,
            "bush_minimum_distance": bush_minimum_distance,
            "placement_extent": extent,
            "tls": {
                "mode": "fixed_origin_spherical",
                "station_count": len(tls_stations),
                "station_count_requested": arguments.tls_station_count,
                "capture_height": arguments.tls_height,
                "station_positions": [
                    {"name": name, "x": x, "y": arguments.tls_height, "z": z}
                    for name, x, z in tls_stations
                ],
                "horizontal_angle_range": [0.0, 360.0],
                "vertical_angle_range": [-90.0, 90.0],
                "angular_step_degrees": tls_settings.angular_step,
                "sector_width_degrees": arguments.tls_sector_width,
                "max_capture_depth": tls_settings.max_capture_depth,
            },
        },
        f,
        indent=2,
    )

print("Generating meshes...", flush=True)
stage_start_time = time.perf_counter()
tree_framework.generate_tree_meshes(mesh_settings)
timings["mesh_generation_seconds"] = time.perf_counter() - stage_start_time

print("Capturing render view...", flush=True)
stage_start_time = time.perf_counter()
tree_framework.capture_tree_scene(
    camera_settings,
    str(output_root / f"{scene_name}_view.png"),
    str(output_root / f"{scene_name}_depth.png"),
    params.max_depth,
)
timings["render_capture_seconds"] = time.perf_counter() - stage_start_time

print("Exporting combined and individual OBJ meshes...", flush=True)
stage_start_time = time.perf_counter()
tree_framework.export_all_trees(str(output_root / f"{scene_name}_trees.obj"))
individual_tree_folder = output_root / "individual_plants"
individual_tree_folder.mkdir(exist_ok=True)
for old_mesh in individual_tree_folder.glob("*.obj"):
    old_mesh.unlink()
for object_id, tree_name, tree in tree_exports:
    individual_path = individual_tree_folder / f"{tree_name}.obj"
    tree_framework.export_tree(tree, mesh_settings, str(individual_path))
    scale_obj_vertices(individual_path, object_map[str(object_id)].get("final_scale", 1.0))

building_folder = output_root / "buildings"
building_folder.mkdir(exist_ok=True)
for old_mesh in building_folder.glob("*.obj"):
    old_mesh.unlink()
ground_path = output_root / f"{scene_name}_ground.obj"
tree_framework.export_ground_mesh(str(ground_path))
write_box_obj(output_root / f"{scene_name}_buildings.obj", building_export_specs)
for building_spec in building_export_specs:
    write_box_obj(building_folder / f"ID{building_spec[0]}_{building_spec[1]}.obj", [building_spec])

scene_sources = []
for object_id, tree_name, _ in tree_exports:
    metadata = object_map[str(object_id)]
    scene_sources.append(
        (
            individual_tree_folder / f"{tree_name}.obj",
            (metadata["x"], metadata["y"], metadata["z"]),
        )
    )
scene_sources.append((ground_path, (0.0, 0.0, 0.0)))
scene_sources.extend(
    (building_folder / f"ID{spec[0]}_{spec[1]}.obj", (0.0, 0.0, 0.0)) for spec in building_export_specs
)
merge_scene_obj(output_root / f"{scene_name}.obj", scene_sources)
timings["mesh_export_seconds"] = time.perf_counter() - stage_start_time

print(f"Scanning {len(tls_stations)} fixed-location spherical GPU TLS stations...", flush=True)
segment_folder = output_root / "tls_segments"
segment_folder.mkdir(exist_ok=True)
for old_path in segment_folder.glob("*.ply"):
    old_path.unlink()
for old_pattern in (f"{scene_name}_tls_scan_*.ply", f"{scene_name}_tls_station_*.ply", f"{scene_name}_tls_merged.ply"):
    for old_path in output_root.glob(old_pattern):
        old_path.unlink()

for station_name, station_x, station_z in tls_stations:
    stage_start_time = time.perf_counter()
    tls_settings.scanner_position.x = station_x
    tls_settings.scanner_position.y = arguments.tls_height
    tls_settings.scanner_position.z = station_z
    segment_paths = []
    horizontal_start = 0.0
    segment_index = 1
    while horizontal_start < 360.0:
        tls_settings.horizontal_angle_start = horizontal_start
        tls_settings.horizontal_angle_end = min(horizontal_start + arguments.tls_sector_width, 360.0)
        segment_path = segment_folder / f"{station_name}_segment_{segment_index:02d}.ply"
        tree_framework.scan_tree_point_cloud(tls_settings, point_settings, mesh_settings, str(segment_path))
        segment_paths.append(segment_path)
        horizontal_start = tls_settings.horizontal_angle_end
        segment_index += 1
    station_path = output_root / f"{scene_name}_tls_{station_name}.ply"
    merge_scanner_ply(segment_paths, station_path)
    for segment_path in segment_paths:
        segment_path.unlink()
    timings[f"tls_{station_name}_seconds"] = time.perf_counter() - stage_start_time
timings["total_seconds"] = time.perf_counter() - total_start_time
if arguments.timing:
    with open(output_root / f"{scene_name}_timings.json", "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)
    print(f"Finished {scene_name} in {timings['total_seconds'] / 60.0:.2f} minutes.", flush=True)
    for stage, seconds in timings.items():
        print(f"  {stage}: {seconds:.2f} s", flush=True)
else:
    print(f"Finished {scene_name}.", flush=True)
kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
