"""Constants for the Raspberry Pi RF Switch integration."""

DOMAIN = "rpi_rf_switch"

CONF_GPIO = "gpio"
CONF_RX_GPIO = "rx_gpio"
CONF_NAME = "name"
CONF_MODE = "mode"
CONF_SYSTEM_CODE = "system_code"
CONF_UNIT_CODE = "unit_code"
CONF_CODE_ON = "code_on"
CONF_CODE_OFF = "code_off"
CONF_PROTOCOL = "protocol"
CONF_PULSELENGTH = "pulselength"
CONF_SIGNAL_REPETITIONS = "signal_repetitions"
CONF_CODE_LENGTH = "code_length"

MODE_DIP = "dip"
MODE_DIRECT = "direct"
MODE_LEARN = "learn"

DEFAULT_GPIO = 17
DEFAULT_RX_GPIO = 27
DEFAULT_PROTOCOL = 1
DEFAULT_SIGNAL_REPETITIONS = 10
DEFAULT_CODE_LENGTH = 24
