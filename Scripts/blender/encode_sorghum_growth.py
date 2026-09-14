"""Encode checked Blender PNGs as an MP4 and create a growth contact sheet."""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PythonBinding"))
from sorghum_growth_export import sha256, validate_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--blender-output", type=Path)
    parser.add_argument(
        "--renders",
        type=Path,
        help="Frame directory selected with Blender --render-output",
    )
    parser.add_argument("--hold-seconds", type=float, default=1.5)
    args = parser.parse_args()
    if not math.isfinite(args.hold_seconds) or args.hold_seconds < 0:
        parser.error("Hold duration must be finite and nonnegative")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    hold_frames = round(args.hold_seconds * manifest["fps"])
    output = args.blender_output or args.manifest.parent / "blender"
    renders = args.renders or output / "renders"
    binding = json.loads((renders / "source.json").read_text(encoding="utf-8"))
    if (
        binding["source_manifest_sha256"] != sha256(args.manifest)
        or binding["cache_sha256"] != sha256(output / "growth.usdc")
        or binding["fps"] != manifest["fps"]
    ):
        raise ValueError("Rendered frames belong to another export/cache")
    files = [renders / f"growth_{f['frame']:04d}.png" for f in manifest["frames"]]
    with Image.open(files[0]) as image:
        width, height = image.size
    if width % 2 or height % 2:
        raise ValueError("H.264 output requires even image dimensions")
    for path in files:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.size != (width, height):
                raise ValueError(f"Unexpected frame size: {path}")
    destination = renders.parent if args.renders else output
    movie = destination / "abc_growth.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(manifest["fps"]),
            "-start_number",
            "1",
            "-i",
            str(renders / "growth_%04d.png"),
            "-vf",
            f"trim=end_frame={len(files)},tpad=stop_mode=clone:stop={hold_frames}",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(movie),
        ],
        check=True,
    )
    count, duration = imageio_ffmpeg.count_frames_and_secs(str(movie))
    expected = len(files) + hold_frames
    if count != expected:
        raise ValueError(f"Encoded {count} frames, expected {expected}")
    milestones = sorted(
        {0, len(files) // 4, len(files) // 2, len(files) * 3 // 4, len(files) - 1}
    )
    thumb_width = 640
    thumb_height = round(height * thumb_width / width)
    sheet = Image.new(
        "RGB", (thumb_width * len(milestones), thumb_height + 40), (25, 29, 24)
    )
    draw = ImageDraw.Draw(sheet)
    for column, index in enumerate(milestones):
        with Image.open(files[index]) as image:
            sheet.paste(
                image.resize((thumb_width, thumb_height)), (column * thumb_width, 0)
            )
        draw.text(
            (column * thumb_width + 20, thumb_height + 12),
            f"Frame {index + 1}  |  {manifest['frames'][index]['gdd']:.0f} GDD",
            fill=(228, 236, 220),
        )
    sheet.save(destination / "growth_contact_sheet.jpg", quality=92)
    with Image.open(files[-1]) as image:
        image.save(destination / "poster.png")
    report = {
        "movie": str(movie.resolve()),
        "fps": manifest["fps"],
        "frames": count,
        "growth_samples": len(files),
        "duration_seconds": duration,
        "resolution": [width, height],
        "hold_seconds": hold_frames / manifest["fps"],
        "hold_frames": hold_frames,
        "native_geometry": not manifest.get("synthetic_only", False),
        "source": binding,
    }
    (destination / "render_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
