from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sorter.ports.camera import Frame


@dataclass(frozen=True)
class RecognitionResult:
    card_name: str | None
    confidence: float
    backend: str = "unknown"
    scryfall_id: str | None = None
    oracle_id: str | None = None
    requested_mode: str | None = None
    effective_mode: str | None = None
    mode_flags: dict[str, bool] = field(default_factory=dict)
    mode_features: tuple[str, ...] = field(default_factory=tuple)
    pipeline_summary: dict[str, Any] = field(default_factory=dict)
    failure_code: str | None = None
    review_reason: str | None = None
    needs_review: bool = False
    fallback_used: bool = False
    alternatives: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    debug: dict[str, Any] = field(default_factory=dict)


class RecognizerPort(Protocol):
    def recognize_top_card(self, frame: Frame) -> RecognitionResult: ...
