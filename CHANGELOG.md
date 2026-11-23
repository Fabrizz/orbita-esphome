# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/), counted against device files:

- **Major:** existing device files need changes (renamed substitutions, package paths or
  face variables).
- **Minor:** new faces, boards or features; existing device files keep working.
- **Patch:** fixes.

Before 1.0.0, a minor release may also break device files; its notes say how to update.

## [Unreleased]

### Added

- PC simulator boards (`host-sdl-r480`, `host-sdl-r240`) with a round mask, mouse as touch and
  keyboard as knob.
- Size profiles `r480` and `r240`, the `dark` theme and shared styles.
- `knob_shell` component and a placeholder start screen.
- Example devices for the simulator and for use from GitHub (`devices/example-remote.yaml`).
- Docker development environment and CI.
- Connection gate: the shell follows the Home Assistant connection (connecting, syncing,
  ready, lost) and shows the connection screen until Home Assistant is ready. Screens register
  their LVGL page with the shell (`knob_shell: screens:`); only the shell switches pages.
  `on_connection_change` runs actions with the new stage. Profiles gain `safe_w`.
- Connection screen details: the device's name and address while waiting for Home Assistant,
  "n of m entities" while syncing (faces add checks with `add_sync_check()`; the shell reports
  `sync_done()` / `sync_total()` and runs `on_sync_progress`), and since when it has been
  retrying after the connection was lost.
- Boot screen: the Orbita mark (animated intro that follows the motion setting), the Orbita
  version and a credit line (`boot_credit`). Shown for 5 s after power-on.
- Home Assistant's device info shows the firmware project `fabrizz.orbita` and the Orbita
  version (`esphome: project:` in `core/version.yaml`).
- `orbita_fonts`: where the fonts in `fonts/` come from (GitHub release by default, `../fonts`
  in a checkout).
- `tools/sim_smoke.py --fake-ha`: plays Home Assistant against a simulator device and checks
  the connection gate (used in CI).
- Icons by semantic name (`${ic_<name>}`) with a Material Design Icons pack (`icons/mdi.yaml`),
  compiled at the profile's icon sizes (`f_ic_s`, `f_ic_m`, `f_ic_l`). Device files include an
  icon pack next to the theme.
- Brand font (`fonts/orbita-brand.ttf`) built from `brand/`: the logo's sections and the author icon,
  with a package of named glyph substitutions (`fonts/orbita-brand.yaml`).
