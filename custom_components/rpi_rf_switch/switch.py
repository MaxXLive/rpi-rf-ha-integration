"""Switch platform for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CODE_LENGTH,
    CONF_CODE_OFF,
    CONF_CODE_ON,
    CONF_GPIO,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_PULSELENGTH,
    CONF_SIGNAL_REPETITIONS,
    DEFAULT_CODE_LENGTH,
    DEFAULT_PROTOCOL,
    DEFAULT_SIGNAL_REPETITIONS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Raspberry Pi RF switches from a config entry."""
    gpio = entry.data[CONF_GPIO]
    rf_data = hass.data[DOMAIN][gpio]

    async_add_entities([RpiRfSwitch(entry, rf_data)])


class RpiRfSwitch(SwitchEntity):
    """A switch that sends 433 MHz RF codes via a GPIO transmitter."""

    _attr_assumed_state = True
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, rf_data: dict) -> None:
        """Initialize the RF switch."""
        self._entry = entry
        self._rfdevice = rf_data["device"]
        self._lock = rf_data["lock"]

        # Merge options over data (options take precedence for edits)
        config = {**entry.data, **entry.options}

        self._attr_name = config[CONF_NAME]
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_is_on = False

        self._code_on: int = config[CONF_CODE_ON]
        self._code_off: int = config[CONF_CODE_OFF]
        self._protocol: int = config.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        self._pulselength: int | None = config.get(CONF_PULSELENGTH)
        self._signal_repetitions: int = config.get(
            CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
        )
        self._code_length: int = config.get(
            CONF_CODE_LENGTH, DEFAULT_CODE_LENGTH
        )

    @property
    def device_info(self):
        """Return device information for the HA device registry."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "433 MHz RF",
            "model": "Funksteckdose",
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Turning on %s (code=%s)", self._attr_name, self._code_on)
        await self._async_send_code(self._code_on)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        _LOGGER.debug(
            "Turning off %s (code=%s)", self._attr_name, self._code_off
        )
        await self._async_send_code(self._code_off)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _async_send_code(self, code: int) -> None:
        """Send an RF code in the executor (blocking I/O)."""
        await self.hass.async_add_executor_job(self._send_code_sync, code)

    def _send_code_sync(self, code: int) -> None:
        """Send an RF code (runs in executor thread)."""
        with self._lock:
            for _ in range(self._signal_repetitions):
                self._rfdevice.tx_code(
                    code,
                    self._protocol,
                    self._pulselength,
                    self._code_length,
                )
