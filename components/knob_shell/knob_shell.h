#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "esphome/components/lvgl/lvgl_esphome.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "shell_types.h"

namespace esphome::knob_shell {

// The address to reach this device by: its IPv4 address, or <name>.local
// where it has none of its own (the PC simulator).
std::string device_address();

// Owner of all UI state: connection gate, the strip, attention level,
// overlays and the screen on display. Boards push raw input in; screens and
// app faces register their LVGL page with the shell, and only the shell
// switches pages.
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

  // Position dots along the bottom curve (profile and theme tokens).
  void set_nav(int radius, int dot, float step_deg, uint32_t color, uint32_t current_color, uint32_t home_color);

  // System screens, registered from the YAML `screens:` map.
  void add_screen(Screen screen, lvgl::LvPageType *page, bool requires_ha);
  void add_enter_trigger(Screen screen, Trigger<> *trigger) { this->screen_(screen).on_enter.push_back(trigger); }
  void add_exit_trigger(Screen screen, Trigger<> *trigger) { this->screen_(screen).on_exit.push_back(trigger); }

  // App faces, registered from the YAML `apps:` map, in strip order. Returns
  // the app's index.
  int add_app(const char *id, lvgl::LvPageType *page, bool requires_ha);
  void add_app_enter_trigger(int app, Trigger<> *trigger) { this->apps_[app].face.on_enter.push_back(trigger); }
  void add_app_exit_trigger(int app, Trigger<> *trigger) { this->apps_[app].face.on_exit.push_back(trigger); }
  void add_app_press_trigger(int app, Trigger<> *trigger) { this->apps_[app].face.on_press.push_back(trigger); }

  // Fired on every connection change, with the new stage.
  void add_connection_trigger(Trigger<Connection> *trigger) { this->connection_triggers_.push_back(trigger); }
  // Fired whenever another screen or app is shown.
  void add_screen_trigger(Trigger<> *trigger) { this->screen_triggers_.push_back(trigger); }

  // SYNCING ends when every check returns true (or after the sync timeout).
  // Faces add a check that their entities have delivered a first state.
  void add_sync_check(std::function<bool()> check) { this->sync_checks_.push_back(std::move(check)); }
  // Fired while SYNCING whenever the number of passed checks changes.
  void add_sync_progress_trigger(Trigger<> *trigger) { this->sync_progress_triggers_.push_back(trigger); }
  size_t sync_total() const { return this->sync_checks_.size(); }
  size_t sync_done() const;

  // Move along the strip by one item (+1 = right, -1 = left). Does nothing
  // unless a strip item is showing. Returns whether it moved.
  bool strip_move(int direction);

  Connection get_connection() const { return this->connection_; }
  Attention get_attention() const { return this->attention_; }
  Overlay get_overlay() const { return this->overlay_; }
  Screen get_screen() const { return this->view_.screen; }
  Motion get_motion() const { return this->motion_; }
  KnobMode get_knob_mode() const { return this->knob_mode_; }
  bool is_locked() const { return this->locked_; }
  const char *connection_str() const { return to_str(this->connection_); }
  const char *screen_str() const { return to_str(this->view_.screen); }
  // Face id of the app showing, or "" when no app is showing.
  const char *app_id() const;
  // What is showing, for logs and file names: "HOME", "APP(lamp)"...
  std::string view_str() const { return this->view_str_(this->view_); }

 protected:
  struct Face {
    lvgl::LvPageType *page{nullptr};
    bool requires_ha{false};
    std::vector<Trigger<> *> on_enter;
    std::vector<Trigger<> *> on_exit;
    std::vector<Trigger<> *> on_press;
  };
  struct App {
    std::string id;
    Face face;
  };
  // A screen, or app `app` when screen == Screen::APP.
  struct View {
    Screen screen{Screen::BOOT};
    int app{-1};
    bool operator==(const View &other) const { return this->screen == other.screen && this->app == other.app; }
    bool operator!=(const View &other) const { return !(*this == other); }
  };
  struct StripItem {
    StripKind kind;
    int app{-1};
  };

  Face &screen_(Screen screen) { return this->screens_[static_cast<size_t>(screen)]; }
  const Face &screen_(Screen screen) const { return this->screens_[static_cast<size_t>(screen)]; }
  bool has_screen_(Screen screen) const { return this->screen_(screen).page != nullptr; }
  Face *face_(const View &view);
  std::string view_str_(const View &view) const;

  // Connection gate.
  bool ha_connected_() const;
  void update_connection_();
  void set_connection_(Connection connection);

  // Arbiter.
  View strip_view_() const;
  bool is_strip_view_(const View &view) const;
  View decide_() const;
  void arbitrate_();
  void show_(const View &view, lv_screen_load_anim_t anim = LV_SCREEN_LOAD_ANIM_NONE, uint32_t time = 0);

  // Strip and position dots.
  void build_strip_();
  void build_nav_();
  void update_nav_();
  void show_nav_();
  void hide_nav_();
  static void on_gesture_(lv_event_t *event);

  bool has_knob_{false};
  bool has_touch_{false};
  Motion motion_default_{Motion::FULL};

  uint32_t boot_min_time_{1000};
  uint32_t sync_timeout_{10000};
  uint32_t boot_start_{0};
  uint32_t sync_start_{0};
  bool boot_done_{false};
  bool was_ready_{false};
  bool shown_{false};

  std::array<Face, SCREEN_COUNT> screens_{};
  std::vector<App> apps_;
  std::vector<StripItem> strip_;
  size_t strip_pos_{0};
  View view_{};

  std::vector<Trigger<Connection> *> connection_triggers_;
  std::vector<Trigger<> *> screen_triggers_;
  std::vector<std::function<bool()>> sync_checks_;
  std::vector<Trigger<> *> sync_progress_triggers_;
  size_t last_sync_done_{SIZE_MAX};

  // Knob button: when it went down, to tell a press from a long press.
  uint32_t button_down_{0};
  bool button_held_{false};

  // Position dots.
  int nav_radius_{0};
  int nav_dot_{0};
  float nav_step_deg_{0};
  uint32_t nav_color_{0};
  uint32_t nav_current_color_{0};
  uint32_t nav_home_color_{0};
  lv_obj_t *nav_{nullptr};
  std::vector<lv_obj_t *> nav_dots_;

  Connection connection_{Connection::BOOTING};
  Attention attention_{Attention::ACTIVE};
  Overlay overlay_{Overlay::NONE};
  Motion motion_{Motion::FULL};
  KnobMode knob_mode_{KnobMode::DIRECT};
  bool locked_{false};
};

}  // namespace esphome::knob_shell
