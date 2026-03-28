from __future__ import annotations

from sorter.domain.models import MachineSnapshot
from sorter.ports.camera import CameraPort
from sorter.ports.recognizer import RecognizerPort


def discover_top_cards(snapshot: MachineSnapshot, camera: CameraPort, recognizer: RecognizerPort) -> dict[str, str | None]:
    discovered: dict[str, str | None] = {}
    for pile in snapshot.piles.values():
        frame = camera.capture_top_card(pile.pile_id)
        result = recognizer.recognize_top_card(frame)
        discovered[pile.pile_id.as_key()] = result.card_name
        if result.card_name is None:
            pile.mark_empty_confirmed(confidence=result.confidence, source="discover_layout", frame_id=frame.frame_id)
        else:
            pile.mark_top_card_seen(
                card_name=result.card_name,
                confidence=result.confidence,
                source="discover_layout",
                frame_id=frame.frame_id,
            )
    return discovered
