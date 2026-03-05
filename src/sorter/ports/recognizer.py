from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sorter.ports.camera import Frame


@dataclass(frozen=True)
class RecognitionResult:
    card_name: str | None
    confidence: float


class RecognizerPort(Protocol):
    def recognize_top_card(self, frame: Frame) -> RecognitionResult: ...
