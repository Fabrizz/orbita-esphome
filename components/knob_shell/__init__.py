"""knob_shell: owner of the UI state of an Orbita device."""

from esphome import automation
import esphome.codegen as cg
from esphome.components.lvgl.types import lv_page_t
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_TRIGGER_ID

DEPENDENCIES = ["lvgl"]

CONF_HAS_KNOB = "has_knob"
CONF_HAS_TOUCH = "has_touch"
CONF_MOTION_DEFAULT = "motion_default"
CONF_BOOT_MIN_TIME = "boot_min_time"
CONF_SYNC_TIMEOUT = "sync_timeout"
CONF_SCREENS = "screens"
CONF_PAGE = "page"
CONF_REQUIRES_HA = "requires_ha"
CONF_ON_ENTER = "on_enter"
CONF_ON_EXIT = "on_exit"
CONF_ON_CONNECTION_CHANGE = "on_connection_change"

knob_shell_ns = cg.esphome_ns.namespace("knob_shell")
KnobShell = knob_shell_ns.class_("KnobShell", cg.Component)
Motion = knob_shell_ns.enum("Motion", is_class=True)
Connection = knob_shell_ns.enum("Connection", is_class=True)
Screen = knob_shell_ns.enum("Screen", is_class=True)

MOTIONS = {
    "full": Motion.FULL,
    "reduced": Motion.REDUCED,
    "off": Motion.OFF,
}

# Screens the shell can show, by name. App faces are added through the strip,
# not here.
SCREENS = {
    "boot": Screen.BOOT,
    "setup_wizard": Screen.SETUP_WIZARD,
    "connection": Screen.CONNECTION,
    "ota": Screen.OTA,
    "factory_reset": Screen.FACTORY_RESET,
    "screensaver": Screen.SCREENSAVER,
    "home": Screen.HOME,
    "info": Screen.INFO,
    "global_controls": Screen.GLOBAL_CONTROLS,
    "hub": Screen.HUB,
}


def _motion(value):
    # Unquoted `off` is parsed by YAML as boolean false.
    if value is False:
        value = "off"
    return cv.enum(MOTIONS, lower=True)(value)


def _trigger_schema(*arg_types):
    return automation.validate_automation(
        {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(automation.Trigger.template(*arg_types))}
    )


SCREEN_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_PAGE): cv.use_id(lv_page_t),
        cv.Optional(CONF_REQUIRES_HA, default=False): cv.boolean,
        cv.Optional(CONF_ON_ENTER): _trigger_schema(),
        cv.Optional(CONF_ON_EXIT): _trigger_schema(),
    }
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(KnobShell),
        cv.Required(CONF_HAS_KNOB): cv.boolean,
        cv.Required(CONF_HAS_TOUCH): cv.boolean,
        cv.Optional(CONF_MOTION_DEFAULT, default="full"): _motion,
        cv.Optional(CONF_BOOT_MIN_TIME, default="1s"): cv.positive_time_period_milliseconds,
        cv.Optional(CONF_SYNC_TIMEOUT, default="10s"): cv.positive_time_period_milliseconds,
        # Each system face package adds its own entry; packages merge the map.
        cv.Optional(CONF_SCREENS, default={}): cv.Schema(
            {cv.Optional(name): SCREEN_SCHEMA for name in SCREENS}
        ),
        # Actions get the new stage as `stage` (knob_shell::Connection).
        cv.Optional(CONF_ON_CONNECTION_CHANGE): _trigger_schema(Connection),
    }
).extend(cv.COMPONENT_SCHEMA)


async def _add_triggers(var, adder, confs, *args, trigger_args=()):
    for conf in confs:
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID])
        await automation.build_automation(trigger, list(trigger_args), conf)
        cg.add(getattr(var, adder)(*args, trigger))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_has_knob(config[CONF_HAS_KNOB]))
    cg.add(var.set_has_touch(config[CONF_HAS_TOUCH]))
    cg.add(var.set_motion_default(config[CONF_MOTION_DEFAULT]))
    cg.add(var.set_boot_min_time(config[CONF_BOOT_MIN_TIME]))
    cg.add(var.set_sync_timeout(config[CONF_SYNC_TIMEOUT]))

    for name, conf in config[CONF_SCREENS].items():
        screen = SCREENS[name]
        page = await cg.get_variable(conf[CONF_PAGE])
        cg.add(var.add_screen(screen, page, conf[CONF_REQUIRES_HA]))
        await _add_triggers(var, "add_enter_trigger", conf.get(CONF_ON_ENTER, []), screen)
        await _add_triggers(var, "add_exit_trigger", conf.get(CONF_ON_EXIT, []), screen)

    await _add_triggers(
        var,
        "add_connection_trigger",
        config.get(CONF_ON_CONNECTION_CHANGE, []),
        trigger_args=[(Connection, "stage")],
    )
