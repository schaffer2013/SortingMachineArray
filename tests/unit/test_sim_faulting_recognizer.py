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
