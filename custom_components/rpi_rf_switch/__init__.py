"""Raspberry Pi 433 MHz RF Switch integration for Home Assistant."""
from __future__ import annotations

import importlib
import logging
from threading import RLock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_GPIO, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Raspberry Pi RF Switch from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    gpio = entry.data[CONF_GPIO]

    # Share one RFDevice instance per GPIO pin (thread-safe via lock)
    if gpio not in hass.data[DOMAIN]:
        try:
            rpi_rf = await hass.async_add_executor_job(
                importlib.import_module, "rpi_rf"
            )
            rfdevice = await hass.async_add_executor_job(rpi_rf.RFDevice, gpio)
            await hass.async_add_executor_job(rfdevice.enable_tx)
        except Exception as err:
            _LOGGER.error(
                "Failed to initialize RF device on GPIO %s: %s", gpio, err
            )
            raise ConfigEntryNotReady(
                f"Cannot access GPIO {gpio}: {err}"
            ) from err

        hass.data[DOMAIN][gpio] = {
            "device": rfdevice,
            "lock": RLock(),
            "users": 0,
        }

    hass.data[DOMAIN][gpio]["users"] += 1

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
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        gpio = entry.data[CONF_GPIO]
        if gpio in hass.data[DOMAIN]:
            hass.data[DOMAIN][gpio]["users"] -= 1
            if hass.data[DOMAIN][gpio]["users"] <= 0:
                rfdevice = hass.data[DOMAIN][gpio]["device"]
                await hass.async_add_executor_job(rfdevice.cleanup)
                del hass.data[DOMAIN][gpio]

    return unload_ok
