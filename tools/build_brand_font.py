#!/usr/bin/env python3
"""Build the brand font (fonts/orbita-brand.ttf) from the SVGs in brand/.

It also writes fonts/orbita-brand.yaml, an ESPHome package with one
substitution per glyph (`brand_mark_<N>` for the logo sections,
`brand_<name>` for the others) plus the glyph lists the fonts need
(`brand_mark_glyphs`, `brand_other_glyphs`). Faces use those names, never the
characters themselves.

Two kinds of glyphs, all in the Unicode private use area:

- Logo sections, U+E000 + (NN - 1): each `brand/orbita-mark-section-NN.svg`.
  All sections are drawn on the same canvas, and every section glyph keeps
  that canvas as its advance width and line height, so labels drawing the
  glyphs at the same position show the assembled logo. Each section can then
  be moved, faded or recolored on its own.
- Other brand glyphs, from U+E010 (see OTHER_GLYPHS): one SVG each, each on
  its own canvas.

Font units: a glyph's canvas height is the em, so at font size N px every
glyph is N px tall (ascent = em, no descent).

Only filled shapes are supported: a font fills every outline, so unfilled or
stroked shapes are rejected instead of turning into solid blobs.

The output is deterministic: running the tool again on unchanged SVGs gives a
byte-identical file, so `--check` can verify the committed font is current.

Run inside the dev container:

    docker compose run --rm --entrypoint python esphome tools/build_brand_font.py
    docker compose run --rm --entrypoint python esphome tools/build_brand_font.py --check
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib import SVGPath

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
SECTION_GLOB = "orbita-mark-section-*.svg"
OUTPUT = ROOT / "fonts" / "orbita-brand.ttf"
PACKAGE = ROOT / "fonts" / "orbita-brand.yaml"

FAMILY = "Orbita Brand"
UNITS_PER_EM = 1000
FIRST_SECTION = 0xE000
MAX_SECTIONS = 16
# Other brand glyphs: (glyph name, codepoint, SVG file in brand/).
OTHER_GLYPHS = [
    ("fabrizz", 0xE010, "fabrizz-icon.svg"),
]
# Max distance (font units) between the source curves and their quadratic
# approximation. 1 unit = 1/1000 of the glyph height: invisible at any size.
CURVE_TOLERANCE = 1.0
# Fixed timestamps keep the output byte-identical between runs.
FIXED_TIMESTAMP = 0

SVG_NS = "{http://www.w3.org/2000/svg}"
SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}


@dataclass
class GlyphSpec:
    name: str
    codepoint: int
    svg: Path
    width: float
    height: float


def canvas_size(svg_file: Path) -> tuple[float, float]:
    root = ET.parse(svg_file).getroot()
    view_box = root.get("viewBox")
    if not view_box:
        raise ValueError(f"{svg_file.name}: missing viewBox")
    _, _, width, height = (float(v) for v in re.split(r"[\s,]+", view_box.strip()))
    return width, height


def check_filled(svg_file: Path) -> None:
    """Reject shapes a font can't reproduce: unfilled or stroked ones."""

    def walk(element, fill: str | None) -> None:
        fill = element.get("fill", fill)
        tag = element.tag.removeprefix(SVG_NS)
        if element.get("style"):
            raise ValueError(f"{svg_file.name}: <{tag}> uses style=, use fill= attributes")
        stroke = element.get("stroke")
        if stroke and stroke != "none":
            raise ValueError(f"{svg_file.name}: <{tag}> has a stroke; outline it as a filled shape")
        if tag in SHAPES and fill == "none":
            raise ValueError(f"{svg_file.name}: <{tag}> is not filled")
        for child in element:
            walk(child, fill)

    walk(ET.parse(svg_file).getroot(), None)


def section_specs() -> list[GlyphSpec]:
    files = sorted(BRAND.glob(SECTION_GLOB))
    if not files:
        raise ValueError(f"no {SECTION_GLOB} in {BRAND}")
    if len(files) > MAX_SECTIONS:
        raise ValueError(f"at most {MAX_SECTIONS} logo sections")
    expected = [f"orbita-mark-section-{i:02d}.svg" for i in range(1, len(files) + 1)]
    if [f.name for f in files] != expected:
        raise ValueError(f"sections must be numbered 01..{len(files):02d} with no gaps")
    width, height = canvas_size(files[0])
    for f in files[1:]:
        if canvas_size(f) != (width, height):
            raise ValueError(f"{f.name}: viewBox differs from {files[0].name}")
    return [
        GlyphSpec(f"section{i:02d}", FIRST_SECTION + i - 1, f, width, height)
        for i, f in enumerate(files, 1)
    ]


