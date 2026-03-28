from __future__ import annotations

from sorter.adapters.sim.sim_faulting_recognizer import SimFaultingRecognizerAdapter
from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


class _Recognizer:
    def recognize_top_card(self, frame):
        return RecognitionResult(card_name="Opt", confidence=1.0, backend="sim_truth")


def test_sim_faulting_recognizer_can_force_low_confidence_review():
    adapter = SimFaultingRecognizerAdapter(
        _Recognizer(),
        (
            {
                "type": "recognition_low_confidence",
                "pile": "0,0",
                "confidence": 0.15,
            },
        ),
    )

    result = adapter.recognize_top_card(Frame(frame_id="frame-1", path="x.jpg", pile_id=PileId(0, 0)))

    assert result.card_name == "Opt"
    assert result.confidence == 0.15
    assert result.needs_review is True


def test_sim_faulting_recognizer_can_force_missing_prediction():
    adapter = SimFaultingRecognizerAdapter(
        _Recognizer(),
        (
            {
                "type": "recognition_missing_prediction",
                "pile": "0,0",
            },
        ),
    )

    result = adapter.recognize_top_card(Frame(frame_id="frame-1", path="x.jpg", pile_id=PileId(0, 0)))

    assert result.card_name is None
    assert result.confidence == 0.0
    assert result.needs_review is True


def test_sim_faulting_recognizer_can_force_false_empty():
    adapter = SimFaultingRecognizerAdapter(
        _Recognizer(),
        (
            {
                "type": "recognition_false_empty",
                "pile": "0,0",
                "confidence": 0.97,
            },
        ),
    )

    result = adapter.recognize_top_card(Frame(frame_id="frame-1", path="x.jpg", pile_id=PileId(0, 0)))

    assert result.card_name is None
    assert result.confidence == 0.97
    assert result.needs_review is True


def test_sim_faulting_recognizer_can_force_ambiguous_candidates():
    adapter = SimFaultingRecognizerAdapter(
        _Recognizer(),
        (
            {
                "type": "recognition_ambiguous_candidates",
                "pile": "0,0",
                "confidence": 0.41,
                "alternatives": ["Alpha", "Beta"],
            },
        ),
    )

    result = adapter.recognize_top_card(Frame(frame_id="frame-1", path="x.jpg", pile_id=PileId(0, 0)))

    assert result.card_name == "Opt"
    assert result.confidence == 0.41
    assert result.needs_review is True
    assert [entry["name"] for entry in result.alternatives] == ["Alpha", "Beta"]


def test_sim_faulting_recognizer_can_force_confirmation_contradiction_for_matching_mode():
    adapter = SimFaultingRecognizerAdapter(
        _Recognizer(),
        (
            {
                "type": "recognition_confirmation_contradiction",
                "pile": "0,0",
                "requested_mode": "confirmation",
                "predicted_name": "Wrong Card",
            },
        ),
    )

    result = adapter.recognize_top_card(
        Frame(
            frame_id="frame-1",
            path="x.jpg",
            pile_id=PileId(0, 0),
            metadata={"recognition_request": {"mode": "confirmation"}},
        )
    )

    assert result.card_name == "Wrong Card"
    assert result.needs_review is True
    assert result.debug["policy"]["reason"] == "expected_card_contradicted"
