#include "knob_shell.h"

#include "esphome/core/log.h"

namespace esphome::knob_shell {

static const char *const TAG = "knob_shell";

void KnobShell::setup() { this->motion_ = this->motion_default_; }

void KnobShell::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Knob shell:\n"
                "  Knob: %s\n"
                "  Touch: %s\n"
                "  Motion default: %s\n"
                "  Knob mode: %s\n"
                "  Connection: %s\n"
                "  Attention: %s\n"
                "  Screen: %s",
                YESNO(this->has_knob_), YESNO(this->has_touch_), to_str(this->motion_default_),
                to_str(this->knob_mode_), to_str(this->connection_), to_str(this->attention_),
                to_str(this->screen_));
}

void KnobShell::knob_delta(int steps) {
  if (!this->has_knob_ || steps == 0)
    return;
  ESP_LOGD(TAG, "Knob delta %+d (screen %s)", steps, to_str(this->screen_));
}

void KnobShell::knob_button(bool pressed) {
  if (!this->has_knob_)
    return;
  ESP_LOGD(TAG, "Knob button %s (screen %s)", pressed ? "pressed" : "released", to_str(this->screen_));
}

}  // namespace esphome::knob_shell
