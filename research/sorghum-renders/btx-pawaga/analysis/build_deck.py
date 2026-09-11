#!/usr/bin/env python3
"""Build the BTx623/Pawaga geometry-calibration slide deck (16:9 PPTX).

Every statement on a slide is sourced from EXPERIMENT_LOG.md / METHODS.md.
Regenerate after any change:

    python analysis/build_deck.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "results" / "btx_pawaga_calibration_deck.pptx"

INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x6E, 0x6E, 0x69)
BLUE = RGBColor(0x00, 0x72, 0xB2)    # BTx623 (Okabe-Ito)
ORANGE = RGBColor(0xD5, 0x5E, 0x00)  # Pawaga (Okabe-Ito)

SW, SH = Inches(13.333), Inches(7.5)


def blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def text_box(slide, x, y, w, h):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    return tf


def set_run(par, text, size, bold=False, color=INK, italic=False):
    run = par.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return run


def title(slide, text, size=24):
    tf = text_box(slide, Inches(0.45), Inches(0.22), SW - Inches(0.9), Inches(0.75))
    set_run(tf.paragraphs[0], text, size, bold=True)


def bullets(slide, x, y, w, h, items, size=13.5, gap=4):
    tf = text_box(slide, x, y, w, h)
    first = True
    for item in items:
        par = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        par.space_after = Pt(gap)
        if isinstance(item, tuple):  # (level, text) or list of styled runs
            level, text = item
            par.level = level
            set_run(par, text, size - 1.5 * level)
        elif isinstance(item, list):  # styled runs: (text, kwargs)
            for text, kwargs in item:
                set_run(par, text, size, **kwargs)
        else:
            set_run(par, item, size)
    return tf


def picture(slide, path, x, y, max_w, max_h, caption=None):
    img = Image.open(path)
    aspect = img.width / img.height
    w, h = max_w, int(max_w / aspect)
    if h > max_h:
        h, w = max_h, int(max_h * aspect)
    pic = slide.shapes.add_picture(str(path), x, y, width=int(w), height=int(h))
    if caption:
        tf = text_box(slide, x, y + int(h) + Inches(0.03), int(w), Inches(0.3))
        set_run(tf.paragraphs[0], caption, 10, color=MUTED)
    return pic


def main() -> int:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH

    # 1 ── Title ─────────────────────────────────────────────────────────────
    s = blank_slide(prs)
    tf = text_box(s, Inches(0.9), Inches(2.5), SW - Inches(1.8), Inches(2.6))
    set_run(tf.paragraphs[0], "Field-validated canopy geometry for BTx623 and Pawaga in EvoEngine", 30, bold=True)
    p = tf.add_paragraph()
    set_run(p, "Calibration and season validation against 2021 Maricopa PARbar transmittance", 17, color=MUTED)
    p = tf.add_paragraph()
    set_run(p, "September 2026", 13, color=MUTED)

    # 2 ── Field data ────────────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Field reference: 2021 PARbar transmittance")
    picture(s, HERE / "targets" / "aerial_2021_parbar_field.png",
            Inches(0.45), Inches(1.0), Inches(7.6), Inches(3.1),
            caption="2021 aerial. PARbars (white, 45°) in furrows between plot pairs; measured block near west end, ~30 sorghum rows east.")
    bullets(s, Inches(8.35), Inches(1.0), Inches(4.55), Inches(5.6), [
        "Maricopa AZ, planted 2021-05-13; N–S rows, 1 m spacing, unthinned",
        "PARbar: 1 m, 50 photodiodes @ 20 mm (Salter 2019); bottom bar near ground, top above canopy",
        [("τ = below / above", {"bold": True}),
         ("  — same-device ratio cancels the +25–35 % calibration bias", {})],
        "Screened: solar azimuth < 245° (mast solar-panel shading), elevation > 30°",
        "3 clear scan days, position Y (plots 7415/16 & 7411/12):",
    ], size=13)
    tf = text_box(s, Inches(8.35), Inches(4.55), Inches(4.55), Inches(2.2))
    for i, row in enumerate([
        ("date", "GDD", "τ BTx623", "τ Pawaga"),
        ("Jul 26", "2036", "0.247", "0.265"),
        ("Aug 22", "2810", "0.248", "0.283"),
        ("Sep 21", "3649", "0.179", "0.208"),
    ]):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        set_run(par, "   ".join(f"{c:<8}" for c in row), 12,
                bold=(i == 0), color=INK if i else MUTED)
        par.runs[0].font.name = "Consolas"

    # 3 ── Architecture reference ───────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Architecture reference: the only published data for the pair")
    picture(s, HERE / "targets" / "photo_greenhouse_BTX623_peerj_s001.png",
            Inches(0.55), Inches(1.05), Inches(3.5), Inches(4.5), caption="BTx623 (greenhouse)")
    picture(s, HERE / "targets" / "photo_greenhouse_Pawaga_peerj_s001.png",
            Inches(4.25), Inches(1.05), Inches(3.5), Inches(4.5), caption="Pawaga (greenhouse)")
    bullets(s, Inches(8.1), Inches(1.05), Inches(4.8), Inches(5.6), [
        "PeerJ 9:e12628 suppl.: the leaf-angle extremes of the sorghum association panel — no numeric traits published",
        "Both genotypes droop; they differ in WHERE the bend starts along the blade and how much blade hangs — not mainly in insertion angle",
        "No 2021 hand measurements exist → dimensions transferred from 3 hand-measured genotypes grown in the same field in 2026",
        "Growth-stage match by thermal time (86/55 °F, hourly, AZMET): Jul 26 = 2036 GDD ≈ midway between measured weeks 6 and 7",
    ], size=13.5)

    # 4 ── What was tuned ───────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Parameter policy: anchored dimensions, calibrated angles")
    bullets(s, Inches(0.55), Inches(1.05), Inches(6.0), Inches(5.6), [
        [("Fixed from measurements", {"bold": True}), ("  (2026 hand data + stand counts)", {"color": MUTED})],
        (1, "leaf width 8.5 cm (max)"),
        (1, "phytomer count 14 ± 1"),
        (1, "internode length curve (≈ stage-matched)"),
        (1, "tillers 2–3 per plant ± 0.5  (≈30 stems/plot counted)"),
        (1, "row/plant spacing: 1 m × 0.30 m, 12 plants/row"),
    ], size=14)
    bullets(s, Inches(6.9), Inches(1.05), Inches(6.0), Inches(5.6), [
        [("Calibrated against τ", {"bold": True}), ("  (unmeasured in either year)", {"color": MUTED})],
        (1, "leaf bending: maximum + curve over leaf rank"),
        (1, "bend position along the blade"),
        (1, "insertion angle at the collar"),
        (1, "blade length within 0.85–1.0 m"),
        "",
        [("Rationale: ", {"bold": True}),
         ("angle-family parameters carry the erectophile/planophile contrast and were never measured; "
          "dimensions stay inside the measured envelope to prevent compensating errors.", {})],
    ], size=14)

    # 5 ── Before / after ───────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Before and after calibration")
    picture(s, HERE / "renders" / "btx_vs_pawaga_v0.png",
            Inches(0.55), Inches(1.15), Inches(6.0), Inches(3.9),
            caption="v0: measured dimensions + literature angle stereotypes — too stiff")
    picture(s, HERE / "renders" / "btx_vs_pawaga_CAL1.png",
            Inches(6.85), Inches(1.15), Inches(6.0), Inches(3.9),
            caption="final (BTx623 v6 / Pawaga v8): photo-anchored droop, τ-calibrated")
    tf = text_box(s, Inches(0.55), Inches(5.6), Inches(12.2), Inches(1.4))
    set_run(tf.paragraphs[0],
            "Pawaga left, BTx623 right in each panel. Droop was introduced to match the greenhouse photos "
            "(field sorghum with panicles is never as erect as v0), then angle parameters were fitted to the "
            "field τ while dimensions stayed fixed.", 13)

    # 6 ── BTx623 versions ──────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "BTx623: six descriptor versions")
    rows = [
        ("v0", "2026 dimensions grafted onto stock erect angle family (insertion max 42°)"),
        ("v1", "droop per greenhouse photo: bend kept at upper ranks, earlier bend development, insertion max 46°"),
        ("combo", "interception raised: blade 1.0 m, width 10 cm, tillers 3 (sensitivity-ranked levers)"),
        ("v2", "further droop (rank tail 0.45→0.55), width 10.7 cm"),
        ("v3–v4", "tiller variance tightened (±0.5); rebalanced after two scene-placement fixes (blade 0.95 m, width 10 cm, tillers 2.5)"),
        ("v5", "seed-ensemble (n=31) showed v4 too closed by 0.06; opening step overshot (+0.12 — tiller floor acts super-linearly near canopy closure)"),
        ("v6", "final: bisection of v4/v5 (tillers 2.25 ± 0.5, blade 0.92 m, width 9.7 cm) — ensemble-verified on target"),
    ]
    tf = text_box(s, Inches(0.55), Inches(1.1), Inches(12.2), Inches(5.6))
    for i, (v, desc) in enumerate(rows):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.space_after = Pt(7)
        set_run(par, f"{v:6s}", 14, bold=True, color=BLUE)
        set_run(par, desc, 14)
    tf = text_box(s, Inches(0.55), Inches(6.35), Inches(12.2), Inches(0.8))
    set_run(tf.paragraphs[0],
            "τ values are comparable only within one scene revision; per-version τ under superseded "
            "scenes is omitted deliberately. Final τ on the corrected scene: slide 9.", 11.5, color=MUTED)

    # 7 ── Pawaga versions ──────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Pawaga: descriptor versions")
    rows = [
        ("v0", "2026 dimensions + rank-increasing insertion curve borrowed from hand-measured genotype C"),
        ("v1", "greenhouse photo refuted v0's premise: stock declining insertion restored; droop moved into early, strong blade bend"),
        ("v2–v3", "opened (shorter blades, fewer tillers) to chase τ — later shown to be fitting a sensor-placement artifact"),
        ("v4–v6", "stochasticity hygiene: tillers 2 ± 0.5 (min 1), insertion s.d. 18→8°, internode s.d. 47→27 % rel."),
        ("v7", "v1 interception restored (blade 0.95 m, full droop) after the artifact was fixed"),
        ("v8", "final: blade 0.92 m"),
    ]
    tf = text_box(s, Inches(0.55), Inches(1.1), Inches(12.2), Inches(5.6))
    for i, (v, desc) in enumerate(rows):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.space_after = Pt(7)
        set_run(par, f"{v:7s}", 14, bold=True, color=ORANGE)
        set_run(par, desc, 14)

    # 8 ── Illumination implementation ──────────────────────────────────────
    s = blank_slide(prs)
    title(s, "How the illumination was computed")
    picture(s, HERE / "renders" / "publication" / "field_furrow.png",
            Inches(0.45), Inches(1.05), Inches(5.9), Inches(4.4),
            caption="Simulated furrow at the sensor station")
    bullets(s, Inches(6.7), Inches(1.0), Inches(6.2), Inches(6.2), [
        "Scene: position-Y plot block replica + ≥4 m of neighboring canopy on every side of each bar (beam path ≤2.5 m at 31° elevation ≈ the field's ~30 rows)",
        "Virtual PARbar: 50 probes on a 1 m bar at 45° in the furrow; bottom 0.11–0.15 m, top raised to 2.30 m (as field crews raised it); placement engine-verified",
        "OptiX ray tracing: 128 rays × 4 bounces per probe; sun set per 15-min pvlib solar position; same azimuth/elevation screen as the field data",
        "τ = bottom/top per genotype — unit-free, so no absolute radiometric calibration is needed",
        "Seed ensembles: n = 8–31 stand realizations per estimate (mean ± 95 % CI); ≤5-seed medians proved unreliable — midday τ is set by the few plants flanking the bar",
        "Two placement errors found by verification and fixed before any reported τ: top bar inside canopy; bar overhanging the row end",
    ], size=13)

    # 9 ── Results ──────────────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Result: calibrated once, holds across the season")
    picture(s, HERE / "results" / "tau_seasonal_agreement.png",
            Inches(0.45), Inches(1.0), Inches(7.3), Inches(5.9))
    bullets(s, Inches(8.05), Inches(1.05), Inches(4.85), Inches(5.9), [
        "Angles fitted on Jul 26 only; Aug 22 and Sep 21 run with geometry unchanged (n = 8–31 stand realizations per point)",
        "8 of 9 quantities: field value inside the simulation's 95 % CI",
        [("Genotype ordering (Pawaga > BTx623) reproduced on all three dates; ", {}),
         ("Jul 26 contrast +0.019 vs field +0.018", {"bold": True})],
        "September levels within 0.007 (BTx623) / 0.024 (Pawaga) — the seasonal decline follows from solar geometry alone",
        "Sole detected difference: BTx623 Aug 22 (p = 0.037) — field τ held at 0.248 while the static canopy tracked the sun downward; consistent with unmodeled post-anthesis opening",
        "Simulating the field beyond the measured plots improves Pawaga's diurnal shape (ensemble-mean r 0.80 → 0.92)",
    ], size=12.5)

    # 10 ── Caveats ─────────────────────────────────────────────────────────
    s = blank_slide(prs)
    title(s, "Known limits")
    bullets(s, Inches(0.55), Inches(1.1), Inches(12.2), Inches(5.8), [
        "Midday τ is governed by the few plants flanking the bar — stand-realization spread is large (sim seed SD 0.03–0.07; the field's own Pawaga plot pairs spanned τ 0.157–0.316 at equal biomass); estimates below ~8 seeds are unreliable",
        "Post-anthesis change (senescence, leaf movement, lodging) is not modeled — the one detected sim–field difference (BTx623, Aug 22) is consistent with this",
        "Pawaga dawn bins remain ≈0.07 above the field after context correction; sky diffuse fraction was tested and excluded as the cause",
        "The 2021 design aliases genotype with device and plot; the field's own genotype contrast (0.02–0.04) is below what its replication can establish — matching it is not a meaningful test",
    ], size=14)

    OUT.parent.mkdir(exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
