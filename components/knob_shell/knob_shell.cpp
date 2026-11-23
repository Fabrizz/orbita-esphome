#include "knob_shell.h"

#include <cmath>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#ifdef USE_API
#include "esphome/components/api/api_server.h"
#endif
#ifdef USE_NETWORK
#include "esphome/components/network/util.h"
#endif

namespace esphome::knob_shell {

static const char *const TAG = "knob_shell";

// A knob press held longer than this is a long press (handled later).
static const uint32_t LONG_PRESS_MS = 600;
// Position dots: visible this long after the last move, then fade out.
static const uint32_t NAV_VISIBLE_MS = 1500;
static const uint32_t NAV_FADE_MS = 400;
// At most this many dots; with more items the window follows the position.
static const int NAV_MAX_DOTS = 7;
// Strip transitions.
static const uint32_t SLIDE_MS = 300;
static const uint32_t FADE_MS = 200;

std::string device_address() {
#ifdef USE_NETWORK
#ifndef USE_HOST
  // (The host build's IPAddress has no is_set()/is_ip4(), and no address.)
  for (auto &ip : network::get_ip_addresses()) {
    if (ip.is_set() && ip.is_ip4()) {
      char buf[network::IP_ADDRESS_BUFFER_SIZE];
      return ip.str_to(buf);
    }
  }
#endif
  char name[network::USE_ADDRESS_BUFFER_SIZE];
  return network::get_use_address_to(name);
#else
  return "";
#endif
}

void KnobShell::setup() {
  this->motion_ = this->motion_default_;
  this->boot_start_ = millis();
  // Without a boot screen there is nothing to wait for.
  this->boot_done_ = !this->has_screen_(Screen::BOOT);
  this->build_strip_();
  this->build_nav_();
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
                to_str(this->attention_), this->view_str().c_str());
  for (size_t i = 0; i < SCREEN_COUNT; i++) {
    const Face &face = this->screens_[i];
    if (face.page != nullptr) {
      ESP_LOGCONFIG(TAG, "  Screen %s: page %u%s", to_str(static_cast<Screen>(i)), (unsigned) face.page->index,
                    face.requires_ha ? ", requires Home Assistant" : "");
    }
  }
  std::string strip;
  for (const auto &item : this->strip_)
    strip += (strip.empty() ? "" : " ") + this->view_str_({item.kind == StripKind::HOME   ? Screen::HOME
                                                           : item.kind == StripKind::INFO ? Screen::INFO
                                                                                          : Screen::APP,
                                                           item.app});
  ESP_LOGCONFIG(TAG, "  Strip: %s", strip.c_str());
}

void KnobShell::set_nav(int radius, int dot, float step_deg, uint32_t color, uint32_t current_color,
                        uint32_t home_color) {
  this->nav_radius_ = radius;
  this->nav_dot_ = dot;
  this->nav_step_deg_ = step_deg;
  this->nav_color_ = color;
  this->nav_current_color_ = current_color;
  this->nav_home_color_ = home_color;
}

void KnobShell::add_screen(Screen screen, lvgl::LvPageType *page, bool requires_ha) {
  Face &face = this->screen_(screen);
  face.page = page;
  face.requires_ha = requires_ha;
}

int KnobShell::add_app(const char *id, lvgl::LvPageType *page, bool requires_ha) {
  App app;
  app.id = id;
  app.face.page = page;
  app.face.requires_ha = requires_ha;
  this->apps_.push_back(std::move(app));
  return static_cast<int>(this->apps_.size()) - 1;
}

const char *KnobShell::app_id() const {
  if (this->view_.screen != Screen::APP || this->view_.app < 0)
    return "";
  return this->apps_[this->view_.app].id.c_str();
}

KnobShell::Face *KnobShell::face_(const View &view) {
  if (view.screen == Screen::APP)
    return view.app >= 0 && view.app < (int) this->apps_.size() ? &this->apps_[view.app].face : nullptr;
  return &this->screen_(view.screen);
}

