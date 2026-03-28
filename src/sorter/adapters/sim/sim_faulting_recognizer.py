from __future__ import annotations

from dataclasses import replace


class SimFaultingRecognizerAdapter:
    def __init__(self, recognizer, faults: tuple[dict, ...]):
        self.recognizer = recognizer
        self._faults = [dict(fault) for fault in faults]
        self._recognition_count = 0

    def recognize_top_card(self, frame):
        result = self.recognizer.recognize_top_card(frame)
        self._recognition_count += 1
        pile_key = frame.pile_id.as_key() if frame.pile_id is not None else None
        for fault in self._faults:
            if not self._matches_fault(fault, pile_key):
                continue
            self._consume_fault(fault)
            return self._apply_fault(result, fault)
        return result

    def _matches_fault(self, fault: dict, pile_key: str | None) -> bool:
        fault_pile = fault.get("pile")
        if fault_pile and fault_pile != pile_key:
            return False
        after_recognition = int(fault.get("after_recognition", 1))
        return self._recognition_count >= after_recognition

    def _consume_fault(self, fault: dict) -> None:
        remaining = int(fault.get("times", 1))
        if remaining <= 1:
            fault["_consumed"] = True
            self._faults = [entry for entry in self._faults if not entry.get("_consumed")]
            return
        fault["times"] = remaining - 1

    def _apply_fault(self, result, fault: dict):
        fault_type = str(fault.get("type", ""))
        if fault_type == "recognition_low_confidence":
            forced_confidence = float(fault.get("confidence", 0.2))
            return replace(
                result,
                confidence=forced_confidence,
                needs_review=True,
                debug={**dict(result.debug), "sim_fault": dict(fault)},
            )
        if fault_type == "recognition_missing_prediction":
            return replace(
                result,
                card_name=None,
                confidence=0.0,
                scryfall_id=None,
                oracle_id=None,
                needs_review=True,
                alternatives=(),
                debug={**dict(result.debug), "sim_fault": dict(fault)},
            )
        return result
