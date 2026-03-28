from __future__ import annotations

from sorter.domain.machine_state import NextMove
from sorter.ports.camera import CameraPort, Frame
from sorter.ports.recognizer import RecognitionResult, RecognizerPort


def verify_move(
    move: NextMove,
    camera: CameraPort,
    recognizer: RecognizerPort,
    *,
    min_confidence: float = 0.6,
) -> tuple[bool, RecognitionResult, Frame]:
    frame = camera.capture_top_card(move.from_pile)
    result = recognizer.recognize_top_card(frame)
    if result.needs_review:
        return False, result, frame
    if result.confidence < min_confidence:
        return False, result, frame
    return True, result, frame
