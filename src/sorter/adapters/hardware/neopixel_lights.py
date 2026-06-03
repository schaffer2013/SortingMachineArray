from __future__ import annotations

from sorter.adapters.hardware.marlin_transport import MarlinTransport, RecordingMarlinTransport


class NeoPixelLightsAdapter:
    """Marlin-style neopixel control for boards like BTT SKR 1.4 Turbo.

    Uses status -> RGB mapping and sends generated `M150` commands through the
    shared Marlin transport used by motion when hardware wiring is active.
    """

    STATUS_RGB = {
        "idle": (0, 0, 16),
        "running": (0, 16, 0),
        "warning": (16, 8, 0),
        "fault": (16, 0, 0),
    }

    def __init__(self, transport: MarlinTransport | None = None):
        self.transport = transport or RecordingMarlinTransport()
        self.last_status = "idle"
        self.last_profile = "idle"
        self.last_rgb = self.STATUS_RGB["idle"]
        self.last_command = "M150 R0 U0 B16"

    def set_status(self, status: str) -> None:
        self.last_status = status
        r, g, b = self.STATUS_RGB.get(status, self.STATUS_RGB["warning"])
        self.last_profile = status
        self.last_rgb = (r, g, b)
        self._send_rgb(r, g, b)

    def set_rgb(self, red: int, green: int, blue: int, *, profile_name: str | None = None) -> None:
        r, g, b = (_clamp_channel(red), _clamp_channel(green), _clamp_channel(blue))
        self.last_status = profile_name or "custom"
        self.last_profile = profile_name or "custom"
        self.last_rgb = (r, g, b)
        self._send_rgb(r, g, b)

    def _send_rgb(self, red: int, green: int, blue: int) -> None:
        self.last_command = f"M150 R{red} U{green} B{blue}"
        self.transport.send_command(self.last_command)


def _clamp_channel(value: int) -> int:
    return max(0, min(255, int(value)))
