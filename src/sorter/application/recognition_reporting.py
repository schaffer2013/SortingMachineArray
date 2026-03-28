from __future__ import annotations

from typing import Iterable


_REVIEW_REASON_FAMILIES = {
    "candidate_tie_unresolved": "perception",
    "deadline_exceeded": "perception",
    "detection_failed": "perception",
    "empty_prediction_below_threshold": "policy",
    "expected_card_contradicted": "perception",
    "expected_card_not_found": "policy",
    "missing_candidate_pool_or_expected_card": "policy",
    "missing_expected_card": "policy",
    "missing_prediction_for_visible_card": "policy",
    "missing_tracked_pool": "policy",
    "ocr_weak": "perception",
    "recognition_ambiguous_candidates": "perception",
    "recognition_confirmation_contradiction": "perception",
    "recognition_false_empty": "perception",
    "confidence_below_threshold": "policy",
}


def classify_review_reason(frame, result) -> str | None:
    if not result.needs_review:
        return None
    if isinstance(result.review_reason, str) and result.review_reason:
        return result.review_reason
    if isinstance(result.failure_code, str) and result.failure_code:
        return result.failure_code
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


def review_reason_family(reason: str | None) -> str | None:
    if reason is None:
        return None
    return _REVIEW_REASON_FAMILIES.get(reason, "unknown")


def recommend_recovery_action(frame, result) -> str | None:
    reason = classify_review_reason(frame, result)
    if reason is None:
        return None
    if reason == "missing_tracked_pool":
        return "seed_candidate_pool_or_disable_small_pool"
    if reason in {"missing_expected_card", "missing_candidate_pool_or_expected_card"}:
        return "attach_expected_card_or_switch_mode"
    if reason == "expected_card_not_found":
        return "verify_expected_identity_against_catalog"
    if reason == "expected_card_contradicted":
        return "operator_confirm_or_retry_confirmation"
    if reason in {"candidate_tie_unresolved", "recognition_ambiguous_candidates"}:
        return "capture_additional_signal"
    if reason in {"detection_failed", "ocr_weak", "deadline_exceeded"}:
        return "rescan_with_more_budget"
    if reason in {"missing_prediction_for_visible_card", "recognition_false_empty"}:
        return "rescan_visible_card"
    if reason in {"confidence_below_threshold", "empty_prediction_below_threshold"}:
        return "retry_or_operator_review"
    return "operator_review"


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


def summarize_review_families(reasons: Iterable[str | None]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in reasons:
        family = review_reason_family(reason)
        if family is None:
            continue
        increment_counter(counts, family)
    return counts


def increment_counter(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1
