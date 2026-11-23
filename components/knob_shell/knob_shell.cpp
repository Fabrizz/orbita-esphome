#include "knob_shell.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#ifdef USE_API
#include "esphome/components/api/api_server.h"
#endif

namespace esphome::knob_shell {

static const char *const TAG = "knob_shell";

void KnobShell::setup() {
  this->motion_ = this->motion_default_;
  this->boot_start_ = millis();
  // Without a boot screen there is nothing to wait for.
  this->boot_done_ = !this->has_screen_(Screen::BOOT);
  this->set_connection_(Connection::CONNECTING);
  this->arbitrate_();
}

void KnobShell::loop() {
  if (!this->boot_done_ && millis() - this->boot_start_ >= this->boot_min_time_) {
    this->boot_done_ = true;
    this->arbitrate_();
  }
  this->update_connection_();
}

void KnobShell::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Knob shell:\n"
                "  Knob: %s\n"
                "  Touch: %s\n"
                "  Motion default: %s\n"
                "  Knob mode: %s\n"
                "  Boot min time: %" PRIu32 " ms\n"
                "  Sync timeout: %" PRIu32 " ms\n"
                "  Connection: %s\n"
                "  Attention: %s\n"
                "  Screen: %s",
                YESNO(this->has_knob_), YESNO(this->has_touch_), to_str(this->motion_default_),
                to_str(this->knob_mode_), this->boot_min_time_, this->sync_timeout_, to_str(this->connection_),
                to_str(this->attention_), to_str(this->screen_));
  for (size_t i = 0; i < SCREEN_COUNT; i++) {
    const ScreenSlot &slot = this->screens_[i];
    if (slot.page != nullptr) {
      ESP_LOGCONFIG(TAG, "  Screen %s: page %u%s", to_str(static_cast<Screen>(i)), (unsigned) slot.page->index,
                    slot.requires_ha ? ", requires Home Assistant" : "");
    }
  }
}

void KnobShell::add_screen(Screen screen, lvgl::LvPageType *page, bool requires_ha) {
  ScreenSlot &slot = this->slot_(screen);
  slot.page = page;
  slot.requires_ha = requires_ha;
}

void KnobShell::add_enter_trigger(Screen screen, Trigger<> *trigger) { this->slot_(screen).on_enter.push_back(trigger); }

void KnobShell::add_exit_trigger(Screen screen, Trigger<> *trigger) { this->slot_(screen).on_exit.push_back(trigger); }

// --- Connection gate --------------------------------------------------------

bool KnobShell::ha_connected_() const {
#ifdef USE_API
  // Home Assistant subscribes to states; a client that only reads logs or
  // device info doesn't count.
  return api::global_api_server != nullptr && api::global_api_server->is_connected_with_state_subscription();
#else
  return false;
#endif
}

bool KnobShell::synced_() const {
  for (const auto &check : this->sync_checks_) {
    if (!check())
      return false;
  }
  return true;
}

void KnobShell::update_connection_() {
  const bool ha = this->ha_connected_();
  switch (this->connection_) {
    case Connection::BOOTING:
      break;
    case Connection::CONNECTING:
    case Connection::LOST:
      if (ha) {
        this->sync_start_ = millis();
        this->set_connection_(Connection::SYNCING);
      }
      break;
    case Connection::SYNCING:
      if (!ha) {
        this->set_connection_(this->was_ready_ ? Connection::LOST : Connection::CONNECTING);
      } else if (this->synced_()) {
        this->set_connection_(Connection::READY);
      } else if (millis() - this->sync_start_ >= this->sync_timeout_) {
        ESP_LOGW(TAG, "Sync timed out after %" PRIu32 " ms; faces still waiting show unavailable",
                 this->sync_timeout_);
        this->set_connection_(Connection::READY);
      }
      break;
    case Connection::READY:
      if (!ha)
        this->set_connection_(Connection::LOST);
      break;
  }
}

void KnobShell::set_connection_(Connection connection) {
  if (connection == this->connection_)
    return;
  ESP_LOGI(TAG, "Connection: %s -> %s", to_str(this->connection_), to_str(connection));
  this->connection_ = connection;
  if (connection == Connection::READY)
    this->was_ready_ = true;
  for (auto *trigger : this->connection_triggers_)
    trigger->trigger(connection);
  this->arbitrate_();
}

// --- Arbiter ----------------------------------------------------------------

Screen KnobShell::decide_() const {
  if (!this->boot_done_)
    return Screen::BOOT;
  // The rest position. HOME is the only one so far.
  const Screen rest = Screen::HOME;
  if (this->slot_(rest).requires_ha && this->connection_ != Connection::READY && this->has_screen_(Screen::CONNECTION))
    return Screen::CONNECTION;
  return rest;
}

void KnobShell::arbitrate_() { this->show_(this->decide_()); }

void KnobShell::show_(Screen screen) {
  if (this->screen_shown_ && screen == this->screen_)
    return;
  ScreenSlot &next = this->slot_(screen);
  if (next.page == nullptr) {
    ESP_LOGW(TAG, "No page registered for screen %s", to_str(screen));
    return;
  }
  if (this->screen_shown_) {
    for (auto *trigger : this->slot_(this->screen_).on_exit)
      trigger->trigger();
    ESP_LOGI(TAG, "Screen: %s -> %s", to_str(this->screen_), to_str(screen));
  } else {
    ESP_LOGI(TAG, "Screen: %s", to_str(screen));
  }
  this->screen_ = screen;
  this->screen_shown_ = true;
  next.page->get_parent()->show_page(next.page->index, LV_SCREEN_LOAD_ANIM_NONE, 0);
  for (auto *trigger : next.on_enter)
    trigger->trigger();
}

// --- Input ------------------------------------------------------------------

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
