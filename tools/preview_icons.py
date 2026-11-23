#!/usr/bin/env python3
"""Render a preview image of every icon pack: icons/previews/<pack>.png.

One cell per semantic name (in icons/semantic.yaml order, grouped by its
section comments): the pack's icon at a large and a small size, the semantic
name and the pack's own icon name. Colors follow the default dark theme.

The previews are for people choosing or reviewing icons. Nothing checks that
they are current; run the tool again after changing icons:

    docker compose run --rm --entrypoint python esphome tools/preview_icons.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_icons import (
    ICONS,
    SEMANTIC,
    SOURCES,
    IconError,
    fetch_font,
    load_semantic,
    load_yaml,
    rel,
    resolve,
)

OUTPUT_DIR = ICONS / "previews"

COLUMNS = 6
CELL_W, CELL_H = 150, 112
GAP = 8
MARGIN = 20
ICON_BIG, ICON_SMALL = 48, 16

BG = "#000000"
CELL = "#181818"
TEXT = "#F0F0F0"
TEXT_DIM = "#989898"
ACCENT = "#FFB000"

GROUP_RE = re.compile(r"^#\s*(\S.*)$")
NAME_RE = re.compile(r"^([a-z][a-z0-9_]*):")


def groups(names: list[str]) -> list[tuple[str, list[str]]]:
    """Split the names by section: a comment line directly above a name."""
    result: list[tuple[str, list[str]]] = []
    previous = ""
    for line in SEMANTIC.read_text(encoding="utf-8").splitlines():
        name = NAME_RE.match(line)
        if name and name.group(1) in names:
            heading = GROUP_RE.match(previous)
            if heading or not result:
                result.append((heading.group(1) if heading else "", []))
            result[-1][1].append(name.group(1))
        previous = line
    return result


def draw_centered(draw: ImageDraw.ImageDraw, center: tuple[float, float], text: str, font, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = center[0] - (left + right) / 2
    y = center[1] - (top + bottom) / 2
    draw.text((x, y), text, font=font, fill=fill)


def render(source: dict, font_path: Path, codepoints: dict[str, int], sections) -> Image.Image:
    big = ImageFont.truetype(str(font_path), ICON_BIG)
    small = ImageFont.truetype(str(font_path), ICON_SMALL)
    title_font = ImageFont.load_default(size=18)
    heading_font = ImageFont.load_default(size=14)
    name_font = ImageFont.load_default(size=13)
    dim_font = ImageFont.load_default(size=11)

    heading_h = 26
    title_h = 40
    rows = sum((len(items) + COLUMNS - 1) // COLUMNS for _, items in sections)
    width = MARGIN * 2 + COLUMNS * CELL_W + (COLUMNS - 1) * GAP
    height = (
        MARGIN * 2
        + title_h
        + sum(heading_h for title, _ in sections if title)
        + rows * (CELL_H + GAP)
    )

    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text(
        (MARGIN, MARGIN),
        f"{source['title']} {source['version']}  ·  {len(codepoints)} icons  ·  {source['license']}",
        font=title_font,
        fill=TEXT,
    )

    y = MARGIN + title_h
    for title, items in sections:
        if title:
            draw.text((MARGIN, y), title, font=heading_font, fill=ACCENT)
            y += heading_h
        for i, name in enumerate(items):
            col, row = i % COLUMNS, i // COLUMNS
            x0 = MARGIN + col * (CELL_W + GAP)
            y0 = y + row * (CELL_H + GAP)
            draw.rounded_rectangle((x0, y0, x0 + CELL_W, y0 + CELL_H), radius=8, fill=CELL)
            glyph = chr(codepoints[name])
            draw_centered(draw, (x0 + CELL_W / 2, y0 + 36), glyph, big, TEXT)
            draw_centered(draw, (x0 + CELL_W - 16, y0 + 16), glyph, small, TEXT_DIM)
            # Labels share a baseline ("ms" = middle, baseline) so descenders don't shift them.
            draw.text((x0 + CELL_W / 2, y0 + 83), name, font=name_font, fill=TEXT, anchor="ms")
            draw.text(
                (x0 + CELL_W / 2, y0 + 100), source["icons"][name], font=dim_font, fill=TEXT_DIM, anchor="ms"
            )
        y += ((len(items) + COLUMNS - 1) // COLUMNS) * (CELL_H + GAP)
    return image


def main() -> int:
    try:
        names = load_semantic()
        sections = groups(names)
        sources = sorted(SOURCES.glob("*.yaml"))
        if not sources:
            raise IconError(f"no icon packs in {rel(SOURCES)}")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for path in sources:
            source = load_yaml(path)
            codepoints = resolve(source, path, names)
            image = render(source, fetch_font(source, path), codepoints, sections)
            output = OUTPUT_DIR / f"{source['name']}.png"
            image.save(output, optimize=True)
            print(f"wrote {rel(output)}: {len(codepoints)} icons")
    except IconError as err:
        print(f"error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
