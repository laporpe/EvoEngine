"""Fetch verified CC0 Poly Haven soil maps used by the Blender review pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


ASSETS = ("dirt", "brown_mud_dry")
CHANNELS = {
    "Diffuse": "jpg",
    "nor_gl": "png",
    "Displacement": "exr",
    "Rough": "exr",
    "Bump": "exr",
    "Spec": "exr",
    "blend": "blend",
}
API = "https://api.polyhaven.com"
LICENSE_URL = "https://polyhaven.com/license"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolution", default="4k")
    return parser.parse_args()


def fetch_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "SorghumDigitalTwin/1.0"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, expected_md5: str) -> None:
    if target.is_file() and md5(target) == expected_md5:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "SorghumDigitalTwin/1.0"})
    with urllib.request.urlopen(request) as response, temporary.open("wb") as stream:
        while block := response.read(1024 * 1024):
            stream.write(block)
    actual = md5(temporary)
    if actual != expected_md5:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"MD5 mismatch for {url}: expected {expected_md5}, got {actual}")
    temporary.replace(target)


def main() -> None:
    args = parse_args()
    root = args.output.resolve()
    records = []
    for asset_id in ASSETS:
        files = fetch_json(f"{API}/files/{asset_id}")
        info = fetch_json(f"{API}/info/{asset_id}")
        asset_dir = root / asset_id
        channels = {}
        for channel, extension in CHANNELS.items():
            variants = files.get(channel)
            if not isinstance(variants, dict):
                continue
            resolution = variants.get(args.resolution)
            if not isinstance(resolution, dict) or extension not in resolution:
                continue
            source = resolution[extension]
            suffix = Path(source["url"]).suffix
            target = asset_dir / f"{asset_id}_{channel.lower()}{suffix}"
            download(source["url"], target, source["md5"])
            channels[channel] = {
                "path": str(target),
                "url": source["url"],
                "md5": source["md5"],
                "bytes": source["size"],
            }
        record = {
            "asset_id": asset_id,
            "name": info["name"],
            "description": info["description"],
            "authors": info["authors"],
            "physical_dimensions_mm": info["dimensions"],
            "maximum_resolution": info["max_resolution"],
            "requested_resolution": args.resolution,
            "files_hash": info["files_hash"],
            "asset_url": f"https://polyhaven.com/a/{asset_id}",
            "license": "CC0",
            "license_url": LICENSE_URL,
            "channels": channels,
        }
        (asset_dir / "provenance.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        records.append(record)
    manifest = {
        "schema_version": 1,
        "source": "Poly Haven",
        "license": "CC0",
        "license_url": LICENSE_URL,
        "resolution": args.resolution,
        "assets": records,
    }
    (root / "polyhaven_soil_assets.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(root / "polyhaven_soil_assets.json")


if __name__ == "__main__":
    main()
