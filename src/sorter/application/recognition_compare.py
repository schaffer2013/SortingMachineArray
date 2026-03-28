from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RecognitionComparisonCase:
    pile_key: str
    expected_name: str | None
    baseline_name: str | None
    candidate_name: str | None
    baseline_confidence: float
    candidate_confidence: float
    baseline_review: bool
    candidate_review: bool
    name_changed: bool
    confidence_delta: float


@dataclass(frozen=True)
class RecognitionComparisonSummary:
    baseline_backend: str
    candidate_backend: str
    scenario_name: str
    total_compared_cases: int
    changed_prediction_count: int
    candidate_review_reduction: int
    confidence_delta_average: float
    cases: tuple[RecognitionComparisonCase, ...]

    def to_dict(self) -> dict:
        return {
            "baseline_backend": self.baseline_backend,
            "candidate_backend": self.candidate_backend,
            "scenario_name": self.scenario_name,
            "total_compared_cases": self.total_compared_cases,
            "changed_prediction_count": self.changed_prediction_count,
            "candidate_review_reduction": self.candidate_review_reduction,
            "confidence_delta_average": self.confidence_delta_average,
            "cases": [asdict(case) for case in self.cases],
        }


def compare_recognition_summaries(
    baseline_summary_path: Path,
    candidate_summary_path: Path,
) -> RecognitionComparisonSummary:
    baseline = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_summary_path.read_text(encoding="utf-8"))
    baseline_cases = {
        str(case.get("pile_key")): case
        for case in baseline.get("cases", [])
        if isinstance(case, dict) and case.get("pile_key") is not None
    }
    candidate_cases = {
        str(case.get("pile_key")): case
        for case in candidate.get("cases", [])
        if isinstance(case, dict) and case.get("pile_key") is not None
    }

    compared_cases: list[RecognitionComparisonCase] = []
    for pile_key in sorted(set(baseline_cases) & set(candidate_cases)):
        baseline_case = baseline_cases[pile_key]
        candidate_case = candidate_cases[pile_key]
        baseline_confidence = float(baseline_case.get("confidence", 0.0))
        candidate_confidence = float(candidate_case.get("confidence", 0.0))
        compared_cases.append(
            RecognitionComparisonCase(
                pile_key=pile_key,
                expected_name=baseline_case.get("expected_name"),
                baseline_name=baseline_case.get("predicted_name"),
                candidate_name=candidate_case.get("predicted_name"),
                baseline_confidence=baseline_confidence,
                candidate_confidence=candidate_confidence,
                baseline_review=bool(baseline_case.get("needs_review", False)),
                candidate_review=bool(candidate_case.get("needs_review", False)),
                name_changed=baseline_case.get("predicted_name") != candidate_case.get("predicted_name"),
                confidence_delta=round(candidate_confidence - baseline_confidence, 4),
            )
        )

    total_compared_cases = len(compared_cases)
    changed_prediction_count = sum(1 for case in compared_cases if case.name_changed)
    candidate_review_reduction = sum(
        1 for case in compared_cases if case.baseline_review and not case.candidate_review
    )
    confidence_delta_average = (
        round(sum(case.confidence_delta for case in compared_cases) / total_compared_cases, 4)
        if total_compared_cases
        else 0.0
    )
    return RecognitionComparisonSummary(
        baseline_backend=str(baseline.get("backend", "baseline")),
        candidate_backend=str(candidate.get("backend", "candidate")),
        scenario_name=str(candidate.get("scenario_name") or baseline.get("scenario_name") or "unknown"),
        total_compared_cases=total_compared_cases,
        changed_prediction_count=changed_prediction_count,
        candidate_review_reduction=candidate_review_reduction,
        confidence_delta_average=confidence_delta_average,
        cases=tuple(compared_cases),
    )
