from __future__ import annotations

from typing import Protocol


class LightsPort(Protocol):
    def set_status(self, status: str) -> None: ...
