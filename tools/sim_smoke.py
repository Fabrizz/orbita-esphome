#!/usr/bin/env python3
"""Boot a simulator device for a few seconds and check that it starts.

Compiles DEVICE (a host-sdl device file in devices/), runs the program and fails
if it exits early or never finishes setup(). With --snapshot it also saves a
screenshot of the screen to the snapshot folder.

With --fake-ha it also plays Home Assistant over the native API: connect and
subscribe, disconnect, reconnect. It fails unless the shell goes through the
expected connection stages and screens, and saves a snapshot of every screen
the shell settles on (scr-<N>-<SCREEN>-<STAGE>.bmp, numbered in order).

Snapshots from an earlier run with the same names are deleted first: the
simulator never overwrites a snapshot file.

Needs a display: run it inside the dev container (WSLg on Windows) or under
`xvfb-run` on a headless machine:

    docker compose run --rm --entrypoint python esphome tools/sim_smoke.py devices/example-sim-r480.yaml
"""

from __future__ import annotations

import argparse
import asyncio
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
API_PORT = 6053
# What the shell must log, in this order, during the --fake-ha scenario.
FAKE_HA_EXPECTED = [
    "Connection: BOOTING -> CONNECTING",
    "Screen: BOOT",
    "Screen: BOOT -> CONNECTION",
    "Connection: CONNECTING -> SYNCING",
    "Connection: SYNCING -> READY",
    "Screen: CONNECTION -> HOME",
    "Connection: READY -> LOST",
    "Screen: HOME -> CONNECTION",
    "Connection: LOST -> SYNCING",
    "Connection: SYNCING -> READY",
    "Screen: CONNECTION -> HOME",
]
PROGRAM_PATH = re.compile(r"Successfully compiled program to path '([^']+)'")


