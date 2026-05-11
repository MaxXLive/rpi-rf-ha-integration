"""Config flow for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .codes import calc_pt2262_code
from .const import (
    CONF_CODE_LENGTH,
    CONF_CODE_OFF,
    CONF_CODE_ON,
    CONF_GPIO,
    CONF_MODE,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_PULSELENGTH,
    CONF_SIGNAL_REPETITIONS,
    CONF_SYSTEM_CODE,
    CONF_UNIT_CODE,
    DEFAULT_CODE_LENGTH,
    DEFAULT_GPIO,
    DEFAULT_PROTOCOL,
    DEFAULT_SIGNAL_REPETITIONS,
    DOMAIN,
    MODE_DIP,
    MODE_DIRECT,
)

GPIO_PINS = list(range(2, 28))
PROTOCOL_OPTIONS = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6 (HT6P20B)"}
UNIT_OPTIONS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"}


class RpiRfSwitchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Raspberry Pi RF Switch."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Name, GPIO pin, and configuration mode."""
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_MODE] == MODE_DIP:
                return await self.async_step_dip()
            return await self.async_step_direct()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_GPIO, default=DEFAULT_GPIO): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                    vol.Required(CONF_MODE, default=MODE_DIP): vol.In(
                        {
                            MODE_DIP: "DIP-Schalter (System + Unit Code)",
                            MODE_DIRECT: "Direkter Code (Dezimal)",
                        }
                    ),
                }
            ),
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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RpiRfSwitchOptionsFlow:
        """Get the options flow handler."""
        return RpiRfSwitchOptionsFlow(config_entry)


class RpiRfSwitchOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for editing an existing RF switch."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

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
                }
            ),
        )
