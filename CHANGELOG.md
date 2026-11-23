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
- `knob_shell` component (state and input logging only) and a placeholder start screen.
- Example devices for the simulator and for use from GitHub (`devices/example-remote.yaml`).
- Docker development environment and CI.
- Icons by semantic name (`${ic_<name>}`) with a Material Design Icons pack (`icons/mdi.yaml`),
  compiled at the profile's icon sizes (`f_ic_s`, `f_ic_m`, `f_ic_l`). Device files include an
  icon pack next to the theme.
- Logo font (`fonts/orbita-mark.ttf`) built from the logo's sections in `brand/`.
