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
CONF_APPS = "apps"
CONF_PAGE = "page"
CONF_FACE = "face"
CONF_ORDER = "order"
CONF_REQUIRES_HA = "requires_ha"
CONF_ON_ENTER = "on_enter"
CONF_ON_EXIT = "on_exit"
CONF_ON_PRESS = "on_press"
CONF_ON_CONNECTION_CHANGE = "on_connection_change"
CONF_ON_SCREEN_CHANGE = "on_screen_change"
CONF_ON_SYNC_PROGRESS = "on_sync_progress"
CONF_NAV = "nav"
CONF_RADIUS = "radius"
CONF_DOT = "dot"
CONF_STEP = "step"
CONF_COLOR = "color"
CONF_CURRENT_COLOR = "current_color"
CONF_HOME_COLOR = "home_color"

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

# System screens the shell can show, by name. App faces go in `apps:`.
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

# An app face on the strip, right of HOME. Its logic and skin packages each
# add an entry with the same `face` (the face id): the skin brings the page,
# the logic the order and actions. Entries are combined per face here, since
# packages only append to lists.
APP_ENTRY_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_FACE): cv.valid_name,
        cv.Optional(CONF_PAGE): cv.use_id(lv_page_t),
        cv.Optional(CONF_ORDER): cv.int_,
        cv.Optional(CONF_REQUIRES_HA): cv.boolean,
        cv.Optional(CONF_ON_ENTER): _trigger_schema(),
        cv.Optional(CONF_ON_EXIT): _trigger_schema(),
        cv.Optional(CONF_ON_PRESS): _trigger_schema(),
    }
)

_APP_SINGLE = (CONF_PAGE, CONF_ORDER, CONF_REQUIRES_HA)
_APP_TRIGGERS = (CONF_ON_ENTER, CONF_ON_EXIT, CONF_ON_PRESS)


def _combine_apps(entries):
    """Combine the entries of each face into one: {face id: config}."""
    apps = {}
    for entry in entries:
        app = apps.setdefault(entry[CONF_FACE], {key: [] for key in _APP_TRIGGERS})
        for key in _APP_SINGLE:
            if key in entry:
                if key in app:
                    raise cv.Invalid(f"app '{entry[CONF_FACE]}': '{key}' is set twice")
                app[key] = entry[key]
        for key in _APP_TRIGGERS:
            app[key] += entry.get(key, [])
    for face_id, app in apps.items():
        if CONF_PAGE not in app:
            raise cv.Invalid(f"app '{face_id}' has no page (is its skin included?)")
        app.setdefault(CONF_ORDER, 0)
        app.setdefault(CONF_REQUIRES_HA, True)
    return apps

NAV_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_RADIUS): cv.positive_int,
        cv.Required(CONF_DOT): cv.positive_int,
        cv.Required(CONF_STEP): cv.positive_float,
        cv.Required(CONF_COLOR): cv.hex_int,
        cv.Required(CONF_CURRENT_COLOR): cv.hex_int,
        cv.Required(CONF_HOME_COLOR): cv.hex_int,
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
        cv.Optional(CONF_NAV): NAV_SCHEMA,
        # Each system face package adds its own entry; packages merge the map.
        cv.Optional(CONF_SCREENS, default={}): cv.Schema(
            {cv.Optional(name): SCREEN_SCHEMA for name in SCREENS}
        ),
        # App faces, shown in `order` (see APP_ENTRY_SCHEMA).
        cv.Optional(CONF_APPS, default=[]): cv.All(cv.ensure_list(APP_ENTRY_SCHEMA), _combine_apps),
        # Actions get the new stage as `stage` (knob_shell::Connection).
        cv.Optional(CONF_ON_CONNECTION_CHANGE): _trigger_schema(Connection),
        cv.Optional(CONF_ON_SCREEN_CHANGE): _trigger_schema(),
        # While SYNCING, whenever sync_done() changes.
        cv.Optional(CONF_ON_SYNC_PROGRESS): _trigger_schema(),
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

    if nav := config.get(CONF_NAV):
        cg.add(
            var.set_nav(
                nav[CONF_RADIUS],
                nav[CONF_DOT],
                nav[CONF_STEP],
                nav[CONF_COLOR],
                nav[CONF_CURRENT_COLOR],
                nav[CONF_HOME_COLOR],
            )
        )

    for name, conf in config[CONF_SCREENS].items():
        screen = SCREENS[name]
        page = await cg.get_variable(conf[CONF_PAGE])
        cg.add(var.add_screen(screen, page, conf[CONF_REQUIRES_HA]))
        await _add_triggers(var, "add_enter_trigger", conf.get(CONF_ON_ENTER, []), screen)
        await _add_triggers(var, "add_exit_trigger", conf.get(CONF_ON_EXIT, []), screen)

    # Apps in strip order: by `order`, then by face id.
    apps = sorted(config[CONF_APPS].items(), key=lambda item: (item[1][CONF_ORDER], item[0]))
    for index, (face_id, conf) in enumerate(apps):
        page = await cg.get_variable(conf[CONF_PAGE])
        cg.add(var.add_app(face_id, page, conf[CONF_REQUIRES_HA]))
        await _add_triggers(var, "add_app_enter_trigger", conf[CONF_ON_ENTER], index)
        await _add_triggers(var, "add_app_exit_trigger", conf[CONF_ON_EXIT], index)
        await _add_triggers(var, "add_app_press_trigger", conf[CONF_ON_PRESS], index)

    await _add_triggers(
        var,
        "add_connection_trigger",
        config.get(CONF_ON_CONNECTION_CHANGE, []),
        trigger_args=[(Connection, "stage")],
    )
    await _add_triggers(var, "add_screen_trigger", config.get(CONF_ON_SCREEN_CHANGE, []))
    await _add_triggers(var, "add_sync_progress_trigger", config.get(CONF_ON_SYNC_PROGRESS, []))
