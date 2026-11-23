#include "shell_types.h"

namespace esphome::knob_shell {

const char *to_str(Connection value) {
  switch (value) {
    case Connection::BOOTING:
      return "BOOTING";
    case Connection::CONNECTING:
      return "CONNECTING";
    case Connection::SYNCING:
      return "SYNCING";
    case Connection::READY:
      return "READY";
    case Connection::LOST:
      return "LOST";
  }
  return "?";
}

const char *to_str(Attention value) {
  switch (value) {
    case Attention::ACTIVE:
      return "ACTIVE";
    case Attention::NEAR:
      return "NEAR";
    case Attention::FAR:
      return "FAR";
    case Attention::AWAY:
      return "AWAY";
    case Attention::IDLE:
      return "IDLE";
    case Attention::SLEEP:
      return "SLEEP";
  }
  return "?";
}

const char *to_str(Overlay value) {
  switch (value) {
    case Overlay::NONE:
      return "NONE";
    case Overlay::LOCK:
      return "LOCK";
    case Overlay::NOTIFY:
      return "NOTIFY";
    case Overlay::CONNECTION:
      return "CONNECTION";
  }
  return "?";
}

const char *to_str(View value) {
  switch (value) {
    case View::CURRENT_APP:
      return "CURRENT_APP";
    case View::HOME:
      return "HOME";
    case View::GLANCE:
      return "GLANCE";
    case View::SCREENSAVER:
      return "SCREENSAVER";
    case View::OFF:
      return "OFF";
  }
  return "?";
}

const char *to_str(Motion value) {
  switch (value) {
    case Motion::FULL:
      return "FULL";
    case Motion::REDUCED:
      return "REDUCED";
    case Motion::OFF:
      return "OFF";
  }
  return "?";
}

const char *to_str(KnobMode value) {
  switch (value) {
    case KnobMode::DIRECT:
      return "DIRECT";
    case KnobMode::CROWN:
      return "CROWN";
  }
  return "?";
}

const char *to_str(Screen value) {
  switch (value) {
    case Screen::BOOT:
      return "BOOT";
    case Screen::SETUP_WIZARD:
      return "SETUP_WIZARD";
    case Screen::CONNECTION:
      return "CONNECTION";
    case Screen::OTA:
      return "OTA";
    case Screen::FACTORY_RESET:
      return "FACTORY_RESET";
    case Screen::SCREENSAVER:
      return "SCREENSAVER";
    case Screen::HOME:
      return "HOME";
    case Screen::INFO:
      return "INFO";
    case Screen::GLOBAL_CONTROLS:
      return "GLOBAL_CONTROLS";
    case Screen::HUB:
      return "HUB";
    case Screen::APP:
      return "APP";
  }
  return "?";
}

}  // namespace esphome::knob_shell
