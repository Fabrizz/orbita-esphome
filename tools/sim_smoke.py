#!/usr/bin/env python3
"""Boot a simulator device for a few seconds and check that it starts.

Compiles DEVICE (a host-sdl device file in devices/), runs the program and fails
if it exits early or never finishes setup(). With --snapshot it also saves a
screenshot of the screen to the snapshot folder.

With --fake-ha it also plays Home Assistant over the native API and checks the
shell end to end:

- Connection gate: connect and subscribe, disconnect, reconnect. The device
  gets one extra Home Assistant entity the shell waits for while syncing; the
  fake sends its state 1.5 s late, so the syncing stage is visible.
- Entities: every entity the device asks for gets a state ("off" for faces),
  and `homeassistant.toggle` calls flip it and send the new state back, like
  Home Assistant would.
- Strip: the device's strip (from its log) is walked to the right end and
  back with knob turns; the first app face gets a knob press, which must
  reach Home Assistant as a toggle. A lost connection must come back to the
  same strip item.

Knob input goes through test-only API actions that call the shell like the
board does. Snapshots: scr-<N>-<VIEW>-<STAGE>.bmp for every screen and stage
the shell settles on, plus step-<name>.bmp at chosen moments. Snapshots from an
earlier run with the same names are deleted first: the simulator never
overwrites a snapshot file.

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
# Home Assistant entity the test device waits for while syncing.
SYNC_ENTITY = "sensor.orbita_sim_test"
SYNC_DELAY = 1.5
# Time for a screen to settle and its snapshot (taken after 900 ms) to be written.
SETTLE = 1.2
# The connection gate: what the shell must log, in this order.
FAKE_HA_EXPECTED = [
    "Connection: BOOTING -> CONNECTING",
    "Screen: BOOT",
    "Screen: BOOT -> CONNECTION",
    "Connection: CONNECTING -> SYNCING",
    "Connection: SYNCING -> READY",
    "Screen: CONNECTION -> HOME",
    "Connection: READY -> LOST",
    "Connection: LOST -> SYNCING",
    "Connection: SYNCING -> READY",
]
PROGRAM_PATH = re.compile(r"Successfully compiled program to path '([^']+)'")
STRIP_LINE = re.compile(r"Strip: ([^\x1b\r\n]+)")


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
        lines += [
            # An entity the shell waits for while syncing.
            "sensor:",
            "  - platform: homeassistant",
            "    id: smoke_sync_entity",
            f"    entity_id: {SYNC_ENTITY}",
            "    internal: true",
            "esphome:",
            "  on_boot:",
            "    - lambda: id(shell).add_sync_check([]() { return id(smoke_sync_entity).has_state(); });",
            # Test input: the same calls the board makes for the knob.
            "api:",
            "  actions:",
            "    - action: smoke_knob",
            "      variables:",
            "        steps: int",
            "      then:",
            "        - lambda: id(shell).knob_delta(steps);",
            "    - action: smoke_press",
            "      then:",
            "        - lambda: |-",
            "            id(shell).knob_button(true);",
            "            id(shell).knob_button(false);",
            "    - action: smoke_snapshot",
            "      variables:",
            "        name: string",
            "      then:",
            "        - snapshot.take:",
            "            filename: !lambda return \"step-\" + name + \".bmp\";",
            # One snapshot per screen + stage the shell settles on: 900 ms after
            # a change (the boot intro is over by then), if nothing changed
            # since and it isn't the same as the previous snapshot.
            "script:",
            "  - id: smoke_settled",
            "    mode: parallel",
            "    parameters:",
            "      view: string",
            "      stage: int",
            "    then:",
            "      - delay: 900ms",
            "      - if:",
            "          condition:",
            "            lambda: |-",
            "              static std::string last;",
            "              if (id(shell).view_str() != view || static_cast<int>(id(shell).get_connection()) != stage)",
            "                return false;",
            "              std::string key = view + \"-\" + id(shell).connection_str();",
            "              if (key == last)",
            "                return false;",
            "              last = key;",
            "              return true;",
            "          then:",
            "            - snapshot.take:",
            "                filename: !lambda |-",
            "                  static int count = 0;",
            "                  std::string shown = id(shell).screen_str();",
            "                  if (*id(shell).app_id())",
            "                    shown += std::string(\"-\") + id(shell).app_id();",
            "                  return \"scr-\" + std::to_string(++count) + \"-\" + shown + \"-\" + id(shell).connection_str() + \".bmp\";",
            "knob_shell:",
            "  on_connection_change:",
            "    - script.execute:",
            "        id: smoke_settled",
            "        view: !lambda return id(shell).view_str();",
            "        stage: !lambda return static_cast<int>(stage);",
            "  on_screen_change:",
            "    - script.execute:",
            "        id: smoke_settled",
            "        view: !lambda return id(shell).view_str();",
            "        stage: !lambda return static_cast<int>(id(shell).get_connection());",
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


class FakeHA:
    """Just enough of Home Assistant: states for the device's entities, and
    toggle calls answered with the new state."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.states: dict[str, str] = {}
        self.toggled: list[str] = []
        self.client = None
        self.actions = {}

    async def connect(self, delay_sync: bool) -> None:
        from aioesphomeapi import APIClient  # ESPHome's dependency; only needed here

        client = APIClient("127.0.0.1", API_PORT, noise_psk=self.key, client_info="orbita-sim-test")
        await client.connect(login=True)
        requested: list[str] = []

        def on_action(call) -> None:
            entity = call.data.get("entity_id", "")
            if call.service == "homeassistant.toggle" and entity in self.states:
                self.toggled.append(entity)
                self.states[entity] = "off" if self.states[entity] == "on" else "on"
                client.send_home_assistant_state(entity, None, self.states[entity])

        client.subscribe_home_assistant_states_and_services(
            on_state=lambda state: None,
            on_service_call=on_action,
            on_state_sub=lambda entity_id, attribute: requested.append(entity_id),
        )
        await asyncio.sleep(0.3)  # the device asks for its entities right after subscribing
        for entity in requested:
            if entity != SYNC_ENTITY:
                client.send_home_assistant_state(entity, None, self.states.setdefault(entity, "off"))
        if delay_sync:
            await asyncio.sleep(SYNC_DELAY)  # the syncing stage, waiting for the last entity
        if SYNC_ENTITY not in requested:
            raise RuntimeError(f"the device never asked for {SYNC_ENTITY} (asked for {requested})")
        client.send_home_assistant_state(SYNC_ENTITY, None, "21.5")
        _, services = await client.list_entities_services()
        self.actions = {service.name: service for service in services}
        self.client = client

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def run(self, action: str, **data) -> None:
        await self.client.execute_service(self.actions[action], data)


