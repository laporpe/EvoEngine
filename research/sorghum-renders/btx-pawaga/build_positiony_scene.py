#!/usr/bin/env python3
"""Build the position-Y PARBAR scene by editing transforms in a scene copy.

Two passes, both engine-verified with verify_positiony_scene.py:

Pass 1 (default): copy Sorghum_4x10_PARBAR.evescene -> Sorghum_PositionY_PARBAR45.evescene,
translate each rig root to its furrow line and shrink it (1.78 m scene bar -> 1.0 m physical
PARbar). No rotation at the root: the mast line must stay along +X (the furrow direction,
per the field SOP), only the bars themselves get yawed in pass 2.

Pass 2 (--pass2 measured.json): rotate each *SensorBarMesh child about its own measured bar
center so its axis lands exactly 45 deg from +X (east end north). Input JSON maps
"<cultivar>:<level>" -> {"center": [x,y,z], "axis_deg": <measured>} from the verify script.

World convention: +X = north (row direction), +Z = east. Rows at z = 0..6, 1 m apart
(BTX plots 7410-7413 -> z 0..3, Pawaga 7414-7416 -> z 4..6).

    python build_positiony_scene.py            # pass 1
    python build_positiony_scene.py --pass2 measured.json
"""

from __future__ import annotations

import os
import argparse
import base64
import json
import math
import random
import re
import struct
from pathlib import Path

import numpy as np

SCENES = (Path(os.environ.get("EVOENGINE_ROOT", r"C:\Users\Brenda\code\EvoEngine")) / r"Resources\DigitalAgricultureProject\Assets\ManualAssets\Scenes")
SOURCE = SCENES / "Sorghum_4x10_PARBAR.evescene"
TARGET = SCENES / "Sorghum_PositionY_PARBAR45.evescene"

RIG_ROOTS = {
    "BTX": 18412299652664880487,
    "Pawaga": 1273479135909045154,
}

# *SensorBarMesh entity handles, keyed "<cultivar>:<level>" (from entity_metadata_list).
BAR_MESHES: dict[str, int] = {}  # filled by scan_bar_mesh_handles()

BAR_SHRINK = 1.0 / 1.78
TARGET_AXIS_DEG = 45.0

TARGET_XZ = {
    "BTX": (0.0, 1.5),     # furrow between plot rows z=1 (7411) and z=2 (7412)
    "Pawaga": (0.0, 5.5),  # furrow between plot rows z=5 (7415) and z=6 (7416)
}


def decode(b64: str) -> np.ndarray:
    return np.array(struct.unpack("<16f", base64.b64decode(b64)), dtype=np.float64).reshape(4, 4).T


def encode(m: np.ndarray) -> str:
    return base64.b64encode(struct.pack("<16f", *m.T.flatten().tolist())).decode()


def ry(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    # +yaw rotates +Z toward +X (matches glm rotation about +Y)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], dtype=np.float64)


def translation(v) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = v
    return m


def entry_pattern(handle: int) -> re.Pattern:
    return re.compile(
        rf'(- h: {handle}\s*\n\s*dc:\s*\n\s*- d: !!binary ")([A-Za-z0-9+/=]+)("\s*\n\s*- d: !!binary ")([A-Za-z0-9+/=]+)(")'
    )


def read_matrix(text: str, handle: int) -> np.ndarray:
    m = entry_pattern(handle).search(text)
    assert m, f"chunk entry {handle} not found"
    return decode(m.group(2))


def write_matrix(text: str, handle: int, matrix: np.ndarray) -> str:
    m = entry_pattern(handle).search(text)
    assert m, f"chunk entry {handle} not found"
    blob = encode(matrix)
    return text[: m.start()] + m.group(1) + blob + m.group(3) + blob + m.group(5) + text[m.end():]


def scan_bar_mesh_handles(text: str) -> None:
    """Map <cultivar>:<level> -> entity handle from entity_metadata_list."""
    for m in re.finditer(r"- n: PARBAR_(BTX|Pawaga)_(Top|Middle|Bottom)SensorBarMesh\s*\n\s*h: (\d+)", text):
        BAR_MESHES[f"{m.group(1)}:{m.group(2).lower()}"] = int(m.group(3))
    assert len(BAR_MESHES) == 6, f"expected 6 bar meshes, found {BAR_MESHES}"


def pass1() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    for name, handle in RIG_ROOTS.items():
        old = read_matrix(text, handle)
        new = old.copy()
        new[:3, :3] *= BAR_SHRINK
        new[0, 3], new[2, 3] = TARGET_XZ[name]  # keep original y
        text = write_matrix(text, handle, new)
        print(f"{name}: root -> ({new[0, 3]}, {round(new[1, 3], 3)}, {new[2, 3]}), scale x{BAR_SHRINK:.4f}, no yaw")

    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    write_sidecar()
    print(f"pass 1 wrote {TARGET.name}")


def pass2(measured_path: Path) -> None:
    measured = json.loads(measured_path.read_text(encoding="utf-8"))
    text = TARGET.read_text(encoding="utf-8")
    scan_bar_mesh_handles(text)
    for key, info in measured.items():
        cultivar = key.split(":")[0]
        handle = BAR_MESHES[key]
        parent_global = read_matrix(text, RIG_ROOTS[cultivar])  # intermediates are identity
        child_local = read_matrix(text, handle)
        delta = TARGET_AXIS_DEG - float(info["axis_deg"])
        # normalize to the nearest equivalent line orientation (axis sign is arbitrary)
        while delta > 90:
            delta -= 180
        while delta < -90:
            delta += 180
        center = np.array(info["center"], dtype=np.float64)
        p_inv = np.linalg.inv(parent_global)
        # ry(theta) rotates the in-plane atan2(dz,dx) angle by -theta, so negate
        new_local = p_inv @ translation(center) @ ry(-delta) @ translation(-center) @ parent_global @ child_local
        text = write_matrix(text, handle, new_local)
        print(f"{key}: axis {info['axis_deg']:+.1f} -> target {TARGET_AXIS_DEG} (delta {delta:+.1f} deg) "
              f"about ({center[0]:.3f},{center[1]:.3f},{center[2]:.3f})")
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"pass 2 rewrote {TARGET.name}")


