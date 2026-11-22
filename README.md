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

## Repository layout

| Folder | Contents |
|---|---|
| `boards/` | hardware files, one per board |
| `profiles/` | sizes and fonts per screen resolution |
| `core/` | shared firmware core and system screens |
| `faces/` | screens for each Home Assistant entity type |
| `themes/`, `i18n/`, `icons/` | colors, translations, icon packs |
| `devices/` | example device configurations |
| `tools/` | build and check scripts |
| `website/` | user guide and blog |

## License

[MIT](LICENSE)