async def fake_ha(log: Log, key: str) -> None:
    """The --fake-ha scenario (see the module docstring)."""
    ha = FakeHA(key)

    async def knob(steps: int) -> None:
        await ha.run("smoke_knob", steps=steps)

    async def snapshot(name: str) -> None:
        await ha.run("smoke_snapshot", name=name)
        await asyncio.sleep(0.3)

    match = STRIP_LINE.search(log.text())
    if not match:
        raise RuntimeError("the shell logged no 'Strip:' line")
    strip = match.group(1).split()
    if "HOME" not in strip:
        raise RuntimeError(f"no HOME on the strip: {strip}")
    home = strip.index("HOME")

    # Connection gate, first time.
    await log.wait_for("Screen: BOOT -> CONNECTION")
    await asyncio.sleep(2)  # the connection screen, waiting for Home Assistant
    await ha.connect(delay_sync=True)
    info = await ha.client.device_info()
    print(
        f"device info: project {info.project_name!r} {info.project_version!r}, "
        f"model {info.model!r}, manufacturer {info.manufacturer!r}"
    )
    await log.wait_for("Screen: CONNECTION -> HOME")
    await asyncio.sleep(SETTLE)

    # Walk right to the end of the strip, pressing on the first app.
    pos = home
    pressed = False
    while pos + 1 < len(strip):
        await knob(1)
        await log.wait_for(f"Screen: {strip[pos]} -> {strip[pos + 1]}")
        pos += 1
        await asyncio.sleep(SETTLE)
        if not pressed and strip[pos].startswith("APP("):
            pressed = True
            await ha.run("smoke_press")
            deadline = time.monotonic() + 5
            while not ha.toggled:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"a press on {strip[pos]} sent no homeassistant.toggle")
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.5)
            await snapshot(f"pressed-{strip[pos][4:-1]}")

    # At the end the strip doesn't move.
    screens = log.text().count("Screen: ")
    await knob(1)
    await asyncio.sleep(1)
    if log.text().count("Screen: ") != screens:
        raise RuntimeError(f"turning past the end of the strip left {strip[pos]}")

    # A lost connection comes back to the same item.
    await ha.disconnect()
    await log.wait_for(f"Screen: {strip[pos]} -> CONNECTION")
    await asyncio.sleep(2)
    await ha.connect(delay_sync=False)
    await log.wait_for(f"Screen: CONNECTION -> {strip[pos]}")
    await asyncio.sleep(SETTLE)

    # Walk back to HOME.
    while pos > home:
        await knob(-1)
        await log.wait_for(f"Screen: {strip[pos]} -> {strip[pos - 1]}")
        pos -= 1
        await asyncio.sleep(0.4)
    await asyncio.sleep(SETTLE)
    await ha.disconnect()
    print(f"strip walked: {' '.join(strip)}; toggled: {ha.toggled}")


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
            await log.wait_for("Strip: ", timeout=10)
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
        help="act as Home Assistant and check the connection gate, the strip and the faces",
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
        patterns = [args.snapshot] if args.snapshot else []
        if args.fake_ha:
            patterns += ["scr-*.bmp", "step-*.bmp"]
        clear_snapshots(program, patterns)
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
        print(f"OK {args.device}: connection gate, strip and faces behaved as expected")
    print(f"OK {args.device}: booted and ran for {args.seconds} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
