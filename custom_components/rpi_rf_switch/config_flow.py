"""Config flow for Raspberry Pi 433 MHz RF Switch."""
from __future__ import annotations

import asyncio
import logging
import re
import time
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
    CONF_CODES_OFF,
    CONF_CODES_ON,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_GPIO,
    CONF_MODE,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_PULSELENGTH,
    CONF_RX_DEBUG,
    CONF_RX_ENABLED,
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
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_RX,
    ENTRY_TYPE_TX,
    MODE_DIP,
    MODE_DIRECT,
    MODE_LEARN,
)

_LOGGER = logging.getLogger(__name__)

GPIO_PINS = list(range(2, 28))
PROTOCOL_OPTIONS = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6 (HT6P20B)"}
UNIT_OPTIONS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"}
DEVICE_TYPE_OPTIONS = {
    DEVICE_TYPE_OUTLET: "Steckdose / Outlet",
    DEVICE_TYPE_LIGHT: "Licht / Light",
    DEVICE_TYPE_SWITCH: "Schalter / Switch",
}


class RpiRfSwitchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Raspberry Pi RF Switch."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._learn_rx = None
        self._learn_rx_is_temp = False
        self._learn_task: asyncio.Task | None = None
        self._is_rotating = False

    def _get_entries_by_type(self, entry_type: str) -> list:
        """Get all config entries of a given type."""
        return [
            e
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.data.get(CONF_ENTRY_TYPE) == entry_type
        ]

    def _has_tx(self) -> bool:
        return len(self._get_entries_by_type(ENTRY_TYPE_TX)) > 0

    def _has_rx(self) -> bool:
        return len(self._get_entries_by_type(ENTRY_TYPE_RX)) > 0

    # --- Step 1: What to add? ---

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry point: decide what to add."""
        has_tx = self._has_tx()
        has_rx = self._has_rx()

        # No TX module yet -> go straight to TX setup
        if not has_tx:
            return await self.async_step_tx_module()

        # TX + RX both exist -> go straight to device setup
        if has_tx and has_rx:
            return await self.async_step_device()

        # TX exists but no RX -> show choice
        if user_input is not None:
            if user_input["choice"] == "rx_module":
                return await self.async_step_rx_module()
            return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("choice", default="device"): vol.In(
                        {
                            "device": "🔌 Funkgerät hinzufügen",
                            "rx_module": "📻 Empfänger-Modul einrichten",
                        }
                    ),
                }
            ),
        )

    # --- TX Module ---

    async def async_step_tx_module(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the TX transmitter module."""
        if user_input is not None:
            await self.async_set_unique_id("rpi_rf_tx_module")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="📡 Sender-Modul (TX)",
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_TX,
                    CONF_GPIO: user_input[CONF_GPIO],
                },
            )

        return self.async_show_form(
            step_id="tx_module",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GPIO, default=DEFAULT_GPIO): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                }
            ),
        )

    # --- RX Module ---

    async def async_step_rx_module(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure the RX receiver module."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tx_entries = self._get_entries_by_type(ENTRY_TYPE_TX)
            tx_gpio = tx_entries[0].data[CONF_GPIO] if tx_entries else None

            if user_input[CONF_GPIO] == tx_gpio:
                errors[CONF_GPIO] = "rx_same_as_tx"
            else:
                await self.async_set_unique_id("rpi_rf_rx_module")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="📻 Empfänger-Modul (RX)",
                    data={
                        CONF_ENTRY_TYPE: ENTRY_TYPE_RX,
                        CONF_GPIO: user_input[CONF_GPIO],
                    },
                )

        return self.async_show_form(
            step_id="rx_module",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GPIO, default=DEFAULT_RX_GPIO): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                }
            ),
            errors=errors,
        )

    # --- Device setup ---

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure a new RF device (outlet/light/switch)."""
        errors: dict[str, str] = {}
        has_rx = self._has_rx()

        if user_input is not None:
            self._data.update(user_input)
            self._data[CONF_ENTRY_TYPE] = ENTRY_TYPE_DEVICE
            mode = user_input[CONF_MODE]

            if mode == MODE_LEARN and not has_rx:
                errors[CONF_MODE] = "rx_required_for_learn"

            if not errors:
                if mode == MODE_DIP:
                    return await self.async_step_dip()
                if mode == MODE_LEARN:
                    return await self.async_step_learn_on()
                return await self.async_step_direct()

        modes = {
            MODE_DIP: "DIP-Schalter (System + Unit Code)",
            MODE_DIRECT: "Direkter Code (Dezimal)",
        }
        if has_rx:
            modes[MODE_LEARN] = "Anlernen (Code von Fernbedienung)"

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_MODE, default=MODE_DIP): vol.In(modes),
                    vol.Required(
                        CONF_DEVICE_TYPE, default=DEFAULT_DEVICE_TYPE
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
            errors=errors,
        )

    # --- DIP switch step ---

    async def async_step_dip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """DIP switch configuration."""
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
                self._data.setdefault(CONF_PROTOCOL, DEFAULT_PROTOCOL)
                self._data.setdefault(
                    CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
                )

                unique_id = f"rpi_rf_{system_code}_{unit_code}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                _LOGGER.info(
                    "DIP device created: system=%s unit=%s code_on=%s code_off=%s",
                    system_code, unit_code, code_on, code_off,
                )

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
            description_placeholders={"example_code": "10101"},
        )

    # --- Direct code step ---

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Direct code configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            unique_id = f"rpi_rf_{user_input[CONF_CODE_ON]}"
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
        global_rx = self.hass.data.get(DOMAIN, {}).get("rx_listener")
        if global_rx:
            self._learn_rx = global_rx
            self._learn_rx_is_temp = False
        else:
            rx_entries = self._get_entries_by_type(ENTRY_TYPE_RX)
            if not rx_entries:
                return False
            rx_gpio = rx_entries[0].data[CONF_GPIO]
            from rpi_rf_gpiod import RFReceiver

            self._learn_rx = RFReceiver(gpio=rx_gpio)
            await self.hass.async_add_executor_job(self._learn_rx.enable)
            self._learn_rx_is_temp = True

        await self.hass.async_add_executor_job(self._learn_rx.start_capture)
        return True

    async def _cleanup_learn_listener(self) -> None:
        """Clean up the learn listener and cancel any running task."""
        if self._learn_task is not None and not self._learn_task.done():
            self._learn_task.cancel()
        self._learn_task = None
        if self._learn_rx is not None:
            await self.hass.async_add_executor_job(
                self._learn_rx.stop_capture
            )
            if self._learn_rx_is_temp:
                await self.hass.async_add_executor_job(self._learn_rx.disable)
            self._learn_rx = None

    async def _async_wait_for_codes(
        self, min_count: int = 5, timeout: float = 60.0
    ):
        """Wait until enough consistent RF codes are captured.

        Returns dict with:
          - codes: list of (code, protocol, pulselength) for all qualifying codes
          - is_rotating: True if multiple distinct codes detected
          - total_received: total number of code receptions

        Detection strategy:
          1. Single code: one code dominates (>50% of total) with ≥min_count hits
          2. Rotating: multiple codes each ≥3 times, no single code dominant,
             count stabilized for 5 seconds, and no emerging codes still climbing

        The dominance check (>50%) prevents noise codes from triggering
        false rotating detection on single-code devices.
        """
        deadline = time.monotonic() + timeout
        last_rotating_count = 0
        rotating_stable_since: float | None = None
        STABLE_DURATION = 5.0

        while time.monotonic() < deadline:
            snapshot = self._learn_rx.get_capture_snapshot()
            if snapshot:
                code_counts = Counter(c[0] for c in snapshot)
                total = sum(code_counts.values())
                best_code, best_count = code_counts.most_common(1)[0]

                # --- Single code: one code dominates >50% of all receptions ---
                if best_count >= min_count and best_count / total > 0.5:
                    await self.hass.async_add_executor_job(
                        self._learn_rx.stop_capture
                    )
                    best = next(c for c in snapshot if c[0] == best_code)
                    return {
                        "codes": [best],
                        "is_rotating": False,
                        "total_received": total,
                    }

                # --- Rotating: codes appearing ≥3 times (confirmed) ---
                confirmed = {c: n for c, n in code_counts.items() if n >= 3}
                # Codes appearing ≥2 times (might reach 3 soon)
                emerging = {c: n for c, n in code_counts.items() if n >= 2}

                if len(confirmed) >= 2:
                    # More codes still emerging → not stable yet
                    if len(emerging) > len(confirmed):
                        rotating_stable_since = None
                        last_rotating_count = len(confirmed)
                    else:
                        # All emerging codes have been confirmed
                        if len(confirmed) != last_rotating_count:
                            last_rotating_count = len(confirmed)
                            rotating_stable_since = time.monotonic()
                        elif rotating_stable_since is not None:
                            elapsed = time.monotonic() - rotating_stable_since
                            if elapsed >= STABLE_DURATION:
                                codes = []
                                for code_val in confirmed:
                                    rep = next(
                                        c for c in snapshot if c[0] == code_val
                                    )
                                    codes.append(rep)
                                await self.hass.async_add_executor_job(
                                    self._learn_rx.stop_capture
                                )
                                return {
                                    "codes": codes,
                                    "is_rotating": True,
                                    "total_received": total,
                                }
            await asyncio.sleep(0.5)
        await self.hass.async_add_executor_job(
            self._learn_rx.stop_capture
        )
        raise asyncio.TimeoutError("No consistent code detected")

    async def async_step_learn_on(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn ON code with auto-detection."""
        if not self._learn_task:
            if not await self._ensure_learn_listener():
                return self.async_abort(reason="no_rx_gpio")

            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_codes(min_count=5, timeout=60.0)
            )
            return self.async_show_progress(
                step_id="learn_on",
                progress_action="learn_on",
                progress_task=self._learn_task,
            )

        # Task completed
        try:
            result = self._learn_task.result()
        except Exception:
            self._learn_task = None
            return self.async_show_progress_done(
                next_step_id="learn_on_retry"
            )

        self._learn_task = None
        codes = result["codes"]
        self._is_rotating = result["is_rotating"]

        # Store primary code (first/most common) for TX
        primary = codes[0]
        self._data[CONF_CODE_ON] = primary[0]
        self._data[CONF_PROTOCOL] = primary[1]
        self._data[CONF_PULSELENGTH] = primary[2]

        if self._is_rotating:
            self._data[CONF_CODES_ON] = [c[0] for c in codes]

        _LOGGER.info(
            "Learned ON: %s code(s), rotating=%s, primary=%s proto=%s pulse=%s",
            len(codes), self._is_rotating, primary[0], primary[1], primary[2],
        )
        return self.async_show_progress_done(next_step_id="learn_off")

    async def async_step_learn_on_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Retry ON code learning after timeout."""
        if user_input is not None:
            await self.hass.async_add_executor_job(
                self._learn_rx.start_capture
            )
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_codes(min_count=5, timeout=60.0)
            )
            return self.async_show_progress(
                step_id="learn_on",
                progress_action="learn_on",
                progress_task=self._learn_task,
            )

        return self.async_show_form(
            step_id="learn_on_retry",
            data_schema=vol.Schema({}),
            errors={"base": "no_code_received"},
        )

    async def async_step_learn_off(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn OFF code with auto-detection."""
        if not self._learn_task:
            await self.hass.async_add_executor_job(
                self._learn_rx.start_capture
            )
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_codes(min_count=5, timeout=60.0)
            )
            return self.async_show_progress(
                step_id="learn_off",
                progress_action="learn_off",
                progress_task=self._learn_task,
            )

        # Task completed
        try:
            result = self._learn_task.result()
        except Exception:
            self._learn_task = None
            return self.async_show_progress_done(
                next_step_id="learn_off_retry"
            )

        self._learn_task = None
        codes = result["codes"]

        self._data[CONF_CODE_OFF] = codes[0][0]
        if result["is_rotating"] or self._is_rotating:
            self._is_rotating = True
            self._data[CONF_CODES_OFF] = [c[0] for c in codes]

        _LOGGER.info(
            "Learned OFF: %s code(s), rotating=%s",
            len(codes), self._is_rotating,
        )
        await self._cleanup_learn_listener()

        next_step = "learn_confirm_rotating" if self._is_rotating else "learn_confirm"
        return self.async_show_progress_done(
            next_step_id=next_step
        )

    async def async_step_learn_off_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Retry OFF code learning after timeout."""
        if user_input is not None:
            await self.hass.async_add_executor_job(
                self._learn_rx.start_capture
            )
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_codes(min_count=5, timeout=60.0)
            )
            return self.async_show_progress(
                step_id="learn_off",
                progress_action="learn_off",
                progress_task=self._learn_task,
            )

        return self.async_show_form(
            step_id="learn_off_retry",
            data_schema=vol.Schema({}),
            errors={"base": "no_code_received"},
        )

    async def async_step_learn_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show learned codes with DIP decode for confirmation."""
        if user_input is not None:
            self._data.update(user_input)

            on_decoded = decode_pt2262_code(self._data[CONF_CODE_ON])
            off_decoded = decode_pt2262_code(self._data[CONF_CODE_OFF])

            if on_decoded and off_decoded:
                self._data[CONF_SYSTEM_CODE] = on_decoded["system_code"]
                self._data[CONF_UNIT_CODE] = on_decoded["unit_code"]
                self._data[CONF_MODE] = MODE_DIP
                unique_id = f"rpi_rf_{on_decoded['system_code']}_{on_decoded['unit_code']}"
                _LOGGER.info(
                    "PT2262 detected: system=%s unit=%s",
                    on_decoded["system_code"],
                    on_decoded["unit_code"],
                )
            else:
                self._data[CONF_MODE] = MODE_DIRECT
                unique_id = f"rpi_rf_{self._data[CONF_CODE_ON]}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        code_on = self._data[CONF_CODE_ON]
        code_off = self._data[CONF_CODE_OFF]

        on_decoded = decode_pt2262_code(code_on)
        off_decoded = decode_pt2262_code(code_off)

        if on_decoded and off_decoded:
            dip_info = (
                f"System: {on_decoded['system_code']}, "
                f"Unit: {on_decoded['unit_code']}"
            )
        else:
            dip_info = "—"

        return self.async_show_form(
            step_id="learn_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CODE_ON, default=code_on): int,
                    vol.Required(CONF_CODE_OFF, default=code_off): int,
                    vol.Optional(
                        CONF_PROTOCOL,
                        default=self._data.get(
                            CONF_PROTOCOL, DEFAULT_PROTOCOL
                        ),
                    ): vol.In(PROTOCOL_OPTIONS),
                    vol.Optional(
                        CONF_PULSELENGTH,
                        default=self._data.get(CONF_PULSELENGTH),
                    ): int,
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=DEFAULT_SIGNAL_REPETITIONS,
                    ): int,
                    vol.Required(
                        CONF_DEVICE_TYPE,
                        default=self._data.get(
                            CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
                        ),
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
            description_placeholders={
                "code_on": str(code_on),
                "code_off": str(code_off),
                "dip_info": dip_info,
            },
        )

    @staticmethod
    def _get_best_code(captured):
        """Find the most frequently received code from the capture buffer."""
        code_counts = Counter(c[0] for c in captured)
        best_code_val = code_counts.most_common(1)[0][0]
        return next(c for c in captured if c[0] == best_code_val)

    async def async_step_learn_confirm_rotating(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show rotating codes for confirmation (read-only codes)."""
        if user_input is not None:
            self._data[CONF_SIGNAL_REPETITIONS] = user_input.get(
                CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
            )
            self._data[CONF_DEVICE_TYPE] = user_input.get(
                CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
            )
            self._data[CONF_MODE] = MODE_LEARN

            unique_id = f"rpi_rf_{self._data[CONF_CODE_ON]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        codes_on = self._data.get(CONF_CODES_ON, [self._data[CONF_CODE_ON]])
        codes_off = self._data.get(CONF_CODES_OFF, [self._data[CONF_CODE_OFF]])

        codes_on_str = ", ".join(str(c) for c in codes_on)
        codes_off_str = ", ".join(str(c) for c in codes_off)

        return self.async_show_form(
            step_id="learn_confirm_rotating",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SIGNAL_REPETITIONS,
                        default=DEFAULT_SIGNAL_REPETITIONS,
                    ): int,
                    vol.Required(
                        CONF_DEVICE_TYPE,
                        default=self._data.get(
                            CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
                        ),
                    ): vol.In(DEVICE_TYPE_OPTIONS),
                }
            ),
            description_placeholders={
                "codes_on": codes_on_str,
                "codes_on_count": str(len(codes_on)),
                "codes_off": codes_off_str,
                "codes_off_count": str(len(codes_off)),
                "protocol": str(self._data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)),
                "pulselength": str(self._data.get(CONF_PULSELENGTH, "—")),
            },
        )

    # --- Options flow ---

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RpiRfSwitchOptionsFlow:
        """Get the options flow handler."""
        return RpiRfSwitchOptionsFlow()


class RpiRfSwitchOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for editing entries."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Route to correct options step based on entry type."""
        data = {**self.config_entry.data, **self.config_entry.options}
        entry_type = data.get(CONF_ENTRY_TYPE)

        if entry_type == ENTRY_TYPE_TX:
            return await self.async_step_tx_options(user_input)
        if entry_type == ENTRY_TYPE_RX:
            return await self.async_step_rx_options(user_input)

        mode = data.get(CONF_MODE, MODE_DIRECT)
        if mode == MODE_DIP:
            return await self.async_step_dip_options(user_input)
        if CONF_CODES_ON in data:
            return await self.async_step_rotating_options(user_input)
        return await self.async_step_direct_options(user_input)

    async def async_step_tx_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit TX module GPIO."""
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="tx_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GPIO,
                        default=data.get(CONF_GPIO, DEFAULT_GPIO),
                    ): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                }
            ),
        )

    async def async_step_rx_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit RX module settings."""
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="rx_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GPIO,
                        default=data.get(CONF_GPIO, DEFAULT_RX_GPIO),
                    ): vol.In(
                        {pin: f"GPIO {pin}" for pin in GPIO_PINS}
                    ),
                    vol.Required(
                        CONF_RX_ENABLED,
                        default=data.get(CONF_RX_ENABLED, True),
                    ): bool,
                    vol.Required(
                        CONF_RX_DEBUG,
                        default=data.get(CONF_RX_DEBUG, False),
                    ): bool,
                }
            ),
        )

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

        # Show calculated codes in description
        code_on = data.get(CONF_CODE_ON, "?")
        code_off = data.get(CONF_CODE_OFF, "?")

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
            description_placeholders={
                "code_on": str(code_on),
                "code_off": str(code_off),
            },
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
                        default=data.get(
                            CONF_CODE_LENGTH, DEFAULT_CODE_LENGTH
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
        )

    async def async_step_rotating_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit rotating code device options (codes are read-only)."""
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            # Preserve all existing code data, only update editable fields
            result = {
                CONF_SIGNAL_REPETITIONS: user_input.get(
                    CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
                ),
                CONF_DEVICE_TYPE: user_input.get(
                    CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE
                ),
            }
            return self.async_create_entry(title="", data=result)

        codes_on = data.get(CONF_CODES_ON, [data.get(CONF_CODE_ON)])
        codes_off = data.get(CONF_CODES_OFF, [data.get(CONF_CODE_OFF)])
        codes_on_str = ", ".join(str(c) for c in codes_on)
        codes_off_str = ", ".join(str(c) for c in codes_off)

        return self.async_show_form(
            step_id="rotating_options",
            data_schema=vol.Schema(
                {
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
            description_placeholders={
                "codes_on": codes_on_str,
                "codes_on_count": str(len(codes_on)),
                "codes_off": codes_off_str,
                "codes_off_count": str(len(codes_off)),
                "protocol": str(data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)),
                "pulselength": str(data.get(CONF_PULSELENGTH, "—")),
            },
        )
