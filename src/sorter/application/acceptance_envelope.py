from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


LEGACY_FUZZY_BASELINE = 0.167
GREENFIELD_MIN_ACCURACY = 0.50
GOLDEN_SMALL_POOL_MIN_ACCURACY = 0.75
GOLDEN_SMALL_POOL_MAX_REVIEW_COUNT = 1


@dataclass(frozen=True)
class AcceptanceGate:
    name: str
    passed: bool
    details: dict[str, object]


@dataclass(frozen=True)
class AcceptanceEnvelope:
    generated_at_utc: str
    overall_passed: bool
    gates: tuple[AcceptanceGate, ...]

    def to_dict(self) -> dict:
        return {
            "generated_at_utc": self.generated_at_utc,
            "overall_passed": self.overall_passed,
            "gates": [asdict(gate) for gate in self.gates],
        }


def evaluate_acceptance_envelope(
    *,
    pytest_passed: bool,
    sim_truth_summary: dict,
    fuzzy_greenfield_summary: dict,
    fuzzy_small_pool_summary: dict,
    fuzzy_golden_small_pool_summary: dict,
) -> AcceptanceEnvelope:
    gates = (
        AcceptanceGate(
            name="pytest_suite",
            passed=pytest_passed,
            details={"expected": True, "actual": pytest_passed},
        ),
        AcceptanceGate(
            name="sim_truth_accuracy",
            passed=float(sim_truth_summary.get("name_accuracy", 0.0)) == 1.0,
            details={
                "expected_accuracy": 1.0,
                "actual_accuracy": float(sim_truth_summary.get("name_accuracy", 0.0)),
            },
        ),
        AcceptanceGate(
            name="fuzzy_greenfield_outperforms_legacy_floor",
            passed=float(fuzzy_greenfield_summary.get("name_accuracy", 0.0)) >= GREENFIELD_MIN_ACCURACY,
            details={
                "legacy_floor": LEGACY_FUZZY_BASELINE,
                "minimum_accuracy": GREENFIELD_MIN_ACCURACY,
                "actual_accuracy": float(fuzzy_greenfield_summary.get("name_accuracy", 0.0)),
            },
        ),
        AcceptanceGate(
            name="fuzzy_small_pool_expected_not_worse_than_greenfield",
            passed=float(fuzzy_small_pool_summary.get("name_accuracy", 0.0))
            >= float(fuzzy_greenfield_summary.get("name_accuracy", 0.0)),
            details={
                "greenfield_accuracy": float(fuzzy_greenfield_summary.get("name_accuracy", 0.0)),
                "small_pool_accuracy": float(fuzzy_small_pool_summary.get("name_accuracy", 0.0)),
            },
        ),
        AcceptanceGate(
            name="fuzzy_golden_small_pool_quality",
            passed=(
                float(fuzzy_golden_small_pool_summary.get("name_accuracy", 0.0)) >= GOLDEN_SMALL_POOL_MIN_ACCURACY
                and int(fuzzy_golden_small_pool_summary.get("review_count", 0)) <= GOLDEN_SMALL_POOL_MAX_REVIEW_COUNT
            ),
            details={
                "minimum_accuracy": GOLDEN_SMALL_POOL_MIN_ACCURACY,
                "maximum_review_count": GOLDEN_SMALL_POOL_MAX_REVIEW_COUNT,
                "actual_accuracy": float(fuzzy_golden_small_pool_summary.get("name_accuracy", 0.0)),
                "actual_review_count": int(fuzzy_golden_small_pool_summary.get("review_count", 0)),
            },
        ),
    )
    return AcceptanceEnvelope(
        generated_at_utc=datetime.now(UTC).isoformat(),
        overall_passed=all(gate.passed for gate in gates),
        gates=gates,
    )
