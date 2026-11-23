#!/usr/bin/env python3
"""Check that .esphome-version and requirements.txt pin the same ESPHome version."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    pinned = (ROOT / ".esphome-version").read_text(encoding="utf-8").strip()

    required = None
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*esphome\s*==\s*([^\s#]+)", line, re.IGNORECASE)
        if match:
            required = match.group(1)
            break

    if required is None:
        print("requirements.txt: no 'esphome==<version>' line found")
        return 1
    if required != pinned:
        print(f"Version mismatch: .esphome-version is {pinned}, requirements.txt pins {required}")
        return 1

    print(f"ESPHome pinned to {pinned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
