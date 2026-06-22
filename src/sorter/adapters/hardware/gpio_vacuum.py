from __future__ import annotations


class GpioVacuumAdapter:
    def __init__(self, relay_pin: int = 17, *, active_high: bool = True):
        self.relay_pin = relay_pin
        self.active_high = active_high
        self._state = False
        self._device = self._open_device()

    def on(self) -> None:
        self._state = True
        self._device.on()

    def off(self) -> None:
        self._state = False
        self._device.off()

    def is_on(self) -> bool:
        return self._state

    def close(self) -> None:
        close = getattr(self._device, "close", None)
        if callable(close):
            close()

    def _open_device(self):
        try:
            from gpiozero import OutputDevice
        except Exception as exc:  # pragma: no cover - requires Raspberry Pi GPIO stack
            raise RuntimeError(
                "GPIO vacuum hardware backend is unavailable. Install gpiozero/RPi GPIO support on the Raspberry Pi."
            ) from exc
        return OutputDevice(self.relay_pin, active_high=self.active_high, initial_value=False)
