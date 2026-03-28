from __future__ import annotations

from dataclasses import replace

from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class PolicyRecognizerAdapter:
    def __init__(
        self,
        primary,
        *,
        min_confidence: float,
        fallback=None,
    ) -> None:
        self.primary = primary
        self.min_confidence = min_confidence
        self.fallback = fallback

    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        primary_result = self.primary.recognize_top_card(frame)
        if self._is_acceptable(frame, primary_result):
            return primary_result

        if self.fallback is not None and self._should_try_fallback(frame, primary_result):
            fallback_result = self.fallback.recognize_top_card(frame)
            return replace(
                fallback_result,
                fallback_used=True,
                requested_mode=primary_result.requested_mode or fallback_result.requested_mode,
                effective_mode=primary_result.effective_mode or fallback_result.effective_mode,
                mode_features=primary_result.mode_features or fallback_result.mode_features,
                debug={
                    "fallback_reason": self._fallback_reason(frame, primary_result),
                    "primary_backend": primary_result.backend,
                    "primary_confidence": primary_result.confidence,
                    "primary_card_name": primary_result.card_name,
                    "primary_requested_mode": primary_result.requested_mode,
                    "primary_effective_mode": primary_result.effective_mode,
                    "fallback_backend": fallback_result.backend,
                    "fallback_result": dict(fallback_result.debug),
                },
            )

        return replace(
            primary_result,
            needs_review=True,
            debug={
                **dict(primary_result.debug),
                "policy": {
                    "accepted": False,
                    "min_confidence": self.min_confidence,
                    "reason": self._fallback_reason(frame, primary_result),
                },
            },
        )

    def _is_acceptable(self, frame: Frame, result: RecognitionResult) -> bool:
        expected_name = frame.metadata.get("card_name")
        if result.card_name is None:
            return expected_name is None and result.confidence >= self.min_confidence
        return result.confidence >= self.min_confidence

    def _should_try_fallback(self, frame: Frame, result: RecognitionResult) -> bool:
        expected_name = frame.metadata.get("card_name")
        if result.card_name is None:
            return expected_name is not None
        return result.confidence < self.min_confidence

    def _fallback_reason(self, frame: Frame, result: RecognitionResult) -> str:
        expected_name = frame.metadata.get("card_name")
        if result.card_name is None and expected_name is not None:
            return "missing_prediction_for_visible_card"
        if result.card_name is None:
            return "empty_prediction_below_threshold"
        return "confidence_below_threshold"
