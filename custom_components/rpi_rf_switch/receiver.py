"""433 MHz RF receiver with polling-based decoder.

Replaces rpi-rf's RX edge-detection which depends on GPIO.add_event_detect()
(broken on Linux kernel 6.12+, HA OS 17+). Uses direct GPIO polling instead.

Decodes PT2262 and compatible protocols by analyzing pulse timing patterns.
Supports all 6 rpi-rf protocols.
"""
from __future__ import annotations

import importlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

TX_GUARD_SECONDS = 0.5

# Noise filter: require N identical codes within a time window before
# firing callbacks. Learn mode capture is unfiltered (uses Counter).
CONFIRM_COUNT = 3
CONFIRM_WINDOW = 2.0  # seconds

# A pulse longer than this (µs) is treated as a sync gap.
# Covers protocols 1,2,3,5,6. Protocol 4 (sync_low=2280µs) is marginal.
SYNC_GAP_US = 4000

# Timing tolerance for protocol matching (60%)
TOLERANCE = 0.60

# Protocol definitions from rpi-rf.
# Pulse ratios relative to base pulse length T.
# sync_low: sync gap duration in multiples of T
# zero_high/zero_low: bit '0' HIGH/LOW duration ratios
# one_high/one_low: bit '1' HIGH/LOW duration ratios
PROTOCOLS = [
    None,  # index 0 unused
    {"sync_low": 31, "zero_high": 1, "zero_low": 3,
     "one_high": 3, "one_low": 1},   # 1: PT2262 ~350µs
    {"sync_low": 10, "zero_high": 1, "zero_low": 3,
     "one_high": 3, "one_low": 1},   # 2: ~650µs
    {"sync_low": 71, "zero_high": 4, "zero_low": 11,
     "one_high": 9, "one_low": 6},   # 3: ~100µs
    {"sync_low": 6,  "zero_high": 1, "zero_low": 3,
     "one_high": 3, "one_low": 1},   # 4: ~380µs
    {"sync_low": 14, "zero_high": 1, "zero_low": 2,
     "one_high": 2, "one_low": 1},   # 5: ~500µs
    {"sync_low": 28, "zero_high": 1, "zero_low": 3,
     "one_high": 3, "one_low": 1},   # 6: HT6P20B ~200µs
]

MAX_CHANGES = 67  # max pulse buffer (same as rpi-rf)
MIN_CHANGES = 48  # 24 bits × 2 pulses each


@dataclass
class ReceivedCode:
    """A received RF code with metadata."""

    code: int
    protocol: int
    pulselength: int
    timestamp: float = field(default_factory=time.monotonic)