def other_specs() -> list[GlyphSpec]:
    specs = []
    for name, codepoint, file_name in OTHER_GLYPHS:
        svg = BRAND / file_name
        if not svg.exists():
            raise ValueError(f"missing {svg.relative_to(ROOT).as_posix()}")
        specs.append(GlyphSpec(name, codepoint, svg, *canvas_size(svg)))
    return specs


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


def draw_glyph(spec: GlyphSpec):
    """Return the TrueType glyph for one SVG, its canvas scaled to the em."""
    check_filled(spec.svg)
    scale = UNITS_PER_EM / spec.height
    # SVG is y-down from the top of the canvas; fonts are y-up from the
    # baseline. Put the canvas bottom on the baseline and its top at the em.
    transform = (scale, 0, 0, -scale, 0, spec.height * scale)
    recording = RecordingPen()
    SVGPath(str(spec.svg), transform=transform).draw(recording)
    if not recording.value:
        raise ValueError(f"{spec.svg.name}: no shapes")
    recording.value = close_contours(recording.value, spec.svg.name)

    # TrueType wants outer contours clockwise (negative area for AreaPen).
    area = AreaPen()
    recording.replay(area)
    tt_pen = TTGlyphPen(None)
    target = ReverseContourPen(tt_pen) if area.value > 0 else tt_pen
    # glyf outlines are quadratic; the SVG shapes come out cubic.
    recording.replay(Cu2QuPen(target, CURVE_TOLERANCE, reverse_direction=False))
    return tt_pen.glyph()


def build() -> tuple[bytes, list[GlyphSpec]]:
    specs = section_specs() + other_specs()
    codepoints = [s.codepoint for s in specs]
    if len(set(codepoints)) != len(codepoints):
        raise ValueError("two glyphs share a codepoint")

    glyph_names = [".notdef"] + [s.name for s in specs]
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    advances = {".notdef": 0}
    cmap = {}
    for spec in specs:
        glyphs[spec.name] = draw_glyph(spec)
        advances[spec.name] = round(spec.width * UNITS_PER_EM / spec.height)
        cmap[spec.codepoint] = spec.name

    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    metrics = {}
    glyf = fb.font["glyf"]
    for name in glyph_names:
        glyph = glyf[name]
        glyph.recalcBounds(glyf)
        metrics[name] = (advances[name], getattr(glyph, "xMin", 0))
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
    return out.getvalue(), specs


def escape(codepoint: int) -> str:
    return f"\\u{codepoint:04X}"


def render_package(specs: list[GlyphSpec]) -> str:
    sections = [s for s in specs if s.name.startswith("section")]
    others = [s for s in specs if not s.name.startswith("section")]
    lines = [
        "# Brand font glyphs (fonts/orbita-brand.ttf), by name.",
        "#",
        "# Generated by tools/build_brand_font.py from brand/. Don't edit: change the",
        "# SVGs and run the tool again.",
        "",
        "substitutions:",
        "  # Logo sections, center first: draw all of them at the same position.",
    ]
    for i, spec in enumerate(sections, 1):
        lines.append(f'  brand_mark_{i}: "{escape(spec.codepoint)}"   # {spec.svg.name}')
    lines.append('  brand_mark_glyphs: "' + "".join(escape(s.codepoint) for s in sections) + '"')
    lines.append("  # Other brand glyphs.")
    for spec in others:
        lines.append(f'  brand_{spec.name}: "{escape(spec.codepoint)}"   # {spec.svg.name}')
    lines.append('  brand_other_glyphs: "' + "".join(escape(s.codepoint) for s in others) + '"')
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed font differs from a fresh build",
    )
    args = parser.parse_args()

    try:
        data, specs = build()
    except ValueError as err:
        print(f"error: {err}")
        return 1
    package = render_package(specs).encode("utf-8")

    outputs = [(OUTPUT, data), (PACKAGE, package)]
    if args.check:
        stale = [path for path, content in outputs if not path.exists() or path.read_bytes() != content]
        for path in stale:
            print(f"{path.relative_to(ROOT).as_posix()} is out of date: run tools/build_brand_font.py")
        if not stale:
            print("fonts/orbita-brand.ttf and fonts/orbita-brand.yaml are up to date")
        return 1 if stale else 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for path, content in outputs:
        path.write_bytes(content)
    print("wrote fonts/orbita-brand.ttf and fonts/orbita-brand.yaml:")
    for spec in specs:
        print(f"  U+{spec.codepoint:04X}  {spec.name:10} {spec.svg.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
