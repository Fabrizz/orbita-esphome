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
  (`pip install -r requirements.txt`)
- For the simulator: Linux or macOS with SDL2 development libraries (Windows via WSL2)

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
