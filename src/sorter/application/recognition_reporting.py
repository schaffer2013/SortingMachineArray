from __future__ import annotations

from typing import Iterable


def classify_review_reason(frame, result) -> str | None:
    if not result.needs_review:
        return None
    engine_error_code = result.debug.get("engine_error_code")
    if isinstance(engine_error_code, str) and engine_error_code:
        return engine_error_code
    policy = result.debug.get("policy")
    if isinstance(policy, dict):
        reason = policy.get("reason")
        if isinstance(reason, str) and reason:
            return reason
    sim_fault = result.debug.get("sim_fault")
    if isinstance(sim_fault, dict):
        fault_type = sim_fault.get("type")
        if isinstance(fault_type, str) and fault_type:
            return fault_type
    expected_name = frame.metadata.get("card_name")
    if result.card_name is None and expected_name is not None:
        return "missing_prediction_for_visible_card"
    if result.card_name is None:
        return "empty_prediction_below_threshold"
    return "confidence_below_threshold"


def confidence_band_for(confidence: float) -> str:
    if confidence < 0.50:
        return "lt_050"
    if confidence < 0.70:
        return "050_to_069"
    if confidence < 0.85:
        return "070_to_084"
    return "085_plus"


def summarize_confidence_bands(confidences: Iterable[float]) -> dict[str, int]:
    bands = {
        "lt_050": 0,
        "050_to_069": 0,
        "070_to_084": 0,
        "085_plus": 0,
    }
    for confidence in confidences:
        increment_counter(bands, confidence_band_for(confidence))
    return bands


def summarize_review_reasons(reasons: Iterable[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in reasons:
        if reason is None:
            continue
        increment_counter(counts, reason)
    return counts


def increment_counter(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1
