#pragma once

#include "esphome/core/component.h"
#include "shell_types.h"

namespace esphome::knob_shell {

// Owner of all UI state: connection gate, attention level, overlays and the
// screen on display. Boards push raw input in; faces and services register
// with it. This version only holds the state and logs incoming input.
class KnobShell : public Component {
 public:
  void setup() override;
  void dump_config() override;

  // Raw input, pushed by the board file.
  void knob_delta(int steps);
  void knob_button(bool pressed);

  // Board capabilities.
  void set_has_knob(bool has_knob) { this->has_knob_ = has_knob; }
  void set_has_touch(bool has_touch) { this->has_touch_ = has_touch; }
  void set_motion_default(Motion motion) { this->motion_default_ = motion; }

  Connection get_connection() const { return this->connection_; }
  Attention get_attention() const { return this->attention_; }
  Overlay get_overlay() const { return this->overlay_; }
  Screen get_screen() const { return this->screen_; }
  Motion get_motion() const { return this->motion_; }
  KnobMode get_knob_mode() const { return this->knob_mode_; }
  bool is_locked() const { return this->locked_; }

 protected:
  bool has_knob_{false};
  bool has_touch_{false};
  Motion motion_default_{Motion::FULL};

  Connection connection_{Connection::BOOTING};
  Attention attention_{Attention::ACTIVE};
  Overlay overlay_{Overlay::NONE};
  Screen screen_{Screen::BOOT};
  Motion motion_{Motion::FULL};
  KnobMode knob_mode_{KnobMode::DIRECT};
  bool locked_{false};
};

}  // namespace esphome::knob_shell
