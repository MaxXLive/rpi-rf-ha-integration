"""Config flow for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .codes import calc_pt2262_code, decode_pt2262_code
from .const import (
    CONF_CODE_LENGTH,
    CONF_CODE_OFF,
    CONF_CODE_ON,
    CONF_DEVICE_TYPE,
    CONF_GPIO,
    CONF_MODE,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_PULSELENGTH,
    CONF_RX_GPIO,
    CONF_SIGNAL_REPETITIONS,
    CONF_SYSTEM_CODE,
    CONF_UNIT_CODE,
    DEFAULT_CODE_LENGTH,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_GPIO,
    DEFAULT_PROTOCOL,
    DEFAULT_RX_GPIO,
    DEFAULT_SIGNAL_REPETITIONS,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_OUTLET,
    DEVICE_TYPE_SWITCH,
    DOMAIN,
    MODE_DIP,
    MODE_DIRECT,
    MODE_LEARN,
)

_LOGGER = logging.getLogger(__name__)

GPIO_PINS = list(range(2, 28))
PROTOCOL_OPTIONS = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6 (HT6P20B)"}
UNIT_OPTIONS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"}
RX_GPIO_OPTIONS = {0: "-- Nicht verwenden --"}
RX_GPIO_OPTIONS.update({pin: f"GPIO {pin}" for pin in GPIO_PINS})

DEVICE_TYPE_OPTIONS = {
    DEVICE_TYPE_OUTLET: "Steckdose / Outlet",
    DEVICE_TYPE_LIGHT: "Licht / Light",
    DEVICE_TYPE_SWITCH: "Schalter / Switch",
}


class RpiRfSwitchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Raspberry Pi RF Switch."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._learn_rx = None
        self._learn_rx_is_temp = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Name, GPIO pin, RX GPIO, and configuration mode."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            rx_gpio = user_input.get(CONF_RX_GPIO, 0)

            # Validate RX GPIO != TX GPIO
            if rx_gpio and rx_gpio > 0 and rx_gpio == user_input[CONF_GPIO]:
                errors[CONF_RX_GPIO] = "rx_same_as_tx"
            elif user_input[CONF_MODE] == MODE_LEARN:
                # Learn mode requires RX GPIO
                global_rx = self.hass.data.get(DOMAIN, {}).get("rx_listener")
                if (not rx_gpio or rx_gpio == 0) and not global_rx:
                    errors[CONF_RX_GPIO] = "rx_gpio_required"
                elif not rx_gpio and global_rx:
                    self._data[CONF_RX_GPIO] = global_rx.gpio

            if not errors:
                if user_input[CONF_MODE] == MODE_DIP:
                    return await self.async_step_dip()
                if user_input[CONF_MODE] == MODE_LEARN:
                    return await self.async_step_learn_on()
                return await self.async_step_direct()

        # Determine default RX GPIO
        global_rx = self.hass.data.get(DOMAIN, {}).get("rx_listener")
        default_rx = global_rx.gpio if global_rx else 0

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_GPIO, default=DEFAULT_GPIO): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                    vol.Required(CONF_RX_GPIO, default=default_rx): vol.In(
                        RX_GPIO_OPTIONS
                    ),
                    vol.Required(CONF_MODE, default=MODE_DIP): vol.In(
                        {
                            MODE_DIP: "DIP-Schalter (System + Unit Code)",
                            MODE_DIRECT: "Direkter Code (Dezimal)",
                            MODE_LEARN: "Anlernen (Code von Fernbedienung)",
                        }
                    ),
                    vol.Required(
                        CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
            errors=errors,
        )

    async def async_step_dip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a: DIP switch configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            system_code = user_input[CONF_SYSTEM_CODE].strip()
            unit_code = user_input[CONF_UNIT_CODE]

            if not re.match(r"^[01]{5}$", system_code):
                errors[CONF_SYSTEM_CODE] = "invalid_system_code"
            else:
                code_on = calc_pt2262_code(system_code, unit_code, True)
                code_off = calc_pt2262_code(system_code, unit_code, False)

                self._data.update(user_input)
                self._data[CONF_SYSTEM_CODE] = system_code
                self._data[CONF_CODE_ON] = code_on
                self._data[CONF_CODE_OFF] = code_off

                unique_id = (
                    f"rpi_rf_{self._data[CONF_GPIO]}_{system_code}_{unit_code}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=self._data[CONF_NAME],
                    data=self._data,
                )

        return self.async_show_form(
            step_id="dip",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYSTEM_CODE): str,
                    vol.Required(CONF_UNIT_CODE, default="A"): vol.In(
                        UNIT_OPTIONS
                    ),
                    vol.Optional(
                        CONF_PROTOCOL, default=DEFAULT_PROTOCOL
                    ): vol.In(PROTOCOL_OPTIONS),
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=DEFAULT_SIGNAL_REPETITIONS,
                    ): int,
                }
            ),
            errors=errors,
            description_placeholders={
                "example_code": "10101",
            },
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2b: Direct code configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            unique_id = (
                f"rpi_rf_{self._data[CONF_GPIO]}_{user_input[CONF_CODE_ON]}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        return self.async_show_form(
            step_id="direct",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CODE_ON): int,
                    vol.Required(CONF_CODE_OFF): int,
                    vol.Optional(
                        CONF_PROTOCOL, default=DEFAULT_PROTOCOL
                    ): vol.In(PROTOCOL_OPTIONS),
                    vol.Optional(CONF_PULSELENGTH): int,
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=DEFAULT_SIGNAL_REPETITIONS,
                    ): int,
                    vol.Optional(
                        CONF_CODE_LENGTH, default=DEFAULT_CODE_LENGTH
                    ): int,
                }
            ),
            errors=errors,
        )

    # --- Learn mode steps ---

    async def _ensure_learn_listener(self) -> bool:
        """Ensure an RX listener is available for learning."""
        rx_gpio = self._data.get(CONF_RX_GPIO, 0)
        if not rx_gpio or rx_gpio == 0:
            return False

        from .receiver import RFReceiver

        # Reuse global listener if on the same GPIO
        global_rx = self.hass.data.get(DOMAIN, {}).get("rx_listener")
        if global_rx and global_rx.gpio == rx_gpio:
            self._learn_rx = global_rx
            self._learn_rx_is_temp = False
        else:
            self._learn_rx = RFReceiver(rx_gpio)
            await self.hass.async_add_executor_job(self._learn_rx.start)
            self._learn_rx_is_temp = True

        await self.hass.async_add_executor_job(self._learn_rx.start_capture)
        return True

    async def _cleanup_learn_listener(self) -> None:
        """Clean up the temporary learn listener."""
        if self._learn_rx is not None:
            await self.hass.async_add_executor_job(
                self._learn_rx.stop_capture
            )
            if self._learn_rx_is_temp:
                await self.hass.async_add_executor_job(self._learn_rx.stop)
            self._learn_rx = None

    async def async_step_learn_on(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn ON code: listen for remote button press."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User submitted — read captured codes
            captured = await self.hass.async_add_executor_job(
                self._learn_rx.stop_capture
            )

            if not captured:
                errors["base"] = "no_code_received"
                # Restart capture for retry
                await self.hass.async_add_executor_job(
                    self._learn_rx.start_capture
                )
            else:
                best = self._get_best_code(captured)
                self._data[CONF_CODE_ON] = best.code
                self._data[CONF_PROTOCOL] = best.protocol
                self._data[CONF_PULSELENGTH] = best.pulselength
                _LOGGER.info(
                    "Learned ON code=%s proto=%s pulse=%s",
                    best.code,
                    best.protocol,
                    best.pulselength,
                )
                # Start capture for OFF code
                await self.hass.async_add_executor_job(
                    self._learn_rx.start_capture
                )
                return await self.async_step_learn_off()
        else:
            # First display — start listening
            if not await self._ensure_learn_listener():
                return self.async_abort(reason="no_rx_gpio")

        return self.async_show_form(
            step_id="learn_on",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_learn_off(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn OFF code: listen for remote button press."""
        errors: dict[str, str] = {}

        if user_input is not None:
            captured = await self.hass.async_add_executor_job(
                self._learn_rx.stop_capture
            )

            if not captured:
                errors["base"] = "no_code_received"
                await self.hass.async_add_executor_job(
                    self._learn_rx.start_capture
                )
            else:
                best = self._get_best_code(captured)
                self._data[CONF_CODE_OFF] = best.code
                _LOGGER.info("Learned OFF code=%s", best.code)

                # Clean up learn listener
                await self._cleanup_learn_listener()

                # Try to decode as PT2262
                on_decoded = decode_pt2262_code(self._data[CONF_CODE_ON])
                off_decoded = decode_pt2262_code(self._data[CONF_CODE_OFF])

                if on_decoded and off_decoded:
                    self._data[CONF_SYSTEM_CODE] = on_decoded["system_code"]
                    self._data[CONF_UNIT_CODE] = on_decoded["unit_code"]
                    self._data[CONF_MODE] = MODE_DIP
                    _LOGGER.info(
                        "PT2262 detected: system=%s unit=%s",
                        on_decoded["system_code"],
                        on_decoded["unit_code"],
                    )
                else:
                    self._data[CONF_MODE] = MODE_DIRECT

                unique_id = (
                    f"rpi_rf_{self._data[CONF_GPIO]}"
                    f"_{self._data[CONF_CODE_ON]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=self._data[CONF_NAME],
                    data=self._data,
                )

        return self.async_show_form(
            step_id="learn_off",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    @staticmethod
    def _get_best_code(captured):
        """Find the most frequently received code from the capture buffer."""
        code_counts = Counter(c.code for c in captured)
        best_code_val = code_counts.most_common(1)[0][0]
        return next(c for c in captured if c.code == best_code_val)

    # --- Options flow ---

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RpiRfSwitchOptionsFlow:
        """Get the options flow handler."""
        return RpiRfSwitchOptionsFlow()


class RpiRfSwitchOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for editing an existing RF switch."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage switch options."""
        data = {**self.config_entry.data, **self.config_entry.options}
        mode = data.get(CONF_MODE, MODE_DIRECT)

        if mode == MODE_DIP:
            return await self.async_step_dip_options(user_input)
        return await self.async_step_direct_options(user_input)

    async def async_step_dip_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit DIP switch options."""
        errors: dict[str, str] = {}
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            system_code = user_input[CONF_SYSTEM_CODE].strip()
            unit_code = user_input[CONF_UNIT_CODE]

            if not re.match(r"^[01]{5}$", system_code):
                errors[CONF_SYSTEM_CODE] = "invalid_system_code"
            else:
                code_on = calc_pt2262_code(system_code, unit_code, True)
                code_off = calc_pt2262_code(system_code, unit_code, False)
                result = {
                    **user_input,
                    CONF_SYSTEM_CODE: system_code,
                    CONF_CODE_ON: code_on,
                    CONF_CODE_OFF: code_off,
                }
                return self.async_create_entry(title="", data=result)

        return self.async_show_form(
            step_id="dip_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SYSTEM_CODE,
                        default=data.get(CONF_SYSTEM_CODE, ""),
                    ): str,
                    vol.Required(
                        CONF_UNIT_CODE,
                        default=data.get(CONF_UNIT_CODE, "A"),
                    ): vol.In(UNIT_OPTIONS),
                    vol.Optional(
                        CONF_PROTOCOL,
                        default=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    ): vol.In(PROTOCOL_OPTIONS),
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=data.get(
                            CONF_SIGNAL_REPETITIONS,
                            DEFAULT_SIGNAL_REPETITIONS,
                        ),
                    ): int,
                    vol.Required(
                        CONF_DEVICE_TYPE,
                        default=data.get(
                            CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
                        ),
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
            errors=errors,
        )

    async def async_step_direct_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit direct code options."""
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="direct_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CODE_ON, default=data.get(CONF_CODE_ON)
                    ): int,
                    vol.Required(
                        CONF_CODE_OFF, default=data.get(CONF_CODE_OFF)
                    ): int,
                    vol.Optional(
                        CONF_PROTOCOL,
                        default=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    ): vol.In(PROTOCOL_OPTIONS),
                    vol.Optional(
                        CONF_PULSELENGTH,
                        default=data.get(CONF_PULSELENGTH),
                    ): int,
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=data.get(
                            CONF_SIGNAL_REPETITIONS,
                            DEFAULT_SIGNAL_REPETITIONS,
                        ),
                    ): int,
                    vol.Optional(
                        CONF_CODE_LENGTH,
                        default=data.get(CONF_CODE_LENGTH, DEFAULT_CODE_LENGTH),
                    ): int,
                    vol.Required(
                        CONF_DEVICE_TYPE,
                        default=data.get(
                            CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
                        ),
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
        )
