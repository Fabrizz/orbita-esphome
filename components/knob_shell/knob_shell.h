#pragma once

#include <array>
#include <functional>
#include <vector>

#include "esphome/components/lvgl/lvgl_esphome.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "shell_types.h"

namespace esphome::knob_shell {

// Owner of all UI state: connection gate, attention level, overlays and the
// screen on display. Boards push raw input in; screens register their LVGL
// page with the shell, and only the shell switches pages.
class KnobShell : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  // After LVGL (PROCESSOR), so the first decision replaces LVGL's default
  // first page before anything is drawn.
  float get_setup_priority() const override { return setup_priority::PROCESSOR - 10.0f; }

  // Raw input, pushed by the board file.
  void knob_delta(int steps);
  void knob_button(bool pressed);

  // Board capabilities.
  void set_has_knob(bool has_knob) { this->has_knob_ = has_knob; }
  void set_has_touch(bool has_touch) { this->has_touch_ = has_touch; }
  void set_motion_default(Motion motion) { this->motion_default_ = motion; }

  // Timing of the connection gate.
  void set_boot_min_time(uint32_t ms) { this->boot_min_time_ = ms; }
  void set_sync_timeout(uint32_t ms) { this->sync_timeout_ = ms; }

  // Screens, registered from the YAML `screens:` map.
  void add_screen(Screen screen, lvgl::LvPageType *page, bool requires_ha);
  void add_enter_trigger(Screen screen, Trigger<> *trigger);
  void add_exit_trigger(Screen screen, Trigger<> *trigger);
  // Fired on every connection change, with the new stage.
  void add_connection_trigger(Trigger<Connection> *trigger) { this->connection_triggers_.push_back(trigger); }

  // SYNCING ends when every check returns true (or after the sync timeout).
  // Faces add a check that their entities have delivered a first state.
  void add_sync_check(std::function<bool()> check) { this->sync_checks_.push_back(std::move(check)); }

  Connection get_connection() const { return this->connection_; }
  Attention get_attention() const { return this->attention_; }
  Overlay get_overlay() const { return this->overlay_; }
  Screen get_screen() const { return this->screen_; }
  Motion get_motion() const { return this->motion_; }
  KnobMode get_knob_mode() const { return this->knob_mode_; }
  bool is_locked() const { return this->locked_; }
  const char *connection_str() const { return to_str(this->connection_); }
  const char *screen_str() const { return to_str(this->screen_); }

 protected:
  struct ScreenSlot {
    lvgl::LvPageType *page{nullptr};
    bool requires_ha{false};
    std::vector<Trigger<> *> on_enter;
    std::vector<Trigger<> *> on_exit;
  };

  ScreenSlot &slot_(Screen screen) { return this->screens_[static_cast<size_t>(screen)]; }
  const ScreenSlot &slot_(Screen screen) const { return this->screens_[static_cast<size_t>(screen)]; }
  bool has_screen_(Screen screen) const { return this->slot_(screen).page != nullptr; }

  bool ha_connected_() const;
  bool synced_() const;
  void update_connection_();
  void set_connection_(Connection connection);
  Screen decide_() const;
  void arbitrate_();
  void show_(Screen screen);

  bool has_knob_{false};
  bool has_touch_{false};
  Motion motion_default_{Motion::FULL};

  uint32_t boot_min_time_{1000};
  uint32_t sync_timeout_{10000};
  uint32_t boot_start_{0};
  uint32_t sync_start_{0};
  bool boot_done_{false};
  bool was_ready_{false};
  bool screen_shown_{false};

  std::array<ScreenSlot, SCREEN_COUNT> screens_{};
  std::vector<Trigger<Connection> *> connection_triggers_;
  std::vector<std::function<bool()>> sync_checks_;

  Connection connection_{Connection::BOOTING};
  Attention attention_{Attention::ACTIVE};
  Overlay overlay_{Overlay::NONE};
  Screen screen_{Screen::BOOT};
  Motion motion_{Motion::FULL};
  KnobMode knob_mode_{KnobMode::DIRECT};
  bool locked_{false};
};

}  // namespace esphome::knob_shell
