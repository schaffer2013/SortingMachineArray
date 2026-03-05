from __future__ import annotations


class NeoPixelLightsAdapter:
    """Marlin-style neopixel control for boards like BTT SKR 1.4 Turbo.

    Uses status -> RGB mapping and exposes a generated `M150` command string.
    Integrate with the same serial transport used by motion when hardware wiring is active.
    """

    STATUS_RGB = {
        "idle": (0, 0, 16),
        "running": (0, 16, 0),
        "warning": (16, 8, 0),
        "fault": (16, 0, 0),
    }

    def __init__(self):
        self.last_status = "idle"
        self.last_command = "M150 R0 U0 B16"

    def set_status(self, status: str) -> None:
        self.last_status = status
        r, g, b = self.STATUS_RGB.get(status, self.STATUS_RGB["warning"])
        self.last_command = f"M150 R{r} U{g} B{b}"
