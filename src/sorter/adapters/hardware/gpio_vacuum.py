from __future__ import annotations


class GpioVacuumAdapter:
    def __init__(self, relay_pin: int = 17):
        self.relay_pin = relay_pin
        self._state = False

    def on(self) -> None:
        self._state = True

    def off(self) -> None:
        self._state = False

    def is_on(self) -> bool:
        return self._state