def write_wrapper(device: Path, snapshot_name: str | None, seconds: int, fake_ha: bool) -> Path:
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
    if fake_ha:
        # One snapshot per screen the shell settles on: 900 ms after it is
        # shown (the boot intro is over by then), if it is still showing.
        lines += [
            "script:",
            "  - id: smoke_snapshot",
            "    mode: parallel",
            "    parameters:",
            "      screen: int",
            "    then:",
            "      - delay: 900ms",
            "      - if:",
            "          condition:",
            "            lambda: return static_cast<int>(id(shell).get_screen()) == screen;",
            "          then:",
            "            - snapshot.take:",
            "                filename: !lambda |-",
            "                  static int count = 0;",
            "                  return \"scr-\" + std::to_string(++count) + \"-\" + id(shell).screen_str() + \"-\"",
            "                      + id(shell).connection_str() + \".bmp\";",
            "knob_shell:",
            "  screens:",
        ]
        for name, enum in (("boot", "BOOT"), ("connection", "CONNECTION"), ("home", "HOME")):
            lines += [
                f"    {name}:",
                "      on_enter:",
                "        - script.execute:",
                "            id: smoke_snapshot",
                f"            screen: !lambda return static_cast<int>(knob_shell::Screen::{enum});",
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


class Log:
    """Output of the running program, collected by a reader thread."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def text(self) -> str:
        return "".join(self.lines)

    async def wait_for(self, needle: str, count: int = 1, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while self.text().count(needle) < count:
            if time.monotonic() > deadline:
                raise TimeoutError(f"'{needle}' (x{count}) not in the log after {timeout:.0f} s")
            await asyncio.sleep(0.1)


def api_key(device: Path) -> str:
    """The device's API encryption key, from secrets.yaml next to it."""
    import yaml  # ESPHome's dependency; only needed here

    secrets = yaml.safe_load((device.parent / "secrets.yaml").read_text(encoding="utf-8"))
    return secrets["api_encryption_key"]


async def fake_ha(log: Log, key: str) -> None:
    """Connect, drop and reconnect like Home Assistant would."""
    from aioesphomeapi import APIClient  # ESPHome's dependency; only needed here

    async def connect() -> APIClient:
        client = APIClient("127.0.0.1", API_PORT, noise_psk=key, client_info="orbita-sim-test")
        await client.connect(login=True)
        client.subscribe_states(lambda state: None)
        return client

    await log.wait_for("Screen: BOOT -> CONNECTION")
    await asyncio.sleep(2)  # the connection screen, waiting for Home Assistant
    client = await connect()
    await log.wait_for("Connection: SYNCING -> READY")
    await asyncio.sleep(2)
    await client.disconnect()
    await log.wait_for("Connection: READY -> LOST")
    await asyncio.sleep(2)
    client = await connect()
    await log.wait_for("Connection: SYNCING -> READY", count=2)
    await asyncio.sleep(2)
    await client.disconnect()


def in_order(text: str, expected: list[str]) -> str | None:
    """Return the first entry of EXPECTED missing from TEXT in that order."""
    position = 0
    for needle in expected:
        found = text.find(needle, position)
        if found < 0:
            return needle
        position = found + len(needle)
    return None


def clear_snapshots(program: Path, names: list[str]) -> None:
    """Delete snapshots from earlier runs that this run would write again.

    The program is <data dir>/build/<name>/.pioenvs/<name>/program and the
    simulator saves snapshots to <data dir>/snapshots/<name>/.
    """
    folder = program.parents[4] / "snapshots" / program.parent.name
    for pattern in names:
        for old in folder.glob(pattern):
            old.unlink()


def run_program(program: Path, seconds: int, scenario=None) -> tuple[bool, bool, str, str | None]:
    """Run PROGRAM for at least SECONDS, plus SCENARIO(log) if given.

    Returns (still_running, setup_done, log, scenario_error).
    """
    process = subprocess.Popen(
        [str(program)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    log = Log()
    reader = threading.Thread(target=lambda: log.lines.extend(process.stdout), daemon=True)
    reader.start()

    start = time.monotonic()
    error = None
    if scenario is not None:

        async def run_scenario() -> None:
            await log.wait_for(SETUP_DONE, timeout=30)
            await scenario(log)

        try:
            asyncio.run(run_scenario())
        except Exception as err:  # noqa: BLE001 - reported as a test failure
            error = f"{type(err).__name__}: {err}"

    deadline = start + seconds
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

    text = log.text()
    return still_running, SETUP_DONE in text, text, error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("device", type=Path, help="host-sdl device file, e.g. devices/example-sim-r480.yaml")
    parser.add_argument("--seconds", type=int, default=10, help="how long the program must keep running")
    parser.add_argument(
        "--snapshot",
        metavar="NAME",
        help="also save a screenshot named NAME (e.g. smoke.bmp) to the snapshot folder",
    )
    parser.add_argument(
        "--fake-ha",
        action="store_true",
        help="act as Home Assistant (connect, drop, reconnect) and check the shell's connection gate",
    )
    args = parser.parse_args()

    device = args.device.resolve()
    if not device.is_file():
        raise SystemExit(f"Not found: {args.device}")

    scenario = None
    if args.fake_ha:
        key = api_key(device)

        def scenario(log: Log):
            return fake_ha(log, key)

    wrapper = write_wrapper(device, args.snapshot, args.seconds, args.fake_ha)
    try:
        program = compile_program(wrapper)
        clear_snapshots(program, ([args.snapshot] if args.snapshot else []) + (["scr-*.bmp"] if args.fake_ha else []))
        still_running, setup_done, log, error = run_program(program, args.seconds, scenario)
    finally:
        wrapper.unlink(missing_ok=True)

    print(log)
    if not still_running:
        print(f"FAIL {args.device}: the program exited within {args.seconds} s")
        return 1
    if not setup_done:
        print(f"FAIL {args.device}: '{SETUP_DONE}' never appeared in the log")
        return 1
    if args.fake_ha:
        if error:
            print(f"FAIL {args.device}: fake Home Assistant: {error}")
            return 1
        missing = in_order(log, FAKE_HA_EXPECTED)
        if missing:
            print(f"FAIL {args.device}: expected '{missing}' (in this order: {FAKE_HA_EXPECTED})")
            return 1
        print(f"OK {args.device}: connection gate went through {len(FAKE_HA_EXPECTED)} expected steps")
    print(f"OK {args.device}: booted and ran for {args.seconds} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
