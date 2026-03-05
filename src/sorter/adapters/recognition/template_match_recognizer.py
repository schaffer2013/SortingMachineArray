from __future__ import annotations

from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class TemplateMatchRecognizer:
    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        card_name = frame.metadata.get("card_name")
        if card_name is None:
            return RecognitionResult(card_name=None, confidence=1.0)
        return RecognitionResult(card_name=card_name, confidence=0.7)
