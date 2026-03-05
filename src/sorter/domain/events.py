from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    payload: dict[str, Any]
    ts: str

    @staticmethod
    def now(event_type: str, payload: dict[str, Any]) -> "DomainEvent":
        return DomainEvent(event_type=event_type, payload=payload, ts=datetime.now(UTC).isoformat())
