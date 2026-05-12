"""Light platform for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CODE_LENGTH,
    CONF_CODE_OFF,
    CONF_CODE_ON,
    CONF_DEVICE_TYPE,
    CONF_GPIO,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_PULSELENGTH,
    CONF_SIGNAL_REPETITIONS,
    DEFAULT_CODE_LENGTH,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_PROTOCOL,
    DEFAULT_SIGNAL_REPETITIONS,
    DEVICE_TYPE_LIGHT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Raspberry Pi RF lights from a config entry."""
    config = {**entry.data, **entry.options}
    device_type = config.get(CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE)

    # Only handle light entities
    if device_type != DEVICE_TYPE_LIGHT:
        return

    gpio = entry.data[CONF_GPIO]
    rf_data = hass.data[DOMAIN][gpio]

    async_add_entities([RpiRfLight(entry, rf_data)])


class RpiRfLight(LightEntity, RestoreEntity):
    """A light that sends 433 MHz RF codes via a GPIO transmitter."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, rf_data: dict) -> None:
        """Initialize the RF light."""
        self._entry = entry
        self._rfdevice = rf_data["device"]
        self._lock = rf_data["lock"]
        self._rx_unregister: Callable[[], None] | None = None

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

    async def async_added_to_hass(self) -> None:
        """Restore last known state and register RX callback."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

        rx_listener = self.hass.data[DOMAIN].get("rx_listener")
        if rx_listener:
            self._rx_unregister = rx_listener.register_callback(
                self._on_rf_received
            )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister RX callback on removal."""
        if self._rx_unregister:
            self._rx_unregister()
            self._rx_unregister = None

    def _on_rf_received(
        self, code: int, protocol: int, pulselength: int
    ) -> None:
        """Handle received RF code (called from RX thread)."""
        if code == self._code_on and not self._attr_is_on:
            self._attr_is_on = True
            self.schedule_update_ha_state()
        elif code == self._code_off and self._attr_is_on:
            self._attr_is_on = False
            self.schedule_update_ha_state()

    @property
    def device_info(self):
        """Return device information for the HA device registry."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "433 MHz RF",
            "model": "Funklicht",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        await self._async_send_code(self._code_on)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._async_send_code(self._code_off)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _async_send_code(self, code: int) -> None:
        """Send an RF code in the executor (blocking I/O)."""
        await self.hass.async_add_executor_job(self._send_code_sync, code)

    def _send_code_sync(self, code: int) -> None:
        """Send an RF code (runs in executor thread)."""
        rx_listener = self.hass.data[DOMAIN].get("rx_listener")
        if rx_listener:
            rx_listener.set_tx_guard()

        with self._lock:
            for _ in range(self._signal_repetitions):
                self._rfdevice.tx_code(
                    code,
                    self._protocol,
                    self._pulselength,
                    self._code_length,
                )