class RFReceiver:
    """Background 433 MHz RF receiver using GPIO polling.

    Polls GPIO directly and decodes RF codes from pulse timing patterns.
    Drop-in replacement for the old rpi-rf based receiver.

    Supports:
    - Registered callbacks for real-time state sync (with noise filter)
    - Capture buffer for learn mode
    - TX guard to ignore self-received codes
    """

    def __init__(self, gpio: int) -> None:
        """Initialize the receiver on the given GPIO pin."""
        self._gpio = gpio
        self._GPIO = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[int, int, int], None]] = []
        self._callbacks_lock = threading.Lock()
        self._tx_guard_until: float = 0.0
        self._tx_active = False
        self._capturing = False
        self._capture_buffer: list[ReceivedCode] = []
        self._recent_codes: list[tuple[float, int]] = []

    @property
    def gpio(self) -> int:
        """Return the GPIO pin number."""
        return self._gpio

    def start(self) -> None:
        """Start the receiver background thread."""
        if self._running:
            return

        self._GPIO = importlib.import_module("RPi.GPIO")
        self._GPIO.setwarnings(False)
        self._GPIO.setmode(self._GPIO.BCM)
        self._GPIO.setup(self._gpio, self._GPIO.IN)

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="rf_rx_poller"
        )
        self._thread.start()
        _LOGGER.info("RF receiver (polling) started on GPIO %s", self._gpio)

    def stop(self) -> None:
        """Stop the receiver background thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        if self._GPIO is not None:
            try:
                self._GPIO.setup(self._gpio, self._GPIO.IN)
            except Exception:
                pass
        _LOGGER.info("RF receiver stopped on GPIO %s", self._gpio)

    def set_tx_guard(self) -> None:
        """Pause polling and ignore codes during TX.

        The polling loop releases the GIL infrequently (~1.4ms).
        This starves rpi-rf's TX timing (350µs pulses) of GIL time,
        corrupting RF signals. Pausing the loop during TX prevents this.
        """
        self._tx_active = True
        self._tx_guard_until = 0.0

    def clear_tx_guard(self) -> None:
        """Resume polling after TX with a short cooldown."""
        self._tx_active = False
        self._tx_guard_until = time.monotonic() + TX_GUARD_SECONDS

    def start_capture(self) -> None:
        """Start capturing received codes into a buffer (for learn mode)."""
        self._capture_buffer.clear()
        self._capturing = True

    def stop_capture(self) -> list[ReceivedCode]:
        """Stop capturing and return all captured codes."""
        self._capturing = False
        result = list(self._capture_buffer)
        self._capture_buffer.clear()
        return result

    def get_capture_snapshot(self) -> list[ReceivedCode]:
        """Return a copy of the current capture buffer without stopping."""
        return list(self._capture_buffer)

    def register_callback(
        self, callback: Callable[[int, int, int], None]
    ) -> Callable[[], None]:
        """Register a callback for received codes.

        Callback signature: (code, protocol, pulselength) -> None
        Returns an unregister function.
        """
        with self._callbacks_lock:
            self._callbacks.append(callback)

        def unregister() -> None:
            with self._callbacks_lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return unregister

    # --- Polling loop ---

    def _poll_loop(self) -> None:
        """Main polling loop — reads GPIO and decodes RF signals.

        Runs in a background thread. Detects signal transitions,
        records pulse durations, and decodes packets delimited by
        sync gaps.
        """
        GPIO = self._GPIO
        gpio_pin = self._gpio
        gpio_input = GPIO.input

        timings = [0] * MAX_CHANGES
        change_count = 0
        last_val = gpio_input(gpio_pin)
        last_time_ns = time.perf_counter_ns()
        idle_loops = 0

        while self._running:
            # Pause during TX to prevent GIL contention with RF timing
            if self._tx_active or time.monotonic() < self._tx_guard_until:
                time.sleep(0.05)
                change_count = 0
                last_val = gpio_input(gpio_pin)
                last_time_ns = time.perf_counter_ns()
                idle_loops = 0
                continue

            val = gpio_input(gpio_pin)
            if val == last_val:
                idle_loops += 1
                if idle_loops > 2000:
                    time.sleep(0)  # yield thread during idle
                    idle_loops = 0
                continue

            idle_loops = 0
            now_ns = time.perf_counter_ns()
            duration_us = (now_ns - last_time_ns) // 1000
            last_time_ns = now_ns
            last_val = val

            if duration_us > SYNC_GAP_US:
                # Sync gap detected — decode accumulated packet
                if change_count >= MIN_CHANGES:
                    self._try_decode(timings, change_count, duration_us)
                change_count = 0
            elif change_count < MAX_CHANGES:
                timings[change_count] = duration_us
                change_count += 1

    # --- Decoder ---

    def _try_decode(
        self, timings: list[int], count: int, sync_duration: int
    ) -> None:
        """Try to decode an RF code from recorded pulse timings.

        After a sync gap, the timings buffer contains alternating
        HIGH and LOW pulse durations. Each pair encodes one binary bit.
        We try all protocol definitions to find a match.
        """
        num_bits = count // 2

        for proto_num in range(1, len(PROTOCOLS)):
            proto = PROTOCOLS[proto_num]
            if proto is None:
                continue

            # Calculate base pulse length T from sync gap duration
            pulse_t = sync_duration / proto["sync_low"]
            if pulse_t < 50 or pulse_t > 1500:
                continue  # unreasonable pulse length

            tol = pulse_t * TOLERANCE
            code = 0
            matched = True

            for i in range(num_bits):
                idx = i * 2
                if idx + 1 >= count:
                    matched = False
                    break

                t_high = timings[idx]
                t_low = timings[idx + 1]

                # Check for '1' bit
                if (abs(t_high - proto["one_high"] * pulse_t) < tol and
                        abs(t_low - proto["one_low"] * pulse_t) < tol):
                    code = (code << 1) | 1
                # Check for '0' bit
                elif (abs(t_high - proto["zero_high"] * pulse_t) < tol and
                        abs(t_low - proto["zero_low"] * pulse_t) < tol):
                    code = code << 1
                else:
                    matched = False
                    break

            if matched and code != 0:
                self._on_code_decoded(code, proto_num, int(pulse_t))
                return

    # --- Code handling ---

    def _on_code_decoded(
        self, code: int, protocol: int, pulselength: int
    ) -> None:
        """Handle a successfully decoded code.

        Always adds to capture buffer (for learn mode).
        Only fires callbacks after noise filter confirms the code.
        """
        now = time.monotonic()

        # Skip self-received codes during/after TX
        if self._tx_active or now < self._tx_guard_until:
            _LOGGER.debug("RX ignored (TX guard): code=%s", code)
            return

        _LOGGER.debug(
            "RX code=%s proto=%s pulse=%s",
            code, protocol, pulselength,
        )

        # Capture mode: store all codes (Counter handles noise)
        if self._capturing:
            self._capture_buffer.append(
                ReceivedCode(code, protocol, pulselength)
            )

        # Noise filter for callbacks: require CONFIRM_COUNT identical
        # codes within CONFIRM_WINDOW seconds
        self._recent_codes.append((now, code))
        cutoff = now - CONFIRM_WINDOW
        self._recent_codes = [
            (t, c) for t, c in self._recent_codes if t > cutoff
        ]
        recent_count = sum(1 for _, c in self._recent_codes if c == code)

        if recent_count < CONFIRM_COUNT:
            return

        _LOGGER.debug(
            "RX confirmed code=%s (%dx in %.1fs)",
            code, recent_count, CONFIRM_WINDOW,
        )
        # Clear this code from window to avoid rapid re-triggering
        self._recent_codes = [
            (t, c) for t, c in self._recent_codes if c != code
        ]

        with self._callbacks_lock:
            for cb in list(self._callbacks):
                try:
                    cb(code, protocol, pulselength)
                except Exception:
                    _LOGGER.exception("Error in RX callback")
