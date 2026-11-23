"""knob_shell: owner of the UI state of an Orbita device."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

CONF_HAS_KNOB = "has_knob"
CONF_HAS_TOUCH = "has_touch"
CONF_MOTION_DEFAULT = "motion_default"

knob_shell_ns = cg.esphome_ns.namespace("knob_shell")
KnobShell = knob_shell_ns.class_("KnobShell", cg.Component)
Motion = knob_shell_ns.enum("Motion", is_class=True)

MOTIONS = {
    "full": Motion.FULL,
    "reduced": Motion.REDUCED,
    "off": Motion.OFF,
}


def _motion(value):
    # Unquoted `off` is parsed by YAML as boolean false.
    if value is False:
        value = "off"
    return cv.enum(MOTIONS, lower=True)(value)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(KnobShell),
        cv.Required(CONF_HAS_KNOB): cv.boolean,
        cv.Required(CONF_HAS_TOUCH): cv.boolean,
        cv.Optional(CONF_MOTION_DEFAULT, default="full"): _motion,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_has_knob(config[CONF_HAS_KNOB]))
    cg.add(var.set_has_touch(config[CONF_HAS_TOUCH]))
    cg.add(var.set_motion_default(config[CONF_MOTION_DEFAULT]))
