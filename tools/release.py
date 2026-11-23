#!/usr/bin/env python3
"""Release helpers. The version lives in core/version.yaml (`orbita_version`).

    release.py version                 print the version
    release.py check --branch BRANCH   validate a release pull request into main
    release.py notes VERSION           print the CHANGELOG.md section of VERSION
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "core" / "version.yaml"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BRANCH = re.compile(r"^(release|hotfix)/(.+)$")


def read_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^\s*orbita_version:\s*"?([^"\s#]+)"?', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"{VERSION_FILE.relative_to(ROOT)}: no orbita_version found")
    return match.group(1)


def parse(version: str) -> tuple[int, int, int] | None:
    match = SEMVER.match(version)
    return tuple(int(part) for part in match.groups()) if match else None


def release_tags() -> list[str]:
    output = subprocess.run(
        ["git", "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [tag for tag in output.split() if parse(tag[1:])]


def changelog_section(version: str) -> str | None:
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    heading = re.compile(rf"^## \[{re.escape(version)}\]")
    for start, line in enumerate(lines):
        if heading.match(line):
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
                len(lines),
            )
            return "\n".join(lines[start + 1 : end]).strip()
    return None


def check(branch: str) -> int:
    errors: list[str] = []
    version = read_version()
    current = parse(version)

    match = BRANCH.match(branch)
    if not match:
        errors.append(f"branch '{branch}' is not release/<version> or hotfix/<version>")
    elif match.group(2) != version:
        errors.append(f"branch '{branch}' does not match orbita_version {version}")

    if current is None:
        errors.append(f"orbita_version '{version}' is not MAJOR.MINOR.PATCH")
    else:
        tags = release_tags()
        if f"v{version}" in tags:
            errors.append(f"tag v{version} already exists")
        newer_or_equal = [t for t in tags if parse(t[1:]) >= current]
        if newer_or_equal:
            latest = max(newer_or_equal, key=lambda t: parse(t[1:]))
            errors.append(f"{version} is not higher than the latest release {latest}")

    if not re.search(
        r"^\s*orbita_ref:\s*v\$\{orbita_version\}\s*$",
        VERSION_FILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
        errors.append("core/version.yaml must keep `orbita_ref: v${orbita_version}`")

    section = changelog_section(version)
    if not section:
        errors.append(f"CHANGELOG.md has no (or an empty) '## [{version}]' section")

    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"OK release {version} from {branch}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print the version")
    check_parser = commands.add_parser("check", help="validate a release pull request")
    check_parser.add_argument("--branch", required=True, help="source branch of the pull request")
    notes_parser = commands.add_parser("notes", help="print the changelog section of a version")
    notes_parser.add_argument("version")
    args = parser.parse_args()

    if args.command == "version":
        print(read_version())
        return 0
    if args.command == "check":
        return check(args.branch)
    section = changelog_section(args.version)
    if section is None:
        print(f"CHANGELOG.md has no '## [{args.version}]' section", file=sys.stderr)
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