std::string KnobShell::view_str_(const View &view) const {
  if (view.screen == Screen::APP && view.app >= 0 && view.app < (int) this->apps_.size())
    return "APP(" + this->apps_[view.app].id + ")";
  return to_str(view.screen);
}

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

size_t KnobShell::sync_done() const {
  size_t done = 0;
  for (const auto &check : this->sync_checks_) {
    if (check())
      done++;
  }
  return done;
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
        this->last_sync_done_ = SIZE_MAX;
        this->set_connection_(Connection::SYNCING);
      }
      break;
    case Connection::SYNCING: {
      if (!ha) {
        this->set_connection_(this->was_ready_ ? Connection::LOST : Connection::CONNECTING);
        break;
      }
      const size_t done = this->sync_done();
      if (done != this->last_sync_done_) {
        this->last_sync_done_ = done;
        ESP_LOGD(TAG, "Sync: %u of %u", (unsigned) done, (unsigned) this->sync_total());
        for (auto *trigger : this->sync_progress_triggers_)
          trigger->trigger();
      }
      if (done == this->sync_total()) {
        this->set_connection_(Connection::READY);
      } else if (millis() - this->sync_start_ >= this->sync_timeout_) {
        ESP_LOGW(TAG, "Sync timed out after %" PRIu32 " ms; faces still waiting show unavailable",
                 this->sync_timeout_);
        this->set_connection_(Connection::READY);
      }
      break;
    }
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

KnobShell::View KnobShell::strip_view_() const {
  if (this->strip_.empty())
    return {Screen::HOME, -1};
  const StripItem &item = this->strip_[this->strip_pos_];
  switch (item.kind) {
    case StripKind::APP:
      return {Screen::APP, item.app};
    case StripKind::INFO:
      return {Screen::INFO, -1};
    default:
      return {Screen::HOME, -1};
  }
}

bool KnobShell::is_strip_view_(const View &view) const {
  return view.screen == Screen::HOME || view.screen == Screen::INFO || view.screen == Screen::APP;
}

KnobShell::View KnobShell::decide_() const {
  if (!this->boot_done_)
    return {Screen::BOOT, -1};
  // For now the connection screen covers the whole strip until Home
  // Assistant is ready, even for faces that work without it. Offline faces
  // (`requires_ha: false`) get their own behavior later.
  if (this->connection_ != Connection::READY && this->has_screen_(Screen::CONNECTION))
    return {Screen::CONNECTION, -1};
  return this->strip_view_();
}

void KnobShell::arbitrate_() { this->show_(this->decide_()); }

void KnobShell::show_(const View &view, lv_screen_load_anim_t anim, uint32_t time) {
  if (this->shown_ && view == this->view_)
    return;
  Face *next = this->face_(view);
  if (next == nullptr || next->page == nullptr) {
    ESP_LOGW(TAG, "No page registered for %s", this->view_str_(view).c_str());
    return;
  }
  if (this->shown_) {
    if (Face *previous = this->face_(this->view_)) {
      for (auto *trigger : previous->on_exit)
        trigger->trigger();
    }
    ESP_LOGI(TAG, "Screen: %s -> %s", this->view_str().c_str(), this->view_str_(view).c_str());
  } else {
    ESP_LOGI(TAG, "Screen: %s", this->view_str_(view).c_str());
  }
  this->view_ = view;
  this->shown_ = true;
  if (!this->is_strip_view_(view))
    this->hide_nav_();
  next->page->get_parent()->show_page(next->page->index, anim, time);
  for (auto *trigger : next->on_enter)
    trigger->trigger();
  for (auto *trigger : this->screen_triggers_)
    trigger->trigger();
}

// --- Strip ------------------------------------------------------------------

