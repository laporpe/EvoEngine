"""Annotate the block renders with per-row genotype brackets.

    python label_block_renders.py [blender-export/btx_block_small]

Reads <stem>_rows.json, written by blender_build_block.py: for each camera, the
normalised screen position of every row's base. Brackets are drawn at those
projected positions, so the BTx623 / Pawaga boundary lands exactly between the
rows it separates instead of being implied by a floating label.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FLAG = {"BTX": (26, 92, 217), "Pawaga": (217, 77, 20)}      # matches the stake tape
INK = (245, 242, 236)
LABEL = {"BTX": "BTx623", "Pawaga": "Pawaga"}


def font(px):
    for n in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            pass
    return ImageFont.load_default()


def caption(im, text, px):
    f = font(px)
    strip = px * 2
    out = Image.new("RGB", (im.width, im.height + strip), (255, 255, 255))
    out.paste(im, (0, strip))
    d = ImageDraw.Draw(out)
    d.text(((im.width - d.textlength(text, font=f)) / 2, strip * 0.28), text, font=f, fill=(20, 20, 20))
    return out


def groups(rows):
    """Contiguous runs of the same genotype, in row order."""
    out = []
    for i in sorted(rows, key=int):
        g = rows[i]["genotype"]
        if out and out[-1][0] == g:
            out[-1][1].append(i)
        else:
            out.append([g, [i]])
    return out


def bracket_cross_section(im, rows):
    """Brackets along the ground line under the row bases (screen x from u)."""
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    px = H // 22
    f = font(px)
    xs = {i: rows[i]["u_near"] * W for i in rows}
    # Row pitch on screen, for half-gaps at the bracket ends and the split.
    order = sorted(rows, key=lambda i: xs[i])
    pitch = (xs[order[-1]] - xs[order[0]]) / max(1, len(order) - 1)
    y_line = H * 0.905
    for g, members in groups(rows):
        x0 = min(xs[i] for i in members) - pitch * 0.5
        x1 = max(xs[i] for i in members) + pitch * 0.5
        colour = FLAG[g]
        d.line((x0, y_line, x1, y_line), fill=colour, width=max(3, px // 8))
        for x in (x0, x1):
            d.line((x, y_line - px * 0.45, x, y_line), fill=colour, width=max(3, px // 8))
        for i in members:                                  # tick per row
            d.line((xs[i], y_line - px * 0.25, xs[i], y_line), fill=colour, width=max(2, px // 12))
        text = f"{LABEL[g]}  ({len(members)} rows)"
        tw = d.textlength(text, font=f)
        cx = (x0 + x1) / 2
        d.rounded_rectangle((cx - tw / 2 - px / 3, y_line + px * 0.35, cx + tw / 2 + px / 3,
                             y_line + px * 1.65), radius=px // 3, fill=(40, 26, 18, 235))
        d.text((cx - tw / 2, y_line + px * 0.5), text, font=f, fill=INK)
    return im


def bracket_top_down(im, rows):
    """Brackets down the left margin beside the rows (screen y from v)."""
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    px = W // 26
    f = font(px)
    ys = {i: (1.0 - rows[i]["v"]) * H for i in rows}
    order = sorted(rows, key=lambda i: ys[i])
    pitch = (ys[order[-1]] - ys[order[0]]) / max(1, len(order) - 1)
    x_line = W * 0.125
    for g, members in groups(rows):
        y0 = min(ys[i] for i in members) - pitch * 0.5
        y1 = max(ys[i] for i in members) + pitch * 0.5
        colour = FLAG[g]
        d.line((x_line, y0, x_line, y1), fill=colour, width=max(3, px // 8))
        for y in (y0, y1):
            d.line((x_line, y, x_line + px * 0.45, y), fill=colour, width=max(3, px // 8))
        for i in members:
            d.line((x_line, ys[i], x_line + px * 0.25, ys[i]), fill=colour, width=max(2, px // 12))
        text = LABEL[g]
        tw = d.textlength(text, font=f)
        cy = (y0 + y1) / 2
        # Label rotated to run along the bracket.
        tag = Image.new("RGBA", (int(tw + px * 0.7), int(px * 1.35)), (40, 26, 18, 235))
        ImageDraw.Draw(tag).text((px * 0.35, px * 0.12), text, font=f, fill=INK)
        tag = tag.rotate(90, expand=True)
        # Keep the rotated label inside the frame whatever the margin allows.
        px_x = max(6, int(x_line - px * 0.55 - tag.width))
        im.paste(tag, (px_x, int(cy - tag.height / 2)), tag)
    return im


def main() -> None:
    stem = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("blender-export/btx_block_small")
    rows = json.loads(stem.with_name(stem.name + "_rows.json").read_text())

    b = Image.open(stem.with_name("btx_block_b_crosssection.png")).convert("RGB")
    b = bracket_cross_section(b, rows["CamCrossSection"])
    caption(b, "(b) row cross-section", b.height // 24).save(
        stem.with_name("btx_block_b_crosssection_labelled.png"))

    a = Image.open(stem.with_name("btx_block_a_topdown.png")).convert("RGB")
    a = bracket_top_down(a, rows["CamTopDown"])
    caption(a, "(a) top-down", a.width // 30).save(stem.with_name("btx_block_a_topdown_labelled.png"))
    print("labelled (a) and (b) with per-row brackets")


main()