def write_sidecar() -> None:
    sidecar_dst = Path(f"{TARGET}.evefilemeta")
    if sidecar_dst.exists():  # keep the existing handle across rebuilds
        return
    meta = Path(f"{SOURCE}.evefilemeta").read_text(encoding="utf-8")
    new_handle = random.getrandbits(63) | 1
    assets_root = SCENES.parents[1]
    hits = [p for p in assets_root.rglob("*.evefilemeta") if str(new_handle) in p.read_text(encoding="utf-8")]
    assert not hits, f"handle collision: {new_handle}"
    meta = re.sub(r"asset_file_name_:.*", f"asset_file_name_: {TARGET.stem}", meta)
    meta = re.sub(r"asset_handle_:.*", f"asset_handle_: {new_handle}", meta)
    with open(sidecar_dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(meta)
    print(f"sidecar written (handle {new_handle})")


def pass3(measured_path: Path, target_top_y: float) -> None:
    """Raise the two *Top* bars so the above-canopy reference clears the canopy."""
    measured = json.loads(measured_path.read_text(encoding="utf-8"))
    text = TARGET.read_text(encoding="utf-8")
    scan_bar_mesh_handles(text)
    for key in ("BTX:top", "Pawaga:top"):
        cultivar = key.split(":")[0]
        handle = BAR_MESHES[key]
        parent_global = read_matrix(text, RIG_ROOTS[cultivar])
        child_local = read_matrix(text, handle)
        dy = target_top_y - float(measured[key]["center"][1])
        p_inv = np.linalg.inv(parent_global)
        new_local = p_inv @ translation((0.0, dy, 0.0)) @ parent_global @ child_local
        text = write_matrix(text, handle, new_local)
        print(f"{key}: raised {dy:+.3f} m to y={target_top_y}")
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"pass 3 rewrote {TARGET.name}")


def pass4(measured_path: Path) -> None:
    """Slide each rig along the row (x) so its mast line centers at mid-row (x=0).

    The bars must sit fully within the planted area (SOP); the rig-internal mast
    offsets otherwise leave the bottom bars at the row end over bare ground.
    """
    measured = json.loads(measured_path.read_text(encoding="utf-8"))
    text = TARGET.read_text(encoding="utf-8")
    for cultivar, handle in RIG_ROOTS.items():
        xs = [float(measured[f"{cultivar}:{lvl}"]["center"][0]) for lvl in ("top", "bottom")]
        dx = -(xs[0] + xs[1]) / 2.0
        root = read_matrix(text, handle)
        root[0, 3] += dx
        text = write_matrix(text, handle, root)
        print(f"{cultivar}: shifted x {dx:+.3f} (bars were at x {xs[1]:+.2f}/{xs[0]:+.2f})")
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"pass 4 rewrote {TARGET.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass2", type=Path, default=None,
                        help="JSON of measured bar centers/axes from verify_positiony_scene.py")
    parser.add_argument("--pass3", type=Path, default=None,
                        help="raise top bars: JSON of measured bar centers from the verify script")
    parser.add_argument("--pass4", type=Path, default=None,
                        help="center mast lines at mid-row: JSON of measured bar centers")
    parser.add_argument("--top-y", type=float, default=2.3,
                        help="target world height for top bars (m)")
    args = parser.parse_args()
    if args.pass4 is not None:
        pass4(args.pass4)
    elif args.pass3 is not None:
        pass3(args.pass3, args.top_y)
    elif args.pass2 is not None:
        pass2(args.pass2)
    else:
        pass1()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
