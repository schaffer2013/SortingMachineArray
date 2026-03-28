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
        requested_mode = _requested_mode(frame, result)
        for fault in self._faults:
            if not self._matches_fault(fault, pile_key, requested_mode):
                continue
            self._consume_fault(fault)
            return self._apply_fault(result, fault)
        return result

    def _matches_fault(self, fault: dict, pile_key: str | None, requested_mode: str | None) -> bool:
        fault_pile = fault.get("pile")
        if fault_pile and fault_pile != pile_key:
            return False
        fault_mode = fault.get("requested_mode")
        if fault_mode and fault_mode != requested_mode:
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
        if fault_type == "recognition_false_empty":
            forced_confidence = float(fault.get("confidence", 0.95))
            return replace(
                result,
                card_name=None,
                confidence=forced_confidence,
                scryfall_id=None,
                oracle_id=None,
                needs_review=True,
                alternatives=(),
                debug={**dict(result.debug), "sim_fault": dict(fault)},
            )
        if fault_type == "recognition_ambiguous_candidates":
            forced_confidence = float(fault.get("confidence", 0.49))
            alternatives = _alternatives_from_fault(fault, result)
            ambiguous_name = str(fault.get("predicted_name") or (result.card_name or _first_alternative_name(alternatives) or "ambiguous"))
            return replace(
                result,
                card_name=ambiguous_name,
                confidence=forced_confidence,
                needs_review=True,
                alternatives=alternatives or result.alternatives,
                debug={**dict(result.debug), "sim_fault": dict(fault)},
            )
        if fault_type == "recognition_confirmation_contradiction":
            forced_confidence = float(fault.get("confidence", 0.91))
            contradiction_name = str(fault.get("predicted_name") or "contradiction")
            policy = dict(result.debug.get("policy") or {})
            policy["reason"] = "expected_card_contradicted"
            return replace(
                result,
                card_name=contradiction_name,
                confidence=forced_confidence,
                needs_review=True,
                debug={**dict(result.debug), "policy": policy, "sim_fault": dict(fault)},
            )
        return result


def _requested_mode(frame, result) -> str | None:
    request = frame.metadata.get("recognition_request")
    if isinstance(request, dict):
        mode = request.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    mode = getattr(result, "requested_mode", None)
    if isinstance(mode, str) and mode.strip():
        return mode.strip()
    return None


def _alternatives_from_fault(fault: dict, result) -> tuple[dict, ...]:
    raw = fault.get("alternatives")
    if not isinstance(raw, list):
        return tuple(result.alternatives)
    alternatives: list[dict] = []
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            alternatives.append({"name": entry.strip(), "score": 0.5})
            continue
        if isinstance(entry, dict):
            name = entry.get("name")
            score = entry.get("score", 0.5)
            if isinstance(name, str) and name.strip():
                alternatives.append({"name": name.strip(), "score": float(score)})
    return tuple(alternatives)


def _first_alternative_name(alternatives: tuple[dict, ...]) -> str | None:
    if not alternatives:
        return None
    name = alternatives[0].get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None
