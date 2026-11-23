#!/usr/bin/env python3
"""Build the logo font from the logo's section SVGs.

Each `brand/orbita-mark-section-NN.svg` becomes one glyph, at codepoint
U+E000 + (NN - 1) (Unicode private use area). Every section is drawn on the
same canvas, and every glyph keeps that canvas as its advance width and line
height, so labels drawing the glyphs at the same position show the assembled
logo. Each glyph can then be moved, faded or recolored on its own.

Font units: the canvas height is the em, so at font size N px the logo is
N px tall.

The output is deterministic: running the tool again on unchanged SVGs gives a
byte-identical file, so `--check` can verify the committed font is current.

Run inside the dev container:

    docker compose run --rm --entrypoint python esphome tools/build_logo_font.py
    docker compose run --rm --entrypoint python esphome tools/build_logo_font.py --check
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib import SVGPath

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
SECTION_GLOB = "orbita-mark-section-*.svg"
OUTPUT = ROOT / "fonts" / "orbita-mark.ttf"

FAMILY = "Orbita Mark"
UNITS_PER_EM = 1000
FIRST_CODEPOINT = 0xE000
# Max distance (font units) between the source curves and their quadratic
# approximation. 1 unit = 1/1000 of the logo height: invisible at any size.
CURVE_TOLERANCE = 1.0
# Fixed timestamps keep the output byte-identical between runs.
FIXED_TIMESTAMP = 0


def canvas_size(svg_file: Path) -> tuple[float, float]:
    root = ET.parse(svg_file).getroot()
    view_box = root.get("viewBox")
    if not view_box:
        raise ValueError(f"{svg_file.name}: missing viewBox")
    _, _, width, height = (float(v) for v in re.split(r"[\s,]+", view_box.strip()))
    return width, height


def section_files() -> list[Path]:
    files = sorted(BRAND.glob(SECTION_GLOB))
    if not files:
        raise ValueError(f"no {SECTION_GLOB} in {BRAND}")
    expected = [f"orbita-mark-section-{i:02d}.svg" for i in range(1, len(files) + 1)]
    if [f.name for f in files] != expected:
        raise ValueError(f"sections must be numbered 01..{len(files):02d} with no gaps")
    return files


def close_contours(ops: list, name: str) -> list:
    """Turn contours that end where they start into closed contours.

    The SVG parser ends shapes such as <ellipse> with `endPath` (open) even
    though the outline returns to its start point. Glyph outlines must be
    closed to be filled, so close those and reject really open ones.
    """
    result = []
    start = last = None
    for op, args in ops:
        if op == "moveTo":
            start = last = args[0]
        elif op in ("lineTo", "curveTo", "qCurveTo"):
            last = args[-1]
        elif op == "endPath":
            if abs(last[0] - start[0]) > 1e-3 or abs(last[1] - start[1]) > 1e-3:
                raise ValueError(f"{name}: open path (only filled shapes are supported)")
            op = "closePath"
        result.append((op, args))
    return result


def draw_section(svg_file: Path, scale: float, height: float):
    """Return the TrueType glyph for one section."""
    # SVG is y-down from the top of the canvas; fonts are y-up from the
    # baseline. Put the canvas bottom on the baseline and its top at the em.
    transform = (scale, 0, 0, -scale, 0, height * scale)
    recording = RecordingPen()
    SVGPath(str(svg_file), transform=transform).draw(recording)
    if not recording.value:
        raise ValueError(f"{svg_file.name}: no shapes")
    recording.value = close_contours(recording.value, svg_file.name)

    # TrueType wants outer contours clockwise (negative area for AreaPen).
    area = AreaPen()
    recording.replay(area)
    tt_pen = TTGlyphPen(None)
    target = ReverseContourPen(tt_pen) if area.value > 0 else tt_pen
    # glyf outlines are quadratic; the SVG shapes come out cubic.
    recording.replay(Cu2QuPen(target, CURVE_TOLERANCE, reverse_direction=False))
    return tt_pen.glyph()


def build() -> bytes:
    files = section_files()
    width, height = canvas_size(files[0])
    for f in files[1:]:
        if canvas_size(f) != (width, height):
            raise ValueError(f"{f.name}: viewBox differs from {files[0].name}")

    scale = UNITS_PER_EM / height
    advance = round(width * scale)

    glyph_names = [".notdef"] + [f"section{i:02d}" for i in range(1, len(files) + 1)]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    cmap = {}
    for i, svg_file in enumerate(files):
        name = glyph_names[i + 1]
        glyphs[name] = draw_section(svg_file, scale, height)
        cmap[FIRST_CODEPOINT + i] = name

    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    metrics = {}
    glyf = fb.font["glyf"]
    for name in glyph_names:
        glyph = glyf[name]
        glyph.recalcBounds(glyf)
        lsb = getattr(glyph, "xMin", 0)
        metrics[name] = (advance if name != ".notdef" else 0, lsb)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=UNITS_PER_EM, descent=0)
    fb.setupNameTable({"familyName": FAMILY, "styleName": "Regular"})
    fb.setupOS2(
        sTypoAscender=UNITS_PER_EM,
        sTypoDescender=0,
        sTypoLineGap=0,
        usWinAscent=UNITS_PER_EM,
        usWinDescent=0,
    )
    fb.setupPost()
    fb.updateHead(created=FIXED_TIMESTAMP, modified=FIXED_TIMESTAMP)

    out = io.BytesIO()
    # recalcTimestamp=False keeps the fixed `modified` time on save.
    fb.font.recalcTimestamp = False
    fb.font.save(out)
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed font differs from a fresh build",
    )
    args = parser.parse_args()

    try:
        data = build()
    except ValueError as err:
        print(f"error: {err}")
        return 1

    rel = OUTPUT.relative_to(ROOT).as_posix()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != data:
            print(f"{rel} is out of date: run tools/build_logo_font.py")
            return 1
        print(f"{rel} is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    count = len(section_files())
    print(f"wrote {rel}: {count} glyphs, U+{FIRST_CODEPOINT:04X}..U+{FIRST_CODEPOINT + count - 1:04X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
