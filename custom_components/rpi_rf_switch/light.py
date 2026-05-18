"""Light platform for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import logging
import time
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
    CONF_CODES_OFF,
    CONF_CODES_ON,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
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
    ENTRY_TYPE_DEVICE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Raspberry Pi RF lights from a config entry."""
    config = {**entry.data, **entry.options}

    if config.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_DEVICE:
        return

    if config.get(CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE) != DEVICE_TYPE_LIGHT:
        return

    async_add_entities([RpiRfLight(entry)])


class RpiRfLight(LightEntity, RestoreEntity):
    """A light that sends 433 MHz RF codes via a GPIO transmitter."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the RF light."""
        self._entry = entry

        config = {**entry.data, **entry.options}

        self._attr_name = None
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_is_on = False
        self._device_name = config[CONF_NAME]

        self._code_on: int = config[CONF_CODE_ON]
        self._code_off: int = config[CONF_CODE_OFF]
        self._codes_on: set[int] = set(config.get(CONF_CODES_ON, [self._code_on]))
        self._codes_off: set[int] = set(config.get(CONF_CODES_OFF, [self._code_off]))
        self._protocol: int = config.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        self._pulselength: int | None = config.get(CONF_PULSELENGTH)
        self._signal_repetitions: int = config.get(
            CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
        )
        self._code_length: int = config.get(
            CONF_CODE_LENGTH, DEFAULT_CODE_LENGTH
        )
        self._tx_generation: int = 0

    async def async_added_to_hass(self) -> None:
        """Restore last known state and register RX callback."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == STATE_ON

        rx_listener = self.hass.data[DOMAIN].get("rx_listener")
        if rx_listener:
            rx_listener.register_callback(self._on_rf_received)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister RX callback on removal."""
        rx_listener = self.hass.data[DOMAIN].get("rx_listener")
        if rx_listener:
            rx_listener.unregister_callback(self._on_rf_received)

    def _on_rf_received(
        self, code: int, protocol: int, pulselength: int
    ) -> None:
        """Handle received RF code (called from RX thread)."""
        if code in self._codes_on and not self._attr_is_on:
            self._attr_is_on = True
            self.schedule_update_ha_state()
        elif code in self._codes_off and self._attr_is_on:
            self._attr_is_on = False
            self.schedule_update_ha_state()

    @property
    def device_info(self):
        """Return device information for the HA device registry."""
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._device_name,
            "manufacturer": "433 MHz RF",
            "model": "Funklicht",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        self._attr_is_on = True
        self.async_write_ha_state()
        self._tx_generation += 1
        gen = self._tx_generation
        self.hass.async_add_executor_job(
            self._send_code_sync, self._code_on, gen
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        self._attr_is_on = False
        self.async_write_ha_state()
        self._tx_generation += 1
        gen = self._tx_generation
        self.hass.async_add_executor_job(
            self._send_code_sync, self._code_off, gen
        )

    def _send_code_sync(self, code: int, generation: int) -> None:
        """Send an RF code (runs in executor thread)."""
        tx = self.hass.data[DOMAIN].get("tx_module")
        if not tx:
            _LOGGER.error("TX module not available")
            return

        with tx["lock"]:
            if generation != self._tx_generation:
                _LOGGER.debug("TX skipped (superseded): code=%s", code)
                return

            rx_listener = self.hass.data[DOMAIN].get("rx_listener")
            if rx_listener:
                rx_listener.set_tx_guard()
                time.sleep(0.1)

            try:
                tx["device"].send(
                    code=code,
                    protocol=self._protocol,
                    pulselength=self._pulselength,
                    repeat=self._signal_repetitions,
                    length=self._code_length,
                )
            finally:
                if rx_listener:
                    rx_listener.clear_tx_guard()
