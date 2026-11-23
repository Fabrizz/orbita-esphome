#!/usr/bin/env python3
"""Boot a simulator device for a few seconds and check that it starts.

Compiles DEVICE (a host-sdl device file in devices/), runs the program and fails
if it exits early or never finishes setup(). With --snapshot it also saves a
screenshot of the screen to the snapshot folder.

Needs a display: run it inside the dev container (WSLg on Windows) or under
`xvfb-run` on a headless machine:

    docker compose run --rm --entrypoint python esphome tools/sim_smoke.py devices/example-sim-r480.yaml
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SETUP_DONE = "setup() finished successfully"
PROGRAM_PATH = re.compile(r"Successfully compiled program to path '([^']+)'")


def write_wrapper(device: Path, snapshot_name: str | None, seconds: int) -> Path:
    """Write a temporary device file next to DEVICE that includes it.

    It must live in the same folder, because local paths in the config resolve
    against the folder of the file being built.
    """
    lines = ["packages:", f"  device: !include {device.name}"]
    if snapshot_name:
        delay = max(1, seconds // 2)
        lines += [
            "interval:",
            f"  - interval: {seconds}s",
            f"    startup_delay: {delay}s",
            "    then:",
            f"      - snapshot.take: {{ filename: {snapshot_name} }}",
        ]
    fd, name = tempfile.mkstemp(prefix=".smoke-", suffix=".yaml", dir=device.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return Path(name)


def compile_program(config: Path) -> Path:
    result = subprocess.run(
        ["esphome", "compile", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(output)
        raise SystemExit(f"Compile failed: {config}")
    match = PROGRAM_PATH.search(output)
    if not match:
        print(output)
        raise SystemExit("Compiled, but the program path was not found in the output")
    return Path(match.group(1))


def run_program(program: Path, seconds: int) -> tuple[bool, bool, str]:
    """Run PROGRAM for SECONDS. Returns (still_running, setup_done, log)."""
    process = subprocess.Popen(
        [str(program)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    log: list[str] = []
    reader = threading.Thread(target=lambda: log.extend(process.stdout), daemon=True)
    reader.start()

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.2)

    still_running = process.poll() is None
    if still_running:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    reader.join(timeout=2)

    text = "".join(log)
    return still_running, SETUP_DONE in text, text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("device", type=Path, help="host-sdl device file, e.g. devices/example-sim-r480.yaml")
    parser.add_argument("--seconds", type=int, default=10, help="how long the program must keep running")
    parser.add_argument(
        "--snapshot",
        metavar="NAME",
        help="also save a screenshot named NAME (e.g. smoke.bmp) to the snapshot folder",
    )
    args = parser.parse_args()

    device = args.device.resolve()
    if not device.is_file():
        raise SystemExit(f"Not found: {args.device}")

    wrapper = write_wrapper(device, args.snapshot, args.seconds)
    try:
        program = compile_program(wrapper)
        still_running, setup_done, log = run_program(program, args.seconds)
    finally:
        wrapper.unlink(missing_ok=True)

    print(log)
    if not still_running:
        print(f"FAIL {args.device}: the program exited within {args.seconds} s")
        return 1
    if not setup_done:
        print(f"FAIL {args.device}: '{SETUP_DONE}' never appeared in the log")
        return 1
    print(f"OK {args.device}: booted and ran for {args.seconds} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
