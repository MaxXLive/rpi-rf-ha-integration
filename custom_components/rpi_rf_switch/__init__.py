"""Raspberry Pi 433 MHz RF Switch integration for Home Assistant."""
from __future__ import annotations

import logging
from threading import RLock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ENTRY_TYPE,
    CONF_GPIO,
    CONF_RX_DEBUG,
    CONF_RX_ENABLED,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_RX,
    ENTRY_TYPE_TX,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "light"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Raspberry Pi RF Switch from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    if entry_type == ENTRY_TYPE_TX:
        return await _setup_tx_module(hass, entry)
    if entry_type == ENTRY_TYPE_RX:
        return await _setup_rx_module(hass, entry)
    if entry_type == ENTRY_TYPE_DEVICE:
        return await _setup_device(hass, entry)

    _LOGGER.error("Unknown entry type: %s", entry_type)
    return False


async def _setup_tx_module(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the TX transmitter module."""
    gpio = entry.data[CONF_GPIO]

    try:
        from rpi_rf_gpiod import RFTransmitter

        tx = RFTransmitter(gpio=gpio)
        await hass.async_add_executor_job(tx.enable)
    except Exception as err:
        _LOGGER.error("Failed to initialize TX on GPIO %s: %s", gpio, err)
        raise ConfigEntryNotReady(
            f"Cannot access GPIO {gpio}: {err}"
        ) from err

    hass.data[DOMAIN]["tx_module"] = {
        "gpio": gpio,
        "device": tx,
        "lock": RLock(),
    }
    _LOGGER.info("TX module initialized on GPIO %s", gpio)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _setup_rx_module(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the RX receiver module."""
    config = {**entry.data, **entry.options}
    gpio = config[CONF_GPIO]
    rx_enabled = config.get(CONF_RX_ENABLED, True)
    rx_debug = config.get(CONF_RX_DEBUG, False)

    if not rx_enabled:
        _LOGGER.info("RX background monitoring disabled")
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        return True

    try:
        from rpi_rf_gpiod import RFReceiver

        receiver = RFReceiver(gpio=gpio)
        await hass.async_add_executor_job(receiver.enable)

        if rx_debug:
            def _debug_rx_callback(code: int, protocol: int, pulselength: int) -> None:
                """Log and fire event for each received RF code."""
                _LOGGER.info(
                    "RX DEBUG: code=%s, protocol=%s, pulselength=%s",
                    code, protocol, pulselength,
                )
                hass.bus.fire(
                    f"{DOMAIN}_code_received",
                    {
                        "code": code,
                        "protocol": protocol,
                        "pulselength": pulselength,
                    },
                )

            receiver.register_callback(_debug_rx_callback)
            _LOGGER.info("RX module initialized on GPIO %s (DEBUG mode active)", gpio)
        else:
            _LOGGER.info("RX module initialized on GPIO %s", gpio)

        hass.data[DOMAIN]["rx_listener"] = receiver
    except Exception as err:
        _LOGGER.warning("Failed to start RX on GPIO %s: %s", gpio, err)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _setup_device(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a device (outlet/light/switch) entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    if entry_type == ENTRY_TYPE_TX:
        tx = hass.data[DOMAIN].pop("tx_module", None)
        if tx:
            await hass.async_add_executor_job(tx["device"].disable)
            _LOGGER.info("TX module stopped")
        return True

    if entry_type == ENTRY_TYPE_RX:
        rx = hass.data[DOMAIN].pop("rx_listener", None)
        if rx:
            await hass.async_add_executor_job(rx.disable)
            _LOGGER.info("RX module stopped")
        return True

    if entry_type == ENTRY_TYPE_DEVICE:
        return await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )

    return True
