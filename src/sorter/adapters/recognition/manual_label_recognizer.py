from __future__ import annotations

from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class ManualLabelRecognizer:
    def __init__(self, fallback_name: str | None = None):
        self.fallback_name = fallback_name

    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        return RecognitionResult(card_name=self.fallback_name, confidence=1.0 if self.fallback_name else 0.0)
