from __future__ import annotations

from sorter.application.recognition_reporting import (
    classify_review_reason,
    recommend_recovery_action,
    review_reason_family,
)
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


def test_review_reason_family_prefers_structured_review_reason():
    frame = Frame(frame_id="frame-1", path="C:/tmp/card.jpg", pile_id=None, metadata={"card_name": "Opt"})
    result = RecognitionResult(
        card_name=None,
        confidence=0.2,
        backend="fuzzy_enigma",
        review_reason="missing_tracked_pool",
        needs_review=True,
    )

    reason = classify_review_reason(frame, result)

    assert reason == "missing_tracked_pool"
    assert review_reason_family(reason) == "policy"
    assert recommend_recovery_action(frame, result) == "seed_candidate_pool_or_disable_small_pool"


def test_review_reason_family_handles_perception_failures():
    frame = Frame(frame_id="frame-2", path="C:/tmp/card.jpg", pile_id=None, metadata={"card_name": "Opt"})
    result = RecognitionResult(
        card_name="Opt",
        confidence=0.5,
        backend="fuzzy_enigma",
        review_reason="candidate_tie_unresolved",
        needs_review=True,
    )

    reason = classify_review_reason(frame, result)

    assert reason == "candidate_tie_unresolved"
    assert review_reason_family(reason) == "perception"
    assert recommend_recovery_action(frame, result) == "capture_additional_signal"
