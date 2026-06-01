DOMAIN="aecc_local_community"
LOGGER_NAME = "custom_components.aecc_local_community"

CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 10  # seconds
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 60

# How many consecutive poll failures before marking coordinator data unavailable
FAILURE_TOLERANCE = 5
# How long (seconds) to hold last good data while failures < FAILURE_TOLERANCE
DATA_HOLD_SECONDS = 120

# ── Control register addresses ────────────────────────────────────────────────
REG_EMS_ENABLE = "3000"       # 0 = off, 1 = on
REG_CONTROL_TIME1 = "3003"    # Power/direction time-slot (CSV string)
REG_SCHEDULE_MODE = "3020"    # 3 = AI self-consumption, 6 = custom schedule
REG_AI_SMART_CHARGE = "3021"  # 0 = off, 1 = on
REG_AI_SMART_DISC = "3022"    # 0 = off, 1 = on
REG_MIN_SOC = "3023"          # Minimum discharge SOC (%)
REG_MAX_SOC = "3024"          # Maximum charge SOC (%)
REG_CUSTOM_MODE = "3030"      # 0 = off, 1 = on

# Disabled/idle time slot — clears any active schedule slot
SLOT_DISABLED = "0,00:00,00:00,0,0,0,0,0,0,100,10"

# ── Work modes ────────────────────────────────────────────────────────────────
MODE_SELF_CONSUMPTION = "Self-Consumption (AI)"
MODE_CUSTOM = "Custom / Manual"
MODE_DISABLED = "Disabled"

# ── Power limits ──────────────────────────────────────────────────────────────
MAX_CHARGE_POWER_W = 800   # conservative default; increase at your own risk
MAX_DISCHARGE_POWER_W = 800

DEVICE_TYPE_MAP = [
    (1, 49, "逆变器/离网机/储能机"),
    (50, 54, "电表"),
    (55, 79, "充电桩"),
    (80, 109, "电池"),
    (110, 139, "插座"),
    (141, 145, "交流耦合器"),
    (150, 155, "热水控制器"),
    (156, 160, "继电器"),
]
def get_device_type_name(device_type: int) -> str:
    for start, end, name in DEVICE_TYPE_MAP:
        if start <= device_type <= end:
            return name
    return "设备"