"""Render-only agricultural context and USGS Sierra Estrella skyline support."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


RENDER_ONLY_OWNERSHIP = "blender_presentation_only"
RAY_VISIBILITY_CONTRACT = {
    "camera": True,
    "diffuse": False,
    "glossy": False,
    "transmission": False,
    "shadow": False,
    "volume_scatter": False,
}
SITE_PROXY = {
    "latitude": 33.068941,
    "longitude": -111.972244,
    "elevation_m": 362.0,
    "source": "University of Arizona AZMET Maricopa",
    "source_url": "https://azmet.arizona.edu/azmet/06.htm",
    "role": "regional geographic proxy; experiment plot coordinates and heading are not established",
}
SIERRA_PROFILE_LICENSE = "USGS public domain"
USGS_IMAGE_SERVER = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
USGS_3DEP_SOURCE = "https://www.usgs.gov/3d-elevation-program"
DEM_BOUNDS_WGS84 = (-112.45, 32.95, -111.95, 33.45)
PROFILE_BEARING_RANGE_DEG = (260.0, 342.0)
PROFILE_STEP_DEG = 0.20
PROFILE_DISTANCE_RANGE_KM = (5.0, 60.0)
ORIENTATION_POLICY = "artistically_aligned_plot_heading_not_measured"
SCENE_AZIMUTH_OFFSET_DEG = 78.0
LANDSCAPE_COLLECTION = "SWEEP_RenderOnly_Landscape"
BACKGROUND_VARIANT_LAYERS = {
    "control": (),
    "horizon": ("terrain",),
    "apron": ("terrain", "lane"),
    "agriculture": ("terrain", "lane", "agriculture"),
    "mountains": ("terrain", "lane", "agriculture", "mountain"),
    "final": ("terrain", "lane", "agriculture", "mountain", "haze", "finish"),
}
BACKGROUND_VARIANTS = tuple(BACKGROUND_VARIANT_LAYERS)
LANDSCAPE_VIEWS = {"perspective", "row_side", "genotype_a_plant", "genotype_b_plant", "genotype_c_plant"}
MEASUREMENT_VIEW_LAYERS = {"terrain"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def angular_height_degrees(observer_elevation_m: float, peak_elevation_m: float, distance_km: float) -> float:
    return math.degrees(math.atan2(peak_elevation_m - observer_elevation_m, distance_km * 1000.0))


def scene_azimuth_degrees(geographic_bearing_degrees: float) -> float:
    return (geographic_bearing_degrees + SCENE_AZIMUTH_OFFSET_DEG) % 360.0


def layers_for_view(view: str, variant: str) -> set[str]:
    layers = set(BACKGROUND_VARIANT_LAYERS[variant])
    return layers if view in LANDSCAPE_VIEWS else layers & MEASUREMENT_VIEW_LAYERS


def _smooth_profile(values, radius: int = 2):
    import numpy as np

    padded = np.pad(values, radius, mode="edge")
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float64)
    kernel /= kernel.sum()
    return np.convolve(padded, kernel, mode="valid")


def skyline_from_dem(dem, extent: dict[str, float]) -> list[dict[str, float]]:
    import numpy as np

    elevation = np.asarray(dem, dtype=np.float64)
    if elevation.ndim > 2:
        elevation = elevation[0]
    height, width = elevation.shape
    longitudes = np.linspace(extent["xmin"], extent["xmax"], width, endpoint=False)
    longitudes += 0.5 * (extent["xmax"] - extent["xmin"]) / width
    latitudes = np.linspace(extent["ymax"], extent["ymin"], height, endpoint=False)
    latitudes -= 0.5 * (extent["ymax"] - extent["ymin"]) / height
    longitude_grid, latitude_grid = np.meshgrid(longitudes, latitudes)
    north_km = (latitude_grid - SITE_PROXY["latitude"]) * 111.32
    east_km = (
        (longitude_grid - SITE_PROXY["longitude"])
        * 111.32
        * math.cos(math.radians(SITE_PROXY["latitude"]))
    )
    distance_km = np.hypot(east_km, north_km)
    bearing = (np.degrees(np.arctan2(east_km, north_km)) + 360.0) % 360.0
    curvature_drop_m = distance_km * distance_km * 1000.0 / (2.0 * 6371.0088)
    angle = np.degrees(
        np.arctan2(elevation - SITE_PROXY["elevation_m"] - curvature_drop_m, distance_km * 1000.0)
    )
    minimum_bearing, maximum_bearing = PROFILE_BEARING_RANGE_DEG
    count = round((maximum_bearing - minimum_bearing) / PROFILE_STEP_DEG) + 1
    maximum_angle = np.full(count, -np.inf)
    valid = (
        np.isfinite(elevation)
        & (elevation > -100.0)
        & (elevation < 5000.0)
        & (distance_km >= PROFILE_DISTANCE_RANGE_KM[0])
        & (distance_km <= PROFILE_DISTANCE_RANGE_KM[1])
        & (bearing >= minimum_bearing)
        & (bearing <= maximum_bearing)
    )
    indices = np.rint((bearing[valid] - minimum_bearing) / PROFILE_STEP_DEG).astype(int)
    np.maximum.at(maximum_angle, indices, angle[valid])
    finite = np.isfinite(maximum_angle)
    if finite.sum() < count * 0.8:
        raise RuntimeError("USGS DEM did not cover enough of the Sierra Estrella skyline")
    x = np.arange(count)
    maximum_angle = np.interp(x, x[finite], maximum_angle[finite])
    maximum_angle = _smooth_profile(maximum_angle)
    return [
        {
            "bearing_deg": round(minimum_bearing + index * PROFILE_STEP_DEG, 4),
            "elevation_angle_deg": round(max(float(value), -0.5), 5),
        }
        for index, value in enumerate(maximum_angle)
    ]


def validate_profile(profile: dict[str, object]) -> None:
    samples = profile.get("samples", [])
    if profile.get("ownership") != RENDER_ONLY_OWNERSHIP or len(samples) < 300:
        raise RuntimeError("invalid Sierra Estrella presentation profile")
    bearings = [float(sample["bearing_deg"]) for sample in samples]
    angles = [float(sample["elevation_angle_deg"]) for sample in samples]
    if bearings != sorted(bearings) or max(angles) < 1.0 or max(angles) > 4.0:
        raise RuntimeError("Sierra Estrella skyline has an implausible scale")


def prepare_sierra_profile(output_dir: Path, image_size: int = 1024) -> Path:
    import numpy as np
    import requests
    import tifffile

    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = output_dir / "sierra_estrella_usgs_3dep_profile.json"
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        validate_profile(profile)
        return profile_path
    params = {
        "bbox": ",".join(str(value) for value in DEM_BOUNDS_WGS84),
        "bboxSR": 4326,
        "imageSR": 4326,
        "size": f"{image_size},{image_size}",
        "format": "tiff",
        "pixelType": "F32",
        "f": "json",
    }
    request_url = f"{USGS_IMAGE_SERVER}?{urlencode(params)}"
    response = requests.get(request_url, timeout=120)
    response.raise_for_status()
    metadata = response.json()
    dem_response = requests.get(metadata["href"], timeout=120)
    dem_response.raise_for_status()
    dem_path = output_dir / "sierra_estrella_usgs_3dep_dem.tif"
    dem_path.write_bytes(dem_response.content)
    dem = tifffile.imread(dem_path)
    extent = {key: float(metadata["extent"][key]) for key in ("xmin", "ymin", "xmax", "ymax")}
    samples = skyline_from_dem(np.asarray(dem), extent)
    peak = max(samples, key=lambda sample: sample["elevation_angle_deg"])
    profile = {
        "schema_version": 1,
        "ownership": RENDER_ONLY_OWNERSHIP,
        "scientific_geometry": False,
        "site_proxy": SITE_PROXY,
        "orientation_policy": ORIENTATION_POLICY,
        "scene_azimuth_offset_deg": SCENE_AZIMUTH_OFFSET_DEG,
        "source": {
            "dataset": "USGS 3D Elevation Program bare-earth DEM",
            "dataset_url": USGS_3DEP_SOURCE,
            "request_url": request_url,
            "download_url": metadata["href"],
            "license": SIERRA_PROFILE_LICENSE,
            "dem_sha256": sha256(dem_path),
            "extent_wgs84": extent,
            "raster_size": [int(dem.shape[-1]), int(dem.shape[-2])],
            "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        },
        "bearing_range_deg": list(PROFILE_BEARING_RANGE_DEG),
        "bearing_step_deg": PROFILE_STEP_DEG,
        "distance_filter_km": list(PROFILE_DISTANCE_RANGE_KM),
        "peak_sample": peak,
        "samples": samples,
    }
    validate_profile(profile)
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return profile_path


def _new_principled_material(name: str, base_color, roughness: float):
    import bpy

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return material


def _lane_material():
    import bpy

    material = _new_principled_material("SWEEP RenderOnly Dry Service Lane", (0.20, 0.10, 0.035, 1.0), 0.86)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.8
    noise.inputs["Detail"].default_value = 4.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.07, 0.035, 0.012, 1.0)
    ramp.color_ramp.elements[1].color = (0.22, 0.12, 0.045, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.24
    bump.inputs["Distance"].default_value = 0.012
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Factor"], ramp.inputs["Factor"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Factor"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def _crop_material():
    import bpy

    material = _new_principled_material("SWEEP RenderOnly Distant Crops", (0.035, 0.070, 0.012, 1.0), 0.76)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.4
    noise.inputs["Detail"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.018, 0.045, 0.006, 1.0)
    ramp.color_ramp.elements[1].color = (0.085, 0.16, 0.026, 1.0)
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Factor"], ramp.inputs["Factor"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def _emission_material(name: str, colors, scale: float = 0.018, strength: float = 0.72):
    import bpy

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = strength
    position = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 2.2
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = colors[0]
    ramp.color_ramp.elements[1].color = colors[1]
    links.new(position.outputs["Position"], noise.inputs["Vector"])
    links.new(noise.outputs["Factor"], ramp.inputs["Factor"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _haze_material(name: str, color, opacity: float, strength: float):
    import bpy

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = opacity
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(emission.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return material


def _mark_render_only(obj, layer: str) -> None:
    obj["sweep_ownership"] = RENDER_ONLY_OWNERSHIP
    obj["scientific_geometry"] = False
    obj["parbar_participant"] = False
    obj["sweep_background_layer"] = layer
    obj.visible_camera = RAY_VISIBILITY_CONTRACT["camera"]
    obj.visible_diffuse = RAY_VISIBILITY_CONTRACT["diffuse"]
    obj.visible_glossy = RAY_VISIBILITY_CONTRACT["glossy"]
    obj.visible_transmission = RAY_VISIBILITY_CONTRACT["transmission"]
    obj.visible_shadow = RAY_VISIBILITY_CONTRACT["shadow"]
    obj.visible_volume_scatter = RAY_VISIBILITY_CONTRACT["volume_scatter"]


def _mesh_object(collection, name: str, vertices, faces, material, layer: str):
    import bpy

    mesh = bpy.data.meshes.new(f"{name} Mesh")
    mesh.from_pydata(vertices, [], faces)
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    _mark_render_only(obj, layer)
    return obj


def remove_landscape_context() -> None:
    import bpy

    collection = bpy.data.collections.get(LANDSCAPE_COLLECTION)
    if not collection:
        return
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)


def _terrain(collection, center, base_z: float, material):
    rings, spokes, radius = 24, 96, 180.0
    vertices = [(center.x, center.y, base_z)]
    for ring in range(1, rings + 1):
        radial = radius * ring / rings
        for spoke in range(spokes):
            angle = math.tau * spoke / spokes
            x = center.x + radial * math.sin(angle)
            y = center.y + radial * math.cos(angle)
            z = base_z + 0.06 * math.sin(0.047 * x + 0.61) * math.sin(0.039 * y - 0.28)
            vertices.append((x, y, z))
    faces = []
    for spoke in range(spokes):
        faces.append((0, 1 + spoke, 1 + (spoke + 1) % spokes))
    for ring in range(1, rings):
        inner = 1 + (ring - 1) * spokes
        outer = 1 + ring * spokes
        for spoke in range(spokes):
            next_spoke = (spoke + 1) % spokes
            faces.append((inner + spoke, outer + spoke, outer + next_spoke, inner + next_spoke))
    obj = _mesh_object(collection, "SWEEP RenderOnly Agricultural Terrain", vertices, faces, material, "terrain")
    obj["radius_m"] = radius
    return obj


def _rectangle(collection, name, x0, x1, y0, y1, z, material, layer):
    return _mesh_object(
        collection,
        name,
        [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)],
        [(0, 1, 2, 3)],
        material,
        layer,
    )


def _service_lane(collection, minimum, maximum, base_z: float):
    material = _lane_material()
    inner = (minimum.x - 1.8, maximum.x + 1.8, minimum.y - 1.8, maximum.y + 1.8)
    outer = (minimum.x - 5.2, maximum.x + 5.2, minimum.y - 5.2, maximum.y + 5.2)
    rectangles = (
        (outer[0], inner[0], outer[2], outer[3]),
        (inner[1], outer[1], outer[2], outer[3]),
        (inner[0], inner[1], outer[2], inner[2]),
        (inner[0], inner[1], inner[3], outer[3]),
    )
    objects = [
        _rectangle(collection, f"SWEEP RenderOnly Service Lane {index + 1}", *rectangle, base_z + 0.004, material, "lane")
        for index, rectangle in enumerate(rectangles)
    ]
    vertices = []
    faces = []
    segments = 72
    ridges = (
        ((minimum.x - 8.0, maximum.y + 3.0), (maximum.x + 24.0, maximum.y + 3.0)),
        ((maximum.x + 3.0, minimum.y - 8.0), (maximum.x + 3.0, maximum.y + 24.0)),
    )
    for ridge, (start, end) in enumerate(ridges):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        lateral_x, lateral_y = -dy / length, dx / length
        strip = []
        for segment in range(segments + 1):
            fraction = segment / segments
            x = start[0] + dx * fraction
            y = start[1] + dy * fraction
            width = 0.42 + 0.10 * math.sin(7.0 * fraction + ridge)
            height = base_z + 0.08 + 0.035 * math.sin(11.0 * fraction + 1.7 * ridge)
            strip.append((len(vertices), len(vertices) + 1, len(vertices) + 2, len(vertices) + 3))
            vertices.extend(
                (
                    (x - lateral_x * width, y - lateral_y * width, base_z),
                    (x - lateral_x * 0.30 * width, y - lateral_y * 0.30 * width, height),
                    (x + lateral_x * 0.30 * width, y + lateral_y * 0.30 * width, height),
                    (x + lateral_x * width, y + lateral_y * width, base_z),
                )
            )
        for first, second in zip(strip, strip[1:]):
            faces.extend(
                (
                    (first[0], second[0], second[1], first[1]),
                    (first[1], second[1], second[2], first[2]),
                    (first[2], second[2], second[3], first[3]),
                )
            )
    objects.append(_mesh_object(collection, "SWEEP RenderOnly Irrigation Berms", vertices, faces, material, "lane"))
    return objects


def _distant_crops(collection, minimum, maximum, center, base_z: float):
    material = _crop_material()
    rows_per_field, half_length, plant_spacing = 18, 72.0, 0.32
    vertices = []
    faces = []

    def add_row(origin_x, origin_y, along_x, along_y, lateral_x, lateral_y, row):
        count = round(2.0 * half_length / plant_spacing)
        for plant in range(count + 1):
            phase = math.sin(12.9898 * (plant + 1) + 78.233 * (row + 1))
            along = -half_length + 2.0 * half_length * plant / count + 0.08 * phase
            lateral_jitter = 0.09 * math.sin(0.73 * plant + 1.91 * row)
            x = origin_x + along_x * along + lateral_x * lateral_jitter
            y = origin_y + along_y * along + lateral_y * lateral_jitter
            height = 0.24 + 0.26 * (0.5 + 0.5 * math.sin(1.37 * plant + 2.11 * row))
            width = 0.035 + 0.045 * (0.5 + 0.5 * math.sin(2.31 * plant + 0.67 * row))
            for cross in range(2):
                angle = math.atan2(along_y, along_x) + cross * math.pi * 0.5 + 0.32 * phase
                dx = 0.5 * width * math.cos(angle)
                dy = 0.5 * width * math.sin(angle)
                first = len(vertices)
                vertices.extend(
                    (
                        (x - dx, y - dy, base_z),
                        (x + dx, y + dy, base_z),
                        (x + dx, y + dy, base_z + height),
                        (x - dx, y - dy, base_z + 0.92 * height),
                    )
                )
                faces.append((first, first + 1, first + 2, first + 3))
    for row in range(rows_per_field):
        add_row(center.x, maximum.y + 22.0 + row * 1.28, 1.0, 0.0, 0.0, 1.0, row)
        add_row(maximum.x + 22.0 + row * 1.28, center.y, 0.0, 1.0, 1.0, 0.0, row + rows_per_field)
    obj = _mesh_object(collection, "SWEEP RenderOnly Adjacent Field Rows", vertices, faces, material, "agriculture")
    obj["generic_unmeasured_vegetation"] = True
    obj["field_band_count"] = 2
    obj["row_count"] = 2 * rows_per_field
    return obj


def _mountain(collection, center, base_z: float, profile: dict[str, object]):
    radius = 320.0
    vertices = []
    for sample in profile["samples"]:
        azimuth = math.radians(scene_azimuth_degrees(float(sample["bearing_deg"])))
        x = center.x + radius * math.sin(azimuth)
        y = center.y + radius * math.cos(azimuth)
        top = base_z + radius * math.tan(math.radians(max(0.10, float(sample["elevation_angle_deg"]))))
        vertices.extend(((x, y, base_z - 14.0), (x, y, top)))
    faces = [(2 * index, 2 * index + 2, 2 * index + 3, 2 * index + 1) for index in range(len(profile["samples"]) - 1)]
    material = _emission_material(
        "SWEEP RenderOnly Sierra Estrella Hazy Surface",
        ((0.27, 0.31, 0.33, 1.0), (0.38, 0.40, 0.39, 1.0)),
        strength=0.90,
    )
    obj = _mesh_object(collection, "SWEEP RenderOnly Sierra Estrella", vertices, faces, material, "mountain")
    obj["nominal_distance_km"] = 30.0
    obj["display_radius_m"] = radius
    obj["profile_source"] = profile["source"]["dataset"]
    obj["orientation_policy"] = ORIENTATION_POLICY
    return obj


def _cylinder_band(collection, center, base_z, radius, angle0, angle1, material, index):
    segments = 128
    vertices = []
    for segment in range(segments + 1):
        azimuth = math.tau * segment / segments
        x = center.x + radius * math.sin(azimuth)
        y = center.y + radius * math.cos(azimuth)
        vertices.extend(
            (
                (x, y, base_z + radius * math.tan(math.radians(angle0))),
                (x, y, base_z + radius * math.tan(math.radians(angle1))),
            )
        )
    faces = [(2 * value, 2 * value + 2, 2 * value + 3, 2 * value + 1) for value in range(segments)]
    return _mesh_object(collection, f"SWEEP RenderOnly Horizon Haze {index}", vertices, faces, material, "haze")


def _haze(collection, center, base_z: float):
    radius = 360.0
    bands = (
        (-3.0, 1.5, (0.72, 0.79, 0.83, 1.0), 0.72, 0.92),
        (1.5, 4.5, (0.66, 0.75, 0.81, 1.0), 0.34, 0.78),
        (4.5, 9.0, (0.57, 0.69, 0.79, 1.0), 0.10, 0.62),
    )
    return [
        _cylinder_band(
            collection,
            center,
            base_z,
            radius,
            angle0,
            angle1,
            _haze_material(f"SWEEP RenderOnly Horizon Haze Material {index}", color, opacity, strength),
            index,
        )
        for index, (angle0, angle1, color, opacity, strength) in enumerate(bands, 1)
    ]


def create_landscape_context(field_minimum, field_maximum, ground_material, profile_path: Path) -> dict[str, object]:
    import bpy
    from mathutils import Vector

    remove_landscape_context()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    validate_profile(profile)
    collection = bpy.data.collections.new(LANDSCAPE_COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    center = (field_minimum + field_maximum) * 0.5
    center.z = 0.0
    base_z = min(float(field_minimum.z), 0.0) - 0.045
    _terrain(collection, center, base_z, ground_material)
    _service_lane(collection, field_minimum, field_maximum, base_z)
    _distant_crops(collection, field_minimum, field_maximum, center, base_z)
    _mountain(collection, center, base_z, profile)
    _haze(collection, center, base_z)
    collection["sweep_ownership"] = RENDER_ONLY_OWNERSHIP
    collection["scientific_geometry"] = False
    collection["parbar_participant"] = False
    collection["profile_path"] = str(profile_path)
    return landscape_report("final", profile)


def configure_finish(scene, enabled: bool) -> dict[str, object]:
    import bpy

    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("SWEEP Presentation Compositor", "CompositorNodeTree")
        scene.compositing_node_group = tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    if not any(item.name == "Image" and item.item_type == "SOCKET" for item in tree.interface.items_tree):
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    output = nodes.new("NodeGroupOutput")
    if not enabled:
        links.new(render_layers.outputs["Image"], output.inputs["Image"])
        return {"enabled": False}
    distortion = nodes.new("CompositorNodeLensdist")
    distortion.inputs["Distortion"].default_value = 0.002
    distortion.inputs["Fit"].default_value = True
    links.new(render_layers.outputs["Image"], distortion.inputs["Image"])
    links.new(distortion.outputs["Image"], output.inputs["Image"])
    return {"enabled": True, "lens_distortion": 0.002}


def set_landscape_for_view(view: str, variant: str) -> dict[str, object]:
    import bpy

    visible_layers = layers_for_view(view, variant)
    collection = bpy.data.collections.get(LANDSCAPE_COLLECTION)
    if collection:
        for obj in collection.objects:
            obj.hide_render = obj.get("sweep_background_layer") not in visible_layers
    finish = configure_finish(bpy.context.scene, "finish" in visible_layers)
    return {"variant": variant, "view": view, "visible_layers": sorted(visible_layers), "finish": finish}


def landscape_report(variant: str, profile: dict[str, object] | None = None) -> dict[str, object]:
    import bpy

    collection = bpy.data.collections.get(LANDSCAPE_COLLECTION)
    objects = list(collection.objects) if collection else []
    if profile is None and collection and collection.get("profile_path"):
        profile = json.loads(Path(collection["profile_path"]).read_text(encoding="utf-8"))
    layer_counts = {}
    for obj in objects:
        layer = obj.get("sweep_background_layer")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
    isolated = all(
        obj.visible_camera
        and not obj.visible_diffuse
        and not obj.visible_glossy
        and not obj.visible_transmission
        and not obj.visible_shadow
        and not obj.visible_volume_scatter
        for obj in objects
    )
    return {
        "ownership": RENDER_ONLY_OWNERSHIP,
        "collection": LANDSCAPE_COLLECTION,
        "object_count": len(objects),
        "layer_counts": layer_counts,
        "active_variant": variant,
        "ray_visibility": RAY_VISIBILITY_CONTRACT,
        "all_objects_camera_only": isolated,
        "scientific_geometry_modified": False,
        "parbar_participant": False,
        "orientation_policy": ORIENTATION_POLICY,
        "site_proxy": SITE_PROXY,
        "profile_peak_sample": profile.get("peak_sample") if profile else None,
        "profile_source": profile.get("source") if profile else None,
    }
