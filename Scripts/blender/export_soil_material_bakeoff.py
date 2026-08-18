"""Run the fixed-scale Blender soil bakeoff and assemble a reference contact sheet."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageStat


ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = ROOT / "Scripts" / "blender" / "render_soil_material_bakeoff.py"
DEFAULT_BLEND = Path(
    r"D:\AlexC\Sorghum_2026_6x10_blender_review\MeasurementStage01\Sorghum_6x10_MeasurementStage01_cycles_ground.blend"
)
DEFAULT_OUTPUT = Path(r"D:\AlexC\Sorghum_2026_6x10_blender_review\Soil_Material_Bakeoff")
REFERENCE_DIR = Path(r"C:\Users\penan\Downloads\Photos-2026-07-09")
VARIANTS = (
    "production_control",
    "legacy_corrected",
    "dirt_scan",
    "brown_mud_scan",
    "hybrid_scan",
    "brown_mud_warm",
    "hybrid_warm",
)
REFERENCE_CROPS = (
    ("ClusterSpacing_3378.png", (0, 2550, 5712, 4284)),
    ("ClusterSpacing_3380.png", (0, 2550, 5712, 4284)),
    ("Tiller_attachment_3418.png", (0, 2400, 5712, 4284)),
    ("Coleoptile_3428.png", (0, 2400, 5712, 4284)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--blend", type=Path, default=DEFAULT_BLEND)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=820)
    return parser.parse_args()


def run_variant(args: argparse.Namespace, variant: str) -> dict[str, object]:
    output = args.output_dir / f"soil_bakeoff_{variant}.png"
    report = args.output_dir / f"soil_bakeoff_{variant}.json"
    log = args.output_dir / f"soil_bakeoff_{variant}.log"
    command = [
        str(args.blender),
        "--background",
        "--python",
        str(RENDER_SCRIPT),
        "--",
        "--blend",
        str(args.blend),
        "--variant",
        variant,
        "--output",
        str(output),
        "--report",
        str(report),
        "--samples",
        str(args.samples),
        "--resolution-x",
        str(args.resolution_x),
        "--resolution-y",
        str(args.resolution_y),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode or not output.is_file() or not report.is_file():
        raise RuntimeError(f"{variant} failed; see {log}")
    return json.loads(report.read_text(encoding="utf-8"))


def image_metrics(image: Image.Image) -> dict[str, object]:
    rgb = image.convert("RGB")
    array = np.asarray(rgb, dtype=np.float32) / 255.0
    luminance = 0.2126 * array[:, :, 0] + 0.7152 * array[:, :, 1] + 0.0722 * array[:, :, 2]
    maximum = array.max(axis=2)
    minimum = array.min(axis=2)
    saturation = np.divide(maximum - minimum, maximum, out=np.zeros_like(maximum), where=maximum > 0)
    gray = np.asarray(rgb.convert("L"), dtype=np.float32) / 255.0
    edge_x = np.abs(np.diff(gray, axis=1)).mean()
    edge_y = np.abs(np.diff(gray, axis=0)).mean()
    return {
        "mean_rgb_8bit": [round(value, 2) for value in ImageStat.Stat(rgb).mean],
        "luminance_percentiles": [round(float(value), 4) for value in np.percentile(luminance, (5, 25, 50, 75, 95))],
        "mean_saturation": round(float(saturation.mean()), 4),
        "mean_local_edge_contrast": round(float(0.5 * (edge_x + edge_y)), 5),
    }


def fitted(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    result = image.convert("RGB").copy()
    result.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (235, 235, 235))
    canvas.paste(result, ((size[0] - result.width) // 2, (size[1] - result.height) // 2))
    return canvas


def make_contact_sheet(args: argparse.Namespace, reports: list[dict[str, object]]) -> dict[str, object]:
    font = ImageFont.load_default(size=24)
    small_font = ImageFont.load_default(size=17)
    cell = (560, 390)
    header = 60
    references: list[tuple[str, Image.Image]] = []
    reference_metrics = {}
    for name, crop_box in REFERENCE_CROPS:
        path = REFERENCE_DIR / name
        if not path.is_file():
            continue
        with Image.open(path) as source:
            crop = source.convert("RGB").crop(crop_box)
        references.append((name, crop))
        reference_metrics[name] = {"crop_box": list(crop_box), **image_metrics(crop)}

    rows = 1 + (len(references) + 2) // 3 + (len(reports) + 2) // 3
    sheet = Image.new("RGB", (3 * cell[0], rows * (cell[1] + header)), (246, 246, 243))
    draw = ImageDraw.Draw(sheet)
    draw.text((22, 14), "Measured field-photo soil crops (visual truth; color is camera-dependent)", fill=(20, 20, 20), font=font)
    y = header
    for index, (name, crop) in enumerate(references):
        column = index % 3
        row = index // 3
        x = column * cell[0]
        top = y + row * (cell[1] + header)
        sheet.paste(fitted(crop, cell), (x, top))
        draw.text((x + 12, top + cell[1] + 8), name, fill=(25, 25, 25), font=small_font)

    render_y = y + ((len(references) + 2) // 3) * (cell[1] + header)
    draw.text((22, render_y + 14), "Fixed 1.2 m Blender patch - identical camera, Nishita sky, AgX, exposure and Cycles settings", fill=(20, 20, 20), font=font)
    render_y += header
    render_metrics = {}
    for index, report in enumerate(reports):
        path = Path(report["render"])
        with Image.open(path) as source:
            render = source.convert("RGB")
            # Exclude the narrow scale-bar band from descriptive material statistics.
            roi = render.crop((0, 0, render.width, round(render.height * 0.86)))
        render_metrics[report["variant"]] = image_metrics(roi)
        column = index % 3
        row = index // 3
        x = column * cell[0]
        top = render_y + row * (cell[1] + header)
        sheet.paste(fitted(render, cell), (x, top))
        label = report["variant"].replace("_", " ")
        draw.text((x + 12, top + cell[1] + 8), label, fill=(25, 25, 25), font=small_font)

    contact_sheet = args.output_dir / "soil_material_bakeoff_contact_sheet.jpg"
    sheet.save(contact_sheet, quality=94, subsampling=0)
    metrics = {
        "protocol": {
            "patch_width_m": 1.2,
            "scale_bar_segment_m": 0.10,
            "lighting": "inherited unchanged from MeasurementStage01 production Blender scene",
            "camera_and_render_settings_fixed_across_candidates": True,
            "metrics_are_descriptive_not_an_automatic_material_selector": True,
        },
        "reference_photo_crops": reference_metrics,
        "renders": render_metrics,
        "contact_sheet": str(contact_sheet.resolve()),
    }
    (args.output_dir / "soil_material_bakeoff_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    return metrics


def main() -> None:
    args = parse_args()
    args.blender = args.blender.resolve()
    args.blend = args.blend.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.blender.is_file():
        raise FileNotFoundError(args.blender)
    if not args.blend.is_file():
        raise FileNotFoundError(args.blend)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = [run_variant(args, variant) for variant in VARIANTS]
    metrics = make_contact_sheet(args, reports)
    manifest = {
        "source_blend": str(args.blend),
        "render_script": str(RENDER_SCRIPT),
        "variants": reports,
        "validation": metrics,
        "scientific_scene_modified": False,
    }
    (args.output_dir / "soil_material_bakeoff_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output_dir": str(args.output_dir), "contact_sheet": metrics["contact_sheet"]}, indent=2))


if __name__ == "__main__":
    main()
