#pragma once

#include <cstddef>
#include <cstdint>

namespace esphome::knob_shell {

// Home Assistant connection stage, owned by the shell.
enum class Connection : uint8_t { BOOTING, CONNECTING, SYNCING, READY, LOST };

// Attention level. ACTIVE/NEAR/FAR/AWAY come from a presence service,
// ACTIVE/IDLE/SLEEP from inactivity timers when there is none.
enum class Attention : uint8_t { ACTIVE, NEAR, FAR, AWAY, IDLE, SLEEP };

// Overlay drawn above the current view.
enum class Overlay : uint8_t { NONE, LOCK, NOTIFY, CONNECTION };

// What the policy table shows for an attention level.
enum class View : uint8_t { CURRENT_APP, HOME, GLANCE, SCREENSAVER, OFF };

// Animation budget: min(board default, level policy, user setting).
enum class Motion : uint8_t { FULL, REDUCED, OFF };

// How knob turns are interpreted.
enum class KnobMode : uint8_t { DIRECT, CROWN };

// Screens owned by the shell. App faces are identified by their face id.
enum class Screen : uint8_t {
  BOOT,
  SETUP_WIZARD,
  CONNECTION,
  OTA,
  FACTORY_RESET,
  SCREENSAVER,
  HOME,
  INFO,
  GLOBAL_CONTROLS,
  HUB,
  APP,
};

constexpr size_t SCREEN_COUNT = static_cast<size_t>(Screen::APP) + 1;

// Kinds of items on the strip, left to right:
// [notifications] [active cards...] [HOME] [apps...] [INFO]
enum class StripKind : uint8_t { NOTIFICATIONS, CARD, HOME, APP, INFO };

const char *to_str(Connection value);
const char *to_str(Attention value);
const char *to_str(Overlay value);
const char *to_str(View value);
const char *to_str(Motion value);
const char *to_str(KnobMode value);
const char *to_str(Screen value);

}  // namespace esphome::knob_shell
