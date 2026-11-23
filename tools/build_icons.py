#!/usr/bin/env python3
"""Build the icon pack packages from the semantic icon names.

Inputs:
  icons/semantic.yaml        the semantic names faces use (${ic_<name>})
  icons/sources/<pack>.yaml  one per pack: font URL + sha256, semantic name ->
                             the pack's own icon name

Output, one per pack:
  icons/<pack>.yaml          ESPHome package with the substitutions
                             `ic_<name>` (the icon's character), `icon_font`
                             (font URL) and `icon_glyphs` (every icon, for the
                             profile's icon fonts)

The pack's font is downloaded once into build/cache/icons/ and checked against
its sha256. Icon names are resolved from the font's own glyph names, so the
codepoints always match the file ESPHome compiles.

It also checks the YAML above the icon layer: every ${ic_<name>} must be a
semantic name, and no raw icon codepoints may appear outside icons/.

Run inside the dev container:

    docker compose run --rm --entrypoint python esphome tools/build_icons.py
    docker compose run --rm --entrypoint python esphome tools/build_icons.py --check
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import logging
import re
import sys
import urllib.request
from pathlib import Path

import yaml
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons"
SEMANTIC = ICONS / "semantic.yaml"
SOURCES = ICONS / "sources"
CACHE = ROOT / "build" / "cache" / "icons"

# Folders whose YAML may use icons; checked for unknown names and raw codepoints.
LINT_DIRS = ["boards", "core", "devices", "faces", "i18n", "profiles", "themes"]
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
USE_RE = re.compile(r"\$\{?ic_([A-Za-z0-9_]+)")
# Private use areas (where icon fonts put their glyphs), raw or escaped.
RAW_CODEPOINT_RE = re.compile(
    r"[-\U000f0000-\U0010fffd]"
    r"|\\u[eEfF][0-9a-fA-F]{3}"
    r"|\\U000[fF][0-9a-fA-F]{4}|\\U0010[0-9a-fA-F]{4}"
)
SOURCE_KEYS = {"name", "title", "version", "license", "url", "sha256", "icons"}
GLYPHS_PER_LINE = 6


# MDI's font has 2 stray bytes in its glyph name table; fontTools warns but reads it fine.
logging.getLogger("fontTools").setLevel(logging.ERROR)


class IconError(Exception):
    pass


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise IconError(f"{rel(path)}: expected a mapping")
    return data


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_semantic() -> list[str]:
    names = list(load_yaml(SEMANTIC))
    bad = [n for n in names if not isinstance(n, str) or not NAME_RE.match(n)]
    if bad:
        raise IconError(f"{rel(SEMANTIC)}: names must be snake_case: {bad}")
    return names


def fetch_font(source: dict, path: Path) -> Path:
    """Return the cached font file, downloading it if needed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{source['name']}-{source['version']}.ttf"
    if not target.exists():
        print(f"downloading {source['url']}")
        request = urllib.request.Request(source["url"], headers={"User-Agent": "orbita-build-icons"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        target.write_bytes(data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != source["sha256"]:
        target.unlink()
        raise IconError(f"{rel(path)}: font sha256 is {digest}, expected {source['sha256']}")
    return target


def escape(codepoint: int) -> str:
    return f"\\u{codepoint:04X}" if codepoint <= 0xFFFF else f"\\U{codepoint:08X}"


def resolve(source: dict, path: Path, names: list[str]) -> dict[str, int]:
    """Map each semantic name to its codepoint in the pack's font."""
    mapping = source["icons"]
    missing = [n for n in names if n not in mapping]
    extra = [n for n in mapping if n not in names]
    if missing:
        raise IconError(f"{rel(path)}: no icon for {missing}")
    if extra:
        raise IconError(f"{rel(path)}: not in {rel(SEMANTIC)}: {extra}")

    cmap = TTFont(fetch_font(source, path), lazy=True).getBestCmap()
    by_name = {glyph: codepoint for codepoint, glyph in cmap.items()}
    result = {}
    for name in names:
        icon = mapping[name]
        if icon not in by_name:
            close = difflib.get_close_matches(icon, by_name, n=3)
            hint = f" (did you mean {', '.join(close)}?)" if close else ""
            raise IconError(f"{rel(path)}: {name}: no icon '{icon}' in the font{hint}")
        result[name] = by_name[icon]
    return result


def render_package(source: dict, path: Path, codepoints: dict[str, int]) -> str:
    glyphs = [escape(cp) for cp in dict.fromkeys(codepoints.values())]
    glyph_lines = [
        "".join(glyphs[i : i + GLYPHS_PER_LINE]) for i in range(0, len(glyphs), GLYPHS_PER_LINE)
    ]
    width = max(len(n) for n in codepoints) + len("ic_") + 1
    lines = [
        f"# Icon pack: {source['title']} {source['version']} ({source['license']}).",
        "#",
        f"# Generated by tools/build_icons.py from {rel(SEMANTIC)} and {rel(path)}.",
        "# Don't edit: change those files and run the tool again.",
        "",
        "substitutions:",
        f"  icon_pack: {source['name']}",
        f"  icon_font: {source['url']}",
        "  # Every icon below, compiled into the profile's icon fonts.",
                # A backslash at the end of a line continues a double-quoted YAML
        # string without adding a space or line break.
        '  icon_glyphs: "' + "\\\n    ".join(glyph_lines) + '"',
        "",
    ]
    for name, cp in codepoints.items():
        key = f"ic_{name}:".ljust(width)
        lines.append(f'  {key} "{escape(cp)}"   # {source["icons"][name]}')
    return "\n".join(lines) + "\n"


def verify_package(text: str, path: Path, codepoints: dict[str, int]) -> None:
    """Parse the generated package back and compare it with what was meant."""
    subs = yaml.safe_load(text)["substitutions"]
    for name, cp in codepoints.items():
        if subs[f"ic_{name}"] != chr(cp):
            raise IconError(f"{rel(path)}: generated ic_{name} doesn't parse back")
    if set(subs["icon_glyphs"]) != {chr(cp) for cp in codepoints.values()}:
        raise IconError(f"{rel(path)}: generated icon_glyphs doesn't parse back")


def lint(names: list[str]) -> list[str]:
    known = set(names)
    problems = []
    for folder in LINT_DIRS:
        for path in sorted((ROOT / folder).rglob("*.yaml")):
            if path.name == "secrets.yaml":
                continue
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for match in USE_RE.finditer(line):
                    if match.group(1) not in known:
                        problems.append(
                            f"{rel(path)}:{lineno}: unknown icon ic_{match.group(1)} "
                            f"(add it to {rel(SEMANTIC)})"
                        )
                if RAW_CODEPOINT_RE.search(line):
                    problems.append(
                        f"{rel(path)}:{lineno}: raw icon codepoint, use an ${{ic_<name>}} icon"
                    )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if a committed pack package is out of date or an icon use is invalid",
    )
    args = parser.parse_args()

    failed = False
    try:
        names = load_semantic()
        sources = sorted(SOURCES.glob("*.yaml"))
        if not sources:
            raise IconError(f"no icon packs in {rel(SOURCES)}")
        for path in sources:
            source = load_yaml(path)
            if set(source) != SOURCE_KEYS:
                raise IconError(f"{rel(path)}: keys must be {sorted(SOURCE_KEYS)}")
            if source["name"] != path.stem:
                raise IconError(f"{rel(path)}: name must match the file name")
            codepoints = resolve(source, path, names)
            text = render_package(source, path, codepoints)
            verify_package(text, path, codepoints)

            output = ICONS / f"{source['name']}.yaml"
            if args.check:
                if not output.exists() or output.read_text(encoding="utf-8") != text:
                    print(f"{rel(output)} is out of date: run tools/build_icons.py")
                    failed = True
                else:
                    print(f"{rel(output)} is up to date")
            else:
                output.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {rel(output)}: {len(codepoints)} icons")
    except IconError as err:
        print(f"error: {err}")
        return 1

    problems = lint(names)
    for problem in problems:
        print(problem)
    if problems:
        failed = True
    else:
        print(f"icon uses ok ({len(names)} semantic names)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
