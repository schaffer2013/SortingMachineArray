from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from sorter.bootstrap import build_sim_runtime_context
from sorter.config.settings import AppSettings
from sorter.domain.models import PileId


@dataclass(frozen=True)
class RecognitionBenchmarkCase:
    pile_key: str
    frame_id: str
    frame_path: str | None
    expected_name: str | None
    expected_scryfall_id: str | None
    expected_oracle_id: str | None
    predicted_name: str | None
    predicted_scryfall_id: str | None
    predicted_oracle_id: str | None
    confidence: float
    backend: str
    needs_review: bool
    fallback_used: bool
    matched_name: bool
    image_available: bool


@dataclass(frozen=True)
class RecognitionBenchmarkSummary:
    backend: str
    scenario_name: str
    total_cases: int
    scored_cases: int
    exact_name_matches: int
    name_accuracy: float
    review_count: int
    fallback_count: int
    missing_image_count: int
    average_confidence: float
    cases: tuple[RecognitionBenchmarkCase, ...]

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "scenario_name": self.scenario_name,
            "total_cases": self.total_cases,
            "scored_cases": self.scored_cases,
            "exact_name_matches": self.exact_name_matches,
            "name_accuracy": self.name_accuracy,
            "review_count": self.review_count,
            "fallback_count": self.fallback_count,
            "missing_image_count": self.missing_image_count,
            "average_confidence": self.average_confidence,
            "cases": [asdict(case) for case in self.cases],
        }


def run_sim_recognition_benchmark(
    settings: AppSettings,
    *,
    pile_keys: Iterable[str] | None = None,
    include_empty: bool = False,
) -> RecognitionBenchmarkSummary:
    context = build_sim_runtime_context(settings)
    selected_piles = set(pile_keys) if pile_keys is not None else None
    cases: list[RecognitionBenchmarkCase] = []

    for pile in context.world.snapshot.piles.values():
        pile_key = pile.pile_id.as_key()
        if selected_piles is not None and pile_key not in selected_piles:
            continue
        frame = context.camera.capture_top_card(pile.pile_id)
        expected_name = frame.metadata.get("card_name")
        if expected_name is None and not include_empty:
            continue
        result = context.recognizer.recognize_top_card(frame)
        cases.append(
            RecognitionBenchmarkCase(
                pile_key=pile_key,
                frame_id=frame.frame_id,
                frame_path=frame.path,
                expected_name=expected_name,
                expected_scryfall_id=frame.metadata.get("scryfall_id"),
                expected_oracle_id=frame.metadata.get("oracle_id"),
                predicted_name=result.card_name,
                predicted_scryfall_id=result.scryfall_id,
                predicted_oracle_id=result.oracle_id,
                confidence=result.confidence,
                backend=result.backend,
                needs_review=result.needs_review,
                fallback_used=result.fallback_used,
                matched_name=result.card_name == expected_name,
                image_available=frame.path is not None,
            )
        )

    scored_cases = len(cases)
    exact_name_matches = sum(1 for case in cases if case.matched_name)
    review_count = sum(1 for case in cases if case.needs_review)
    fallback_count = sum(1 for case in cases if case.fallback_used)
    missing_image_count = sum(1 for case in cases if not case.image_available)
    average_confidence = sum(case.confidence for case in cases) / scored_cases if scored_cases else 0.0
    name_accuracy = exact_name_matches / scored_cases if scored_cases else 0.0
    return RecognitionBenchmarkSummary(
        backend=settings.recognizer_backend,
        scenario_name=context.world.scenario_name,
        total_cases=scored_cases,
        scored_cases=scored_cases,
        exact_name_matches=exact_name_matches,
        name_accuracy=name_accuracy,
        review_count=review_count,
        fallback_count=fallback_count,
        missing_image_count=missing_image_count,
        average_confidence=average_confidence,
        cases=tuple(cases),
    )


def default_json_path(project_root: Path, backend: str) -> Path:
    return project_root / "data" / "recognition_reports" / f"{backend}_summary.json"
