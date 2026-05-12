"""433 MHz RF receiver for state synchronization and code learning."""
from __future__ import annotations

import importlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

TX_GUARD_SECONDS = 0.5


@dataclass
class ReceivedCode:
    """A received RF code with metadata."""

    code: int
    protocol: int
    pulselength: int
    timestamp: float = field(default_factory=time.monotonic)


class RFReceiver:
    """Background 433 MHz RF receiver.

    Runs a polling thread that reads codes from an rpi-rf RFDevice in RX mode.
    Supports:
    - Registered callbacks for real-time state sync
    - Capture buffer for learn mode
    - TX guard to ignore self-received codes
    """

    def __init__(self, gpio: int) -> None:
        """Initialize the receiver on the given GPIO pin."""
        self._gpio = gpio
        self._rfdevice = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[int, int, int], None]] = []
        self._callbacks_lock = threading.Lock()
        self._tx_guard_until: float = 0.0
        self._capturing = False
        self._capture_buffer: list[ReceivedCode] = []

    @property
    def gpio(self) -> int:
        """Return the GPIO pin number."""
        return self._gpio

    def start(self) -> None:
        """Start the receiver background thread."""
        if self._running:
            return

        rpi_rf = importlib.import_module("rpi_rf")
        self._rfdevice = rpi_rf.RFDevice(self._gpio)
        self._rfdevice.enable_rx()
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="rf_receiver"
        )
        self._thread.start()
        _LOGGER.info("RF receiver started on GPIO %s", self._gpio)

    def stop(self) -> None:
        """Stop the receiver (uses disable_rx to avoid GPIO.cleanup)."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        if self._rfdevice is not None:
            self._rfdevice.disable_rx()
            self._rfdevice = None
        _LOGGER.info("RF receiver stopped on GPIO %s", self._gpio)

    def set_tx_guard(self) -> None:
        """Ignore received codes for a short period (call before TX)."""
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

    def _listen_loop(self) -> None:
        """Main receiver loop (runs in background thread)."""
        last_timestamp = None

        while self._running:
            if self._rfdevice is None:
                break

            if self._rfdevice.rx_code_timestamp != last_timestamp:
                last_timestamp = self._rfdevice.rx_code_timestamp
                code = self._rfdevice.rx_code
                protocol = self._rfdevice.rx_proto
                pulselength = self._rfdevice.rx_pulselength

                if not code:
                    continue

                # Skip self-received codes during/after TX
                if time.monotonic() < self._tx_guard_until:
                    _LOGGER.debug("RX ignored (TX guard): code=%s", code)
                    continue

                _LOGGER.debug(
                    "RX code=%s proto=%s pulse=%s",
                    code,
                    protocol,
                    pulselength,
                )

                if self._capturing:
                    self._capture_buffer.append(
                        ReceivedCode(code, protocol, pulselength)
                    )

                with self._callbacks_lock:
                    for cb in list(self._callbacks):
                        try:
                            cb(code, protocol, pulselength)
                        except Exception:
                            _LOGGER.exception("Error in RX callback")

            time.sleep(0.01)
