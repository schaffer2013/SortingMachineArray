from __future__ import annotations

from sorter.domain.machine_state import NextMove
from sorter.ports.camera import CameraPort
from sorter.ports.recognizer import RecognizerPort


def verify_move(move: NextMove, camera: CameraPort, recognizer: RecognizerPort) -> tuple[bool, float, str | None]:
    frame = camera.capture_top_card(move.from_pile)
    result = recognizer.recognize_top_card(frame)
    if result.confidence < 0.6:
        return False, result.confidence, result.card_name
    return True, result.confidence, result.card_name
