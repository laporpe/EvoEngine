"""Score a render against the field photographs.

    python measure_render.py <render.png>

Reports the numbers that separated the flat first attempt from the photos:
sky colour and blue/red ratio at the top of frame, darkest-percentile level,
and p99/p1 dynamic range. Targets come from IMG_4137, IMG_4163 and IMG_4171.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TARGET = {
    "sky top RGB": "(108-118, 146-152, 212-214)",
    "sky blue/red": "1.8 - 2.0",
    "p1 (darkest 1 %)": "6 - 15",
    "p99/p1 range": "16x - 38x",
}


def box(a, fx0, fy0, fx1, fy1):
    h, w = a.shape[:2]
    r = a[int(h * fy0):int(h * fy1), int(w * fx0):int(w * fx1)]
    return r.reshape(-1, 3).mean(0)


def main() -> None:
    path = Path(sys.argv[1])
    a = np.asarray(Image.open(path).convert("RGB")).astype(float)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    sky = box(a, 0.30, 0.02, 0.70, 0.10)
    p1, p50, p99 = (np.percentile(lum, q) for q in (1, 50, 99))
    rows = [
        ("sky top RGB", f"({sky[0]:.0f}, {sky[1]:.0f}, {sky[2]:.0f})"),
        ("sky blue/red", f"{sky[2] / max(sky[0], 1):.2f}"),
        ("p1 (darkest 1 %)", f"{p1:.0f}"),
        ("p50 (median)", f"{p50:.0f}"),
        ("p99/p1 range", f"{p99 / max(p1, 1):.0f}x"),
    ]
    print(f"{path.name}")
    print(f"  {'metric':20s} {'render':>22s}   target")
    for name, value in rows:
        print(f"  {name:20s} {value:>22s}   {TARGET.get(name, '')}")


main()