void KnobShell::build_strip_() {
  // Left of HOME: notifications and active cards (none registered yet).
  this->strip_.clear();
  if (this->has_screen_(Screen::HOME))
    this->strip_.push_back({StripKind::HOME, -1});
  for (int i = 0; i < (int) this->apps_.size(); i++)
    this->strip_.push_back({StripKind::APP, i});
  if (this->has_screen_(Screen::INFO))
    this->strip_.push_back({StripKind::INFO, -1});

  this->strip_pos_ = 0;
  for (size_t i = 0; i < this->strip_.size(); i++) {
    if (this->strip_[i].kind == StripKind::HOME)
      this->strip_pos_ = i;
  }

  // Swipes on any strip page move along the strip.
  if (!this->has_touch_)
    return;
  for (const auto &item : this->strip_) {
    View view = item.kind == StripKind::APP    ? View{Screen::APP, item.app}
                : item.kind == StripKind::INFO ? View{Screen::INFO, -1}
                                               : View{Screen::HOME, -1};
    Face *face = this->face_(view);
    if (face != nullptr && face->page != nullptr)
      lv_obj_add_event_cb(face->page->obj, KnobShell::on_gesture_, LV_EVENT_GESTURE, this);
  }
}

void KnobShell::on_gesture_(lv_event_t *event) {
  auto *shell = static_cast<KnobShell *>(lv_event_get_user_data(event));
  lv_dir_t dir = lv_indev_get_gesture_dir(lv_indev_active());
  // The content follows the finger: swiping left brings in the item on the right.
  if (dir == LV_DIR_LEFT) {
    shell->strip_move(1);
  } else if (dir == LV_DIR_RIGHT) {
    shell->strip_move(-1);
  }
}

bool KnobShell::strip_move(int direction) {
  if (!this->shown_ || !this->is_strip_view_(this->view_) || this->strip_.empty())
    return false;
  const int next = static_cast<int>(this->strip_pos_) + (direction > 0 ? 1 : -1);
  if (next < 0 || next >= (int) this->strip_.size()) {
    this->show_nav_();  // show where we are, even at the end
    return false;
  }
  this->strip_pos_ = next;
  lv_screen_load_anim_t anim = LV_SCREEN_LOAD_ANIM_NONE;
  uint32_t time = 0;
  if (this->motion_ == Motion::FULL) {
    anim = direction > 0 ? LV_SCREEN_LOAD_ANIM_MOVE_LEFT : LV_SCREEN_LOAD_ANIM_MOVE_RIGHT;
    time = SLIDE_MS;
  } else if (this->motion_ == Motion::REDUCED) {
    anim = LV_SCREEN_LOAD_ANIM_FADE_IN;
    time = FADE_MS;
  }
  this->show_(this->strip_view_(), anim, time);
  this->show_nav_();
  return true;
}

// --- Position dots ----------------------------------------------------------

static void nav_set_opa(void *obj, int32_t value) {
  lv_obj_set_style_opa(static_cast<lv_obj_t *>(obj), static_cast<lv_opa_t>(value), 0);
}

static void nav_faded(lv_anim_t *anim) { lv_obj_add_flag(static_cast<lv_obj_t *>(anim->var), LV_OBJ_FLAG_HIDDEN); }

static lv_obj_t *plain_obj(lv_obj_t *parent) {
  lv_obj_t *obj = lv_obj_create(parent);
  lv_obj_remove_style_all(obj);
  lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
  return obj;
}

void KnobShell::build_nav_() {
  if (this->strip_.size() < 2 || this->nav_dot_ <= 0)
    return;
  // On the top layer, so the dots stay put while pages slide underneath.
  this->nav_ = plain_obj(lv_layer_top());
  lv_obj_set_size(this->nav_, lv_pct(100), lv_pct(100));
  lv_obj_add_flag(this->nav_, LV_OBJ_FLAG_HIDDEN);
  const int count = std::min<int>(this->strip_.size(), NAV_MAX_DOTS);
  for (int i = 0; i < count; i++) {
    lv_obj_t *dot = plain_obj(this->nav_);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    this->nav_dots_.push_back(dot);
  }
}

