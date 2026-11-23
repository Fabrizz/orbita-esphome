# Orbita

ESPHome + LVGL firmware framework for round ESP32 displays — knobs with a rotary encoder,
a touchscreen, or both — that control Home Assistant.

One codebase for many boards: a board file describes the hardware, everything else (screens,
navigation, themes, translations, icons) is shared.

> **Status: early development.** Nothing is usable yet. Interfaces and file layout will change.

## Planned

- Round displays from 240 to 480 px (SPI, QSPI and RGB panels), encoder and/or touch
- A PC simulator that runs the same configuration in a desktop window
- Interchangeable screen designs, themes and icon packs
- Responsive, optimistic controls for lights, climate, covers, media and more
- Local only: no cloud, no auto-update; local ESPHome OTA

## Target boards

| Board | Resolution |
|---|---|
| Elecrow CrowPanel 2.1" | 480 × 480 |
| Elecrow CrowPanel 1.28" / M5Stack Dial | 240 × 240 |
| PC simulator (`host` + SDL) | any |

More boards later.

## Requirements

- ESPHome — the exact version is pinned in [`.esphome-version`](.esphome-version)
- Either **Docker** (recommended, any OS) or a native Python install
  (`pip install -r requirements.txt`)
- For the simulator: Docker Desktop on Windows 11 (window shown through WSLg), or Linux/macOS
  with SDL2 development libraries

## Building with Docker

The image in [`tools/docker/`](tools/docker/Dockerfile) contains ESPHome, the SDL2 libraries and
a C++ toolchain. Build output and toolchains are kept in Docker volumes, not in the repo.

```sh
docker compose build                                    # once, and after a version bump

docker compose run --rm esphome compile devices/<device>.yaml          # ESP32 firmware
docker compose run --rm esphome upload --device <ip> devices/<device>.yaml    # OTA
docker compose run --rm --service-ports esphome run devices/<device>-sim.yaml # simulator
```

`--service-ports` publishes the simulator's API port (6053), so Home Assistant can add it by
this PC's IP address. Docker Desktop on Windows can't reach USB serial ports: do the first USB
flash with a native install (`esphome upload --device COM3 <file>`) or the ESPHome web flasher,
then update over the network.

## Simulator

```sh
cp devices/secrets.example.yaml devices/secrets.yaml   # once; fill in the API key
docker compose run --rm --service-ports esphome run devices/example-sim-r480.yaml
docker compose run --rm --service-ports esphome run devices/example-sim-r240.yaml
```

| Input | Simulates |
|---|---|
| Mouse | touchscreen |
| ← / → | knob turn |
| Space | knob button |
| F12 | screenshot, saved to `build/snapshots/<device>/` |

Boot check (what CI runs): compiles the device, runs it for a few seconds and fails if it
crashes or never finishes setup; `--snapshot` also saves a screenshot.

```sh
docker compose run --rm --entrypoint python esphome tools/sim_smoke.py devices/example-sim-r480.yaml --snapshot smoke.bmp
```

## Continuous integration

- **CI** (every push and pull request): checks the ESPHome version pin, compiles every
  `devices/example-*.yaml` and boots the simulator ones under a virtual display (Xvfb).
  Screenshots are attached to the run.
- **Latest ESPHome** (1st of every month, or run by hand): the same builds with the newest
  ESPHome release instead of the pinned one, to catch breaking changes early.
- Both also build `devices/example-remote.yaml` from a folder outside the repo, downloading
  Orbita from GitHub at the commit being tested, exactly as a user's device file does.

## Using it from your own ESPHome setup

You don't need a copy of this repository: a device file can pull Orbita straight from GitHub,
pinned to a version. See [`devices/example-remote.yaml`](devices/example-remote.yaml):

```yaml
substitutions:
  orbita_ref: v0.1.0              # Orbita version, used for packages and components

packages:
  orbita:
    url: https://github.com/Fabrizz/orbita-esphome
    ref: ${orbita_ref}
    files:
      - boards/<board>.yaml
      - i18n/en.yaml
      - themes/dark.yaml
      - core/all.yaml
```

Builds with an ESPHome older than the supported version stop with a clear "too old" error.

## Repository layout

| Folder | Contents |
|---|---|
| `boards/` | hardware files, one per board |
| `profiles/` | sizes and fonts per screen resolution |
| `core/` | shared firmware core and system screens |
| `components/` | C++ ESPHome components (the shell) |
| `faces/` | screens for each Home Assistant entity type |
| `themes/`, `i18n/`, `icons/` | colors, translations, icon packs |
| `devices/` | example device configurations |
| `tools/` | build and check scripts |
| `website/` | user guide and blog |

## License

[MIT](LICENSE)
