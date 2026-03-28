from __future__ import annotations

from sorter.adapters.recognition.policy_recognizer import PolicyRecognizerAdapter
from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class StaticRecognizer:
    def __init__(self, result: RecognitionResult):
        self.result = result

    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        return self.result


def test_policy_recognizer_marks_low_confidence_result_for_review():
    primary = StaticRecognizer(
        RecognitionResult(
            card_name="Opt",
            confidence=0.41,
            backend="fuzzy_enigma",
            requested_mode="small_pool",
            effective_mode="greenfield",
            mode_features=("has_candidate_pool",),
        )
    )
    adapter = PolicyRecognizerAdapter(primary, min_confidence=0.6)
    frame = Frame(
        frame_id="frame-1",
        path="C:/tmp/card.jpg",
        pile_id=PileId(0, 0),
        metadata={"card_name": "Opt", "mode": "sim"},
    )

    result = adapter.recognize_top_card(frame)

    assert result.needs_review is True
    assert result.fallback_used is False
    assert result.requested_mode == "small_pool"
    assert result.effective_mode == "greenfield"
    assert result.debug["policy"]["reason"] == "confidence_below_threshold"


def test_policy_recognizer_can_fallback_to_sim_truth_for_visible_sim_card():
    primary = StaticRecognizer(
        RecognitionResult(
            card_name="Opt",
            confidence=0.41,
            backend="fuzzy_enigma",
            requested_mode="confirmation",
            effective_mode="confirmation",
            mode_features=("has_expected_card",),
        )
    )
    fallback = StaticRecognizer(
        RecognitionResult(
            card_name="Opt",
            confidence=1.0,
            backend="sim_truth",
            scryfall_id="opt-id",
            requested_mode="sim_truth",
            effective_mode="sim_truth",
        )
    )
    adapter = PolicyRecognizerAdapter(primary, min_confidence=0.6, fallback=fallback)
    frame = Frame(
        frame_id="frame-1",
        path="C:/tmp/card.jpg",
        pile_id=PileId(0, 0),
        metadata={"card_name": "Opt", "mode": "sim"},
    )

    result = adapter.recognize_top_card(frame)

    assert result.card_name == "Opt"
    assert result.backend == "sim_truth"
    assert result.fallback_used is True
    assert result.requested_mode == "confirmation"
    assert result.effective_mode == "confirmation"
    assert result.debug["fallback_reason"] == "confidence_below_threshold"