void KnobShell::update_nav_() {
  if (this->nav_ == nullptr)
    return;
  const int items = this->strip_.size();
  const int count = this->nav_dots_.size();
  // Window of items shown as dots, following the position.
  int first = 0;
  if (items > count)
    first = std::max(0, std::min<int>(this->strip_pos_ - count / 2, items - count));
  const int cx = lv_obj_get_width(lv_layer_top()) / 2;
  const int cy = lv_obj_get_height(lv_layer_top()) / 2;
  for (int i = 0; i < count; i++) {
    const int item = first + i;
    const bool current = item == (int) this->strip_pos_;
    const bool more_beyond = (i == 0 && first > 0) || (i == count - 1 && item < items - 1);
    int size = this->nav_dot_;
    if (current) {
      size = this->nav_dot_ * 8 / 5;
    } else if (more_beyond) {
      size = std::max(2, this->nav_dot_ * 3 / 5);
    }
    uint32_t color = this->nav_color_;
    if (current) {
      color = this->nav_current_color_;
    } else if (this->strip_[item].kind == StripKind::HOME) {
      color = this->nav_home_color_;
    }
    // On an arc around the center, 0 degrees = straight down, left to right.
    const float angle = (i - (count - 1) / 2.0f) * this->nav_step_deg_ * static_cast<float>(M_PI) / 180.0f;
    const int x = cx + static_cast<int>(lroundf(this->nav_radius_ * sinf(angle)));
    const int y = cy + static_cast<int>(lroundf(this->nav_radius_ * cosf(angle)));
    lv_obj_t *dot = this->nav_dots_[i];
    lv_obj_set_size(dot, size, size);
    lv_obj_set_pos(dot, x - size / 2, y - size / 2);
    lv_obj_set_style_bg_color(dot, lv_color_hex(color), 0);
  }
}

void KnobShell::show_nav_() {
  if (this->nav_ == nullptr)
    return;
  this->update_nav_();
  lv_anim_delete(this->nav_, nav_set_opa);
  lv_obj_set_style_opa(this->nav_, LV_OPA_COVER, 0);
  lv_obj_remove_flag(this->nav_, LV_OBJ_FLAG_HIDDEN);
  this->set_timeout("nav_hide", NAV_VISIBLE_MS, [this]() {
    if (this->motion_ == Motion::OFF) {
      lv_obj_add_flag(this->nav_, LV_OBJ_FLAG_HIDDEN);
      return;
    }
    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, this->nav_);
    lv_anim_set_values(&anim, LV_OPA_COVER, LV_OPA_TRANSP);
    lv_anim_set_duration(&anim, NAV_FADE_MS);
    lv_anim_set_exec_cb(&anim, nav_set_opa);
    lv_anim_set_completed_cb(&anim, nav_faded);
    lv_anim_start(&anim);
  });
}

void KnobShell::hide_nav_() {
  if (this->nav_ == nullptr)
    return;
  this->cancel_timeout("nav_hide");
  lv_anim_delete(this->nav_, nav_set_opa);
  lv_obj_add_flag(this->nav_, LV_OBJ_FLAG_HIDDEN);
}

// --- Input ------------------------------------------------------------------

void KnobShell::knob_delta(int steps) {
  if (!this->has_knob_ || steps == 0)
    return;
  ESP_LOGD(TAG, "Knob delta %+d (%s)", steps, this->view_str().c_str());
  // No face has a value to adjust yet: turning moves along the strip.
  const int direction = steps > 0 ? 1 : -1;
  for (int i = 0; i < std::abs(steps); i++) {
    if (!this->strip_move(direction))
      break;
  }
}

void KnobShell::knob_button(bool pressed) {
  if (!this->has_knob_)
    return;
  if (pressed) {
    this->button_down_ = millis();
    this->button_held_ = true;
    return;
  }
  if (!this->button_held_)
    return;
  this->button_held_ = false;
  const uint32_t held = millis() - this->button_down_;
  if (held >= LONG_PRESS_MS) {
    ESP_LOGD(TAG, "Long press (%s): nothing yet", this->view_str().c_str());
    return;
  }
  ESP_LOGD(TAG, "Press (%s)", this->view_str().c_str());
  if (Face *face = this->face_(this->view_)) {
    for (auto *trigger : face->on_press)
      trigger->trigger();
  }
}

}  // namespace esphome::knob_shell
