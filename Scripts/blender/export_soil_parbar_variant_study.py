"""Run the Blender soil/PARBAR variant study and make a labeled contact sheet."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--output-blend", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    return parser.parse_args()


def make_contact_sheet(records: list[dict[str, object]], output: Path) -> None:
    columns = 2
    rows = 4
    cell_width = 800
    image_height = 450
    label_height = 74
    sheet = Image.new("RGB", (columns * cell_width, rows * (image_height + label_height)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=22)
    detail_font = ImageFont.load_default(size=16)
    for index, record in enumerate(records):
        x = (index % columns) * cell_width
        y = (index // columns) * (image_height + label_height)
        with Image.open(record["output"]) as source:
            source = source.convert("RGB")
            source.thumbnail((cell_width, image_height), Image.Resampling.LANCZOS)
            paste_x = x + (cell_width - source.width) // 2
            paste_y = y + (image_height - source.height) // 2
            sheet.paste(source, (paste_x, paste_y))
        draw.text((x + 14, y + image_height + 8), record["id"], fill=(245, 245, 245), font=font)
        description = record["description"]
        draw.text((x + 14, y + image_height + 39), description, fill=(190, 190, 190), font=detail_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> None:
    args = parse_args()
    script = Path(__file__).with_name("render_soil_parbar_variant_study.py").resolve()
    command = [
        str(args.blender.resolve()), "--background", "--python", str(script), "--",
        "--blend", str(args.blend.resolve()),
        "--output-blend", str(args.output_blend.resolve()),
        "--output-dir", str(args.output_dir.resolve()),
        "--samples", str(args.samples),
        "--resolution-x", str(args.resolution_x),
        "--resolution-y", str(args.resolution_y),
    ]
    subprocess.run(command, check=True)
    report_path = args.output_dir.resolve() / "soil_parbar_variant_study_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = report["variants"]
    if len(records) != 8 or not all(Path(record["output"]).exists() for record in records):
        raise RuntimeError("Blender did not produce all eight variant renders")
    contact_sheet = args.output_dir.resolve() / "soil_parbar_variant_contact_sheet.png"
    make_contact_sheet(records, contact_sheet)
    print(f"SWEEP_VARIANT_CONTACT_SHEET={contact_sheet}")


if __name__ == "__main__":
    main()
