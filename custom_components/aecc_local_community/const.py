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