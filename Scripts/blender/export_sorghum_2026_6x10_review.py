"""Export and render both 2026 6x10 scenes as a Blender Cycles review."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON_BINDING = ROOT / "PythonBinding"
BLENDER_SCRIPTS = ROOT / "Scripts" / "blender"
LEAF_MATERIAL_SCRIPTS = ROOT / "Scripts" / "sorghum_leaf_materials"
sys.path.insert(0, str(PYTHON_BINDING))
sys.path.insert(0, str(BLENDER_SCRIPTS))
sys.path.insert(0, str(LEAF_MATERIAL_SCRIPTS))

from sorghum_render_2026_6x10 import (  # noqa: E402
    SESSION_LABELS,
    VIEWS,
    make_multiview_contact_sheet,
)
import sorghum_2026_background as background  # noqa: E402
import bake_continuous_sorghum_leaf_atlas as continuous_leaf_atlas  # noqa: E402


SESSIONS = ("MeasurementStage01", "MeasurementStage02")
APP = ROOT / "out/build/vs2026-x64/EvoEngine_App/RelWithDebInfo/DigitalAgricultureApp.exe"
PROJECT = ROOT / "Resources/DigitalAgricultureProject/test_lsystem_sorghum.eveproj"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe")
PREPARE = ROOT / "scripts/blender/prepare_lsystem_cycles_scene.py"
GROUND = ROOT / "scripts/blender/setup_ground_displacement_render.py"
RENDER = ROOT / "scripts/blender/render_sorghum_2026_6x10_multiview.py"
DEFAULT_OUTPUT = ROOT / "out/exports/sorghum_2026_6x10_blender"
LEAF_ALBEDO_MASTER = LEAF_MATERIAL_SCRIPTS / "assets/leaf_anatomy_master_v2.png"
SCIENTIFIC_SCENE_BASELINES = {
    "MeasurementStage01": "d3af44b32f2ff6443804a7e7e6de460681097f6345affbe7563c0a15eede4081",
    "MeasurementStage02": "6bacc4fa7dd0d7e8b9d564912c919c81c39e144903dd6da7afff361a8c23fb88",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=APP)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    parser.add_argument("--displacement-strength", type=float, default=0.0)
    parser.add_argument("--macro-displacement-strength", type=float, default=0.0)
    parser.add_argument("--material-displacement-strength", type=float, default=0.042)
    parser.add_argument("--leaf-bend-degrees", type=float, default=42.0)
    parser.add_argument("--leaf-bend-start", type=float, default=0.20)
    parser.add_argument("--background-bakeoff", action="store_true")
    parser.add_argument("--skip-leaf-bakeoff", action="store_true")
    parser.add_argument("--leaf-atlas-tile-size", type=int, default=1536)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_logged(command: list[str], log: Path) -> subprocess.CompletedProcess[str]:
    log.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout, encoding="utf-8")
    return result


def close(actual: float | None, expected: float, tolerance: float = 1.0e-5) -> bool:
    return actual is not None and abs(float(actual) - expected) <= tolerance


def scene_asset(session: str) -> str:
    return f"GeneratedAssets/Experiments/Sorghum2026_6x10/Scenes/Sorghum_6x10_{session}.evescene"


def validate_export(gltf: Path, manifest_path: Path, session: str) -> dict[str, object]:
    if not gltf.is_file() or not manifest_path.is_file() or not gltf.with_suffix(".bin").is_file():
        raise RuntimeError(f"{session}: EvoEngine did not create a complete glTF export")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sorghum_ls") != 60 or manifest.get("source_scene") != scene_asset(session):
        raise RuntimeError(f"{session}: unexpected export manifest: {manifest}")
    gltf_data = json.loads(gltf.read_text(encoding="utf-8"))
    names = {node.get("name") for node in gltf_data.get("nodes", [])}
    required = {"Ground Mesh", "PARBAR_GenotypeA", "PARBAR_GenotypeB", "PARBAR_GenotypeC"}
    if not required <= names:
        raise RuntimeError(f"{session}: glTF is missing context roots: {sorted(required - names)}")
    if sum(1 for name in names if isinstance(name, str) and name.startswith("Genotype") and "_LSystem_" in name) != 60:
        raise RuntimeError(f"{session}: glTF does not contain 60 named plant roots")
    return manifest


def make_background_bakeoff_contact_sheet(report: dict[str, object], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    variants = report["variants"]
    margin, tile_width, tile_height, label_height = 24, 640, 360, 44
    canvas = Image.new("RGB", (2 * tile_width + 3 * margin, 3 * (tile_height + label_height) + 4 * margin + 62), (17, 24, 28))
    draw = ImageDraw.Draw(canvas)
    regular = Path(r"C:\Windows\Fonts\segoeui.ttf")
    bold = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    title_font = ImageFont.truetype(str(bold), 32) if bold.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(regular), 24) if regular.exists() else ImageFont.load_default()
    draw.text((margin, 18), "2026 Sorghum 6x10 | Stage 2 background landscape bakeoff", font=title_font, fill=(245, 248, 247))
    for index, row in enumerate(variants):
        grid_row, column = divmod(index, 2)
        x = margin + column * (tile_width + margin)
        y = 80 + margin + grid_row * (tile_height + label_height + margin)
        draw.text((x, y), f"{index + 1:02d}  {str(row['variant']).replace('_', ' ').title()}", font=label_font, fill=(218, 227, 225))
        with Image.open(row["output"]).convert("RGB") as image:
            image.thumbnail((tile_width, tile_height))
            canvas.paste(image, (x + (tile_width - image.width) // 2, y + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def make_leaf_bakeoff_contact_sheet(rows: list[dict[str, object]], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    margin, tile_width, tile_height, label_height = 24, 640, 426, 70
    columns, row_count = 3, 2
    canvas = Image.new(
        "RGB",
        (
            columns * tile_width + (columns + 1) * margin,
            row_count * (tile_height + label_height) + (row_count + 1) * margin + 68,
        ),
        (17, 24, 28),
    )
    draw = ImageDraw.Draw(canvas)
    regular = Path(r"C:\Windows\Fonts\segoeui.ttf")
    bold = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    title_font = ImageFont.truetype(str(bold), 32) if bold.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(regular), 22) if regular.exists() else ImageFont.load_default()
    draw.text(
        (margin, 18),
        "Sorghum leaf junction | fixed-camera validation ladder",
        font=title_font,
        fill=(245, 248, 247),
    )
    for index, row in enumerate(rows):
        grid_row, column = divmod(index, columns)
        x = margin + column * (tile_width + margin)
        y = 78 + margin + grid_row * (tile_height + label_height + margin)
        draw.text((x, y), f"{index + 1}. {row['label']}", font=label_font, fill=(218, 227, 225))
        with Image.open(row["output"]).convert("RGB") as source:
            source.thumbnail((tile_width, tile_height))
            canvas.paste(source, (x + (tile_width - source.width) // 2, y + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", optimize=True)


def render_leaf_bakeoff(
    args: argparse.Namespace,
    session: str,
    gltf: Path,
    manifest_path: Path,
    final_ground_blend: Path,
    session_dir: Path,
) -> dict[str, object]:
    bakeoff_dir = session_dir / "leaf_junction_bakeoff"
    legacy_base = bakeoff_dir / "legacy_prepared.blend"
    legacy_ground = bakeoff_dir / "legacy_ground.blend"
    bakeoff_dir.mkdir(parents=True, exist_ok=True)
    prepare = run_logged(
        [
            str(args.blender), "--background", "--python", str(PREPARE), "--",
            "--gltf", str(gltf),
            "--manifest", str(manifest_path),
            "--output-blend", str(legacy_base),
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
        ],
        bakeoff_dir / "legacy_prepare.log",
    )
    if prepare.returncode or not legacy_base.is_file():
        raise RuntimeError(f"{session}: legacy leaf control preparation failed")
    legacy_prepare_report = json.loads(
        legacy_base.with_name(legacy_base.stem + "_blender_report.json").read_text(encoding="utf-8")
    )
    if any(
        "variants_v2" in Path(value).name
        for value in legacy_prepare_report.get("leaf_textures", {}).values()
        if value
    ):
        raise RuntimeError(f"{session}: legacy control unexpectedly used the V2 atlas")
    ground = run_logged(
        [
            str(args.blender), "--background", "--python", str(GROUND), "--",
            "--blend", str(legacy_base),
            "--output-blend", str(legacy_ground),
            "--render-output", str(bakeoff_dir / "unused.png"),
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
            "--displacement-strength", str(args.displacement_strength),
            "--macro-displacement-strength", str(args.macro_displacement_strength),
            "--material-displacement-strength", str(args.material_displacement_strength),
            "--skip-render",
        ],
        bakeoff_dir / "legacy_ground.log",
    )
    if ground.returncode or not legacy_ground.is_file():
        raise RuntimeError(f"{session}: legacy leaf control ground preparation failed")

    variants = (
        ("current_control", "Current control: legacy geometry + legacy atlas", legacy_ground, "legacy_all_components", "legacy"),
        ("geometry_repair", "Blade-only geometry repair", legacy_ground, "blade_only", "legacy"),
        ("continuous_albedo", "Continuous anatomical albedo", final_ground_blend, "blade_only", "continuous_albedo"),
        ("continuous_pbr", "Continuous albedo + PBR maps", final_ground_blend, "blade_only", "continuous_pbr"),
        ("final_shader", "Final thickness / underside / anisotropy", final_ground_blend, "blade_only", "final"),
    )
    rows = []
    for name, label, source_blend, bend_mode, shader_stage in variants:
        variant_dir = bakeoff_dir / name
        render_dir = variant_dir / "renders"
        output_blend = variant_dir / f"{name}.blend"
        result = run_logged(
            [
                str(args.blender), "--background", "--python", str(RENDER), "--",
                "--blend", str(source_blend),
                "--output-blend", str(output_blend),
                "--output-dir", str(render_dir),
                "--session", session,
                "--samples", str(args.samples),
                "--resolution-x", str(args.resolution_x),
                "--resolution-y", str(args.resolution_y),
                "--views", "genotype_a_basal",
                "--leaf-bend-degrees", str(args.leaf_bend_degrees),
                "--leaf-bend-start", str(args.leaf_bend_start),
                "--leaf-bend-mode", bend_mode,
                "--leaf-shader-stage", shader_stage,
                "--background-profile", str(args.background_profile),
                "--background-variant", "final",
            ],
            variant_dir / "render.log",
        )
        report_path = variant_dir / f"{session}_blender_render_report.json"
        if result.returncode or not report_path.is_file():
            raise RuntimeError(f"{session}: leaf bakeoff variant {name} failed")
        variant_report = json.loads(report_path.read_text(encoding="utf-8"))
        output = Path(variant_report["views"][0]["output"])
        if not output.is_file():
            raise RuntimeError(f"{session}: leaf bakeoff variant {name} produced no image")
        rows.append(
            {
                "name": name,
                "label": label,
                "output": str(output),
                "sha256": sha256(output),
                "bend": variant_report["leaf_bend"],
                "shader_stage": variant_report["leaf_shader_stage"],
                "leaf_shader": variant_report["leaf_shader"],
            }
        )
    contact_sheet = bakeoff_dir / f"{session}_leaf_junction_bakeoff.png"
    make_leaf_bakeoff_contact_sheet(rows, contact_sheet)
    report = {
        "schema_version": 1,
        "ownership": "blender_presentation_only",
        "scientific_scene_modified": False,
        "fixed_view": "genotype_a_basal",
        "variants": rows,
        "contact_sheet": str(contact_sheet),
        "contact_sheet_sha256": sha256(contact_sheet),
    }
    report_path = bakeoff_dir / f"{session}_leaf_junction_bakeoff_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def render_background_bakeoff(
    args: argparse.Namespace,
    session: str,
    ground_blend: Path,
    session_dir: Path,
) -> dict[str, object]:
    bakeoff_dir = session_dir / "background_bakeoff"
    render_dir = bakeoff_dir / "renders"
    output_blend = bakeoff_dir / f"Sorghum_6x10_{session}_background_bakeoff.blend"
    result = run_logged(
        [
            str(args.blender), "--background", "--python", str(RENDER), "--",
            "--blend", str(ground_blend),
            "--output-blend", str(output_blend),
            "--output-dir", str(render_dir),
            "--session", session,
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
            "--leaf-bend-degrees", str(args.leaf_bend_degrees),
            "--leaf-bend-start", str(args.leaf_bend_start),
            "--leaf-shader-stage", "final",
            "--background-profile", str(args.background_profile),
            "--background-bakeoff",
        ],
        bakeoff_dir / "blender_background_bakeoff.log",
    )
    report_path = bakeoff_dir / f"{session}_background_bakeoff_report.json"
    if result.returncode or not report_path.is_file() or not output_blend.is_file():
        raise RuntimeError(f"{session}: background bakeoff failed; see {bakeoff_dir / 'blender_background_bakeoff.log'}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if [row["variant"] for row in report["variants"]] != list(background.BACKGROUND_VARIANTS):
        raise RuntimeError(f"{session}: background bakeoff variants are incomplete")
    for row in report["variants"]:
        image = Path(row["output"])
        if not image.is_file():
            raise RuntimeError(f"{session}: missing background bakeoff image {image}")
        row["sha256"] = sha256(image)
    contact_sheet = bakeoff_dir / f"{session}_background_bakeoff_contact_sheet.png"
    make_background_bakeoff_contact_sheet(report, contact_sheet)
    report["contact_sheet"] = str(contact_sheet)
    report["contact_sheet_sha256"] = sha256(contact_sheet)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def export_session(args: argparse.Namespace, session: str) -> dict[str, object]:
    session_dir = args.output_dir / session
    stem = f"Sorghum_6x10_{session}"
    gltf = session_dir / f"{stem}.gltf"
    manifest_path = session_dir / f"{stem}_manifest.json"
    base_blend = session_dir / f"{stem}_cycles.blend"
    ground_blend = session_dir / f"{stem}_cycles_ground.blend"
    review_blend = session_dir / f"{stem}_cycles_ground_multiview.blend"
    render_dir = session_dir / "renders"
    session_dir.mkdir(parents=True, exist_ok=True)
    scientific_scene = args.project.parent / "Assets" / scene_asset(session)
    if sha256(scientific_scene) != SCIENTIFIC_SCENE_BASELINES[session]:
        raise RuntimeError(f"{session}: scientific scene no longer matches the locked background-render baseline")

    project_bytes = args.project.read_bytes()
    try:
        export_result = run_logged(
            [
                str(args.app),
                "--export-lsystem-blender-scene",
                "--project", str(args.project),
                "--rt-scene", scene_asset(session),
                "--blender-preserve-lsystem-state",
                "--blender-output", str(gltf),
            ],
            session_dir / "evoengine_export.log",
        )
    finally:
        args.project.write_bytes(project_bytes)
    if args.project.read_bytes() != project_bytes:
        raise RuntimeError(f"{session}: failed to restore the protected project manifest")
    export_manifest = validate_export(gltf, manifest_path, session)

    prepare_result = run_logged(
        [
            str(args.blender), "--background", "--python", str(PREPARE), "--",
            "--gltf", str(gltf),
            "--manifest", str(manifest_path),
            "--output-blend", str(base_blend),
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
            "--leaf-atlas-dir", str(args.leaf_atlas_dir),
        ],
        session_dir / "blender_prepare.log",
    )
    if prepare_result.returncode or not base_blend.is_file():
        raise RuntimeError(f"{session}: Blender preparation failed; see {session_dir / 'blender_prepare.log'}")
    prepare_report_path = base_blend.with_name(base_blend.stem + "_blender_report.json")
    prepare_report = json.loads(prepare_report_path.read_text(encoding="utf-8"))
    leaf_textures = prepare_report.get("leaf_textures", {})
    if (
        not leaf_textures
        or any(not leaf_textures.get(key) for key in ("albedo", "normal", "roughness", "height", "ao", "metallic", "thickness"))
        or any("variants_v2" not in Path(value).name for value in leaf_textures.values())
    ):
        raise RuntimeError(f"{session}: continuous leaf atlas was not assigned: {leaf_textures}")
    exported_roles = {
        "leaf_objects": 60,
        "stem_objects": 60,
        "parbar_long_bar_objects": 9,
        "parbar_panel_objects": 3,
    }
    for role, expected_count in exported_roles.items():
        if len(prepare_report.get(role, [])) != expected_count:
            raise RuntimeError(
                f"{session}: expected {expected_count} {role}, got {len(prepare_report.get(role, []))}"
            )
    if prepare_report.get("stem_material") != "SWEEP_LSystem_Stem_Cycles":
        raise RuntimeError(f"{session}: calibrated stem material was not assigned")
    if prepare_report.get("stem_normals_recalculated") != 60:
        raise RuntimeError(f"{session}: expected normal repair on all 60 stem meshes")
    metal_objects = prepare_report.get("parbar_metal_objects", [])
    metal_shader = prepare_report.get("parbar_metal_shader", {})
    if (
        not metal_objects
        or prepare_report.get("parbar_metal_beveled_objects") != len(metal_objects)
        or not close(metal_shader.get("metallic"), 1.0)
        or metal_shader.get("roughness_range") != [0.24, 0.46]
        or not close(metal_shader.get("anisotropic"), 0.28)
        or not close(metal_shader.get("micro_bump_distance_m"), 0.00008)
    ):
        raise RuntimeError(f"{session}: brushed PARBAR metal contract failed: {metal_shader}")

    ground_result = run_logged(
        [
            str(args.blender), "--background", "--python", str(GROUND), "--",
            "--blend", str(base_blend),
            "--output-blend", str(ground_blend),
            "--render-output", str(session_dir / "unused.png"),
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
            "--displacement-strength", str(args.displacement_strength),
            "--macro-displacement-strength", str(args.macro_displacement_strength),
            "--material-displacement-strength", str(args.material_displacement_strength),
            "--skip-render",
        ],
        session_dir / "blender_ground.log",
    )
    if ground_result.returncode or not ground_blend.is_file():
        raise RuntimeError(f"{session}: Blender ground preparation failed; see {session_dir / 'blender_ground.log'}")
    ground_report_path = ground_blend.with_name(ground_blend.stem + "_report.json")
    ground_report = json.loads(ground_report_path.read_text(encoding="utf-8"))
    ground_context = ground_report["soil_context"]
    physical_widths = ground_report.get("pbr_physical_width_m", {})
    ground_shader = ground_report.get("soil_shader", {})
    if (
        ground_report.get("height_extension") != "REPEAT"
        or not close(physical_widths.get("brown_mud_dry"), 1.3)
        or not close(physical_widths.get("dirt"), 2.0)
        or ground_shader.get("scan_height_applied_more_than_once")
        or not ground_shader.get("material_output_displacement_linked")
        or ground_context.get("ownership") != "blender_presentation_only"
        or ground_context.get("plant_base_count") != 60
        or not close(ground_context.get("minimum_culm_overlap_m"), 0.002)
        or ground_context.get("contact_clod_count") != 360
        or ground_context.get("clod_count", 0) <= 360
        or ground_context.get("small_aggregate_count", 0) <= 5000
        or ground_context.get("pebble_count", 0) <= 500
        or ground_context.get("residue_fragment_count", 0) <= 20
        or len(ground_context.get("row_centers_y_m", [])) != 6
        or not close(ground_context.get("furrow_ridge_height_m"), 0.014)
        or ground_context.get("scientific_scene_modified")
    ):
        raise RuntimeError(f"{session}: dry soil context validation failed: {ground_report}")

    bakeoff_report = None
    if args.background_bakeoff and session == "MeasurementStage02":
        bakeoff_report = render_background_bakeoff(args, session, ground_blend, session_dir)

    render_result = run_logged(
        [
            str(args.blender), "--background", "--python", str(RENDER), "--",
            "--blend", str(ground_blend),
            "--output-blend", str(review_blend),
            "--output-dir", str(render_dir),
            "--session", session,
            "--samples", str(args.samples),
            "--resolution-x", str(args.resolution_x),
            "--resolution-y", str(args.resolution_y),
            "--leaf-bend-degrees", str(args.leaf_bend_degrees),
            "--leaf-bend-start", str(args.leaf_bend_start),
            "--leaf-shader-stage", "final",
            "--background-profile", str(args.background_profile),
            "--background-variant", "final",
        ],
        session_dir / "blender_multiview.log",
    )
    report_path = session_dir / f"{session}_blender_render_report.json"
    if render_result.returncode or not report_path.is_file() or not review_blend.is_file():
        raise RuntimeError(f"{session}: Blender multi-view render failed; see {session_dir / 'blender_multiview.log'}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if [row["view"] for row in report["views"]] != list(VIEWS):
        raise RuntimeError(f"{session}: Blender report does not contain the twelve expected views")
    for row in report["views"]:
        output = Path(row["output"])
        if not output.is_file():
            raise RuntimeError(f"{session}: missing rendered view {output}")
        row["sha256"] = sha256(output)
    shader = report["leaf_shader"]
    stem = report["stem_shader"]
    soil = report["soil_shader"]
    world = report["world"]
    color = report["color_management"]
    bend = report["leaf_bend"]
    soil_context = report["soil_context"]
    landscape = report["landscape"]
    atlas = args.leaf_atlas_report
    seam = atlas["seam_metrics"]
    texture_paths = shader["texture_paths"]
    checks = {
        "leaf_subsurface_weight": close(shader["subsurface_weight"], 0.06),
        "leaf_subsurface_scale": close(shader["subsurface_scale"], 0.009),
        "leaf_specular": close(shader["specular_ior_level"], 0.35),
        "leaf_color_saturation": close(shader["color_saturation"], 1.05),
        "leaf_color_value": close(shader["color_value"], 0.88),
        "leaf_anisotropic": close(shader["anisotropic"], 0.20),
        "leaf_thickness_driven_sss": shader["subsurface_source"] == "SWEEP Leaf Thickness to SSS",
        "leaf_restrained_underside": shader["base_color_source"] == "SWEEP Leaf Restrained Underside Tint",
        "continuous_leaf_atlas": set(texture_paths) >= {
            "albedo", "normal", "roughness", "ao", "height", "metallic", "thickness"
        }
        and all("variants_v2" in Path(path).name for path in texture_paths.values()),
        "continuous_leaf_atlas_ownership": atlas["ownership"] == "blender_presentation_only"
        and not atlas["scientific_geometry_modified"]
        and atlas["variant_count"] == 9,
        "continuous_leaf_atlas_seam": seam["albedo_mean_rgb_255"] <= 4.0
        and seam["normal_mean_rgb_255"] <= 8.0
        and seam["roughness_mean_255"] <= 5.1
        and seam["height_mean_255"] <= 8.0
        and seam["ao_mean_255"] <= 5.1,
        "stem_base_color": all(
            close(actual, expected) for actual, expected in zip(stem["base_color"], (0.38, 0.54, 0.20, 1.0))
        ),
        "stem_roughness": close(stem["roughness"], 0.60),
        "stem_specular": close(stem["specular_ior_level"], 0.30),
        "stem_indirect_fill": close(stem["emission_strength"], 0.25),
        "soil_color_saturation": close(soil["color_saturation"], 1.05),
        "soil_color_value": close(soil["color_value"], 0.64),
        "soil_warm_tint": close(soil["warm_tint_factor"], 0.60)
        and all(
            close(actual, expected)
            for actual, expected in zip(soil["warm_tint_linear_rgba"], (0.55, 0.23, 0.06, 1.0))
        ),
        "soil_scan_roughness_uncompressed": ground_shader.get("roughness")
        == "direct scan maps; no narrow remap",
        "soil_neutral_specular": close(soil["specular_ior_level"], 0.5),
        "soil_normal_strength": close(soil["normal_strength"], 1.0),
        "soil_height_bump": close(soil["height_bump_strength"], 0.30)
        and close(soil["height_bump_distance_m"], 0.003),
        "soil_crack_bump": close(soil["crack_bump_strength"], 0.12)
        and close(soil["crack_bump_distance_m"], 0.0012),
        "soil_dirt_fraction": close(soil["dirt_mix_minimum"], 0.08)
        and close(soil["dirt_mix_maximum"], 0.28),
        "soil_true_displacement": close(soil["material_displacement_scale_m"], 0.042)
        and close(soil["material_displacement_midlevel"], 0.58),
        "soil_height_repeats": ground_report["height_extension"] == "REPEAT",
        "soil_contact_geometry": soil_context["collection"] == "SWEEP_RenderOnly_SoilContext"
        and soil_context["object_count"] == 6
        and soil_context["plant_base_count"] == 60
        and soil_context["clod_count"] == ground_context["clod_count"]
        and soil_context["small_aggregate_count"] == ground_context["small_aggregate_count"]
        and soil_context["pebble_count"] == ground_context["pebble_count"]
        and soil_context["residue_fragment_count"] == ground_context["residue_fragment_count"],
        "soil_context_presentation_only": soil_context["ownership"] == "blender_presentation_only"
        and not soil_context["scientific_scene_modified"],
        "nishita_sun_elevation": close(world["sun_elevation"], 0.9599310885968813),
        "nishita_sun_rotation": close(world["sun_rotation"], 2.356194490192345),
        "nishita_sun_intensity": close(world["sun_intensity"], 0.35),
        "nishita_altitude": close(world["altitude"], 100.0),
        "agx": color["view_transform"] == "AgX",
        "exposure": close(color["exposure"], -0.9),
        "presentation_leaf_bend": close(bend["bend_degrees"], args.leaf_bend_degrees),
        "presentation_leaf_bend_start": close(bend["bend_start_fraction"], args.leaf_bend_start),
        "all_leaf_objects_bent": bend["leaf_object_count"] == 60 and bend["deformed_vertex_count"] > 0,
        "blade_only_leaf_bend": bend["method"]
        == "atlas_semantic_blade_only_longitudinal_uv_distal_rotation"
        and bend["blade_surface_component_count"] > 0
        and bend["bent_blade_group_count"] > 0
        and bend["unbent_proximal_group_count"] > 0
        and bend["blade_base_max_displacement_m"] <= 1.0e-7
        and close(bend["junction_weld_distance_m"], 1.0e-6)
        and bend["junction_weld_count"] > 0,
        "scientific_geometry_untouched": not bend["canonical_descriptors_modified"] and not bend["scientific_scenes_modified"],
        "landscape_presentation_only": landscape["ownership"] == background.RENDER_ONLY_OWNERSHIP
        and not landscape["scientific_geometry_modified"]
        and not landscape["parbar_participant"],
        "landscape_camera_ray_isolated": landscape["all_objects_camera_only"]
        and landscape["ray_visibility"] == background.RAY_VISIBILITY_CONTRACT,
        "landscape_layers_complete": landscape["layer_counts"]
        == {"terrain": 1, "lane": 5, "agriculture": 1, "mountain": 1, "haze": 3},
        "sierra_estrella_scale": 1.0 <= landscape["profile_peak_sample"]["elevation_angle_deg"] <= 4.0,
        "sierra_estrella_provenance": landscape["profile_source"]["license"] == background.SIERRA_PROFILE_LICENSE
        and landscape["orientation_policy"] == background.ORIENTATION_POLICY,
        "measurement_view_background_rules": all(
            "mountain" not in row["landscape"]["visible_layers"]
            and "haze" not in row["landscape"]["visible_layers"]
            for row in report["views"]
            if row["view"] == "near_top_down" or row["view"].endswith(("_basal", "_leaf"))
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"{session}: approved Blender settings were not preserved: {checks}")
    leaf_bakeoff_report = None
    if not args.skip_leaf_bakeoff and session == "MeasurementStage01":
        leaf_bakeoff_report = render_leaf_bakeoff(
            args,
            session,
            gltf,
            manifest_path,
            ground_blend,
            session_dir,
        )
    contact_sheet = session_dir / f"{session}_blender_multiview.png"
    make_multiview_contact_sheet(session, report["views"], contact_sheet)
    report.update(
        {
            "scene_sha256": sha256(scientific_scene),
            "gltf_sha256": sha256(gltf),
            "output_blend_sha256": sha256(review_blend),
            "contact_sheet": str(contact_sheet),
            "contact_sheet_sha256": sha256(contact_sheet),
            "evoengine_export_exit_status": export_result.returncode,
            "evoengine_export_teardown_warning": export_result.returncode != 0,
            "evoengine_export_manifest": export_manifest,
            "ground_presentation_report": ground_report,
            "background_bakeoff": bakeoff_report,
            "leaf_junction_bakeoff": leaf_bakeoff_report,
            "leaf_atlas_validation": atlas,
            "approved_settings_checks": checks,
            "session_label": SESSION_LABELS[session],
        }
    )
    if sha256(scientific_scene) != SCIENTIFIC_SCENE_BASELINES[session]:
        raise RuntimeError(f"{session}: Blender presentation changed the scientific scene")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    args.app = args.app.resolve()
    args.project = args.project.resolve()
    args.blender = args.blender.resolve()
    args.output_dir = args.output_dir.resolve()
    for required in (
        args.app,
        args.project,
        args.blender,
        PREPARE,
        GROUND,
        RENDER,
        Path(background.__file__),
        Path(continuous_leaf_atlas.__file__),
        LEAF_ALBEDO_MASTER,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    args.background_profile = background.prepare_sierra_profile(args.output_dir / "background_assets")
    leaf_outputs = continuous_leaf_atlas.bake_continuous_atlas(
        LEAF_ALBEDO_MASTER,
        args.output_dir / "leaf_assets",
        tile_size=args.leaf_atlas_tile_size,
    )
    args.leaf_atlas_dir = leaf_outputs["albedo"].parent
    args.leaf_atlas_report = json.loads(leaf_outputs["report"].read_text(encoding="utf-8"))
    reports = [export_session(args, session) for session in SESSIONS]
    combined = {
        "schema_version": 1,
        "experiment_id": "Sorghum2026_6x10",
        "renderer": "Blender Cycles",
        "presentation_only": True,
        "scientific_scene_assets_modified": False,
        "background_profile": str(args.background_profile),
        "background_profile_sha256": sha256(args.background_profile),
        "leaf_atlas": args.leaf_atlas_report,
        "sessions": reports,
    }
    output = args.output_dir / "blender_render_report.json"
    output.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
