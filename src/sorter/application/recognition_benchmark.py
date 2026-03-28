from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
from typing import Iterable

from sorter.application.recognition_reporting import (
    classify_review_reason,
    summarize_confidence_bands,
    summarize_review_reasons,
)
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
    review_reason: str | None
    fallback_used: bool
    matched_name: bool
    image_available: bool
    alternatives: tuple[dict, ...]
    debug: dict


@dataclass(frozen=True)
class RecognitionBenchmarkSummary:
    backend: str
    scenario_name: str
    total_cases: int
    scored_cases: int
    exact_name_matches: int
    name_accuracy: float
    review_count: int
    low_confidence_count: int
    missing_prediction_count: int
    fallback_count: int
    missing_image_count: int
    average_confidence: float
    confidence_band_counts: dict[str, int]
    review_reason_counts: dict[str, int]
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
            "low_confidence_count": self.low_confidence_count,
            "missing_prediction_count": self.missing_prediction_count,
            "fallback_count": self.fallback_count,
            "missing_image_count": self.missing_image_count,
            "average_confidence": self.average_confidence,
            "confidence_band_counts": dict(self.confidence_band_counts),
            "review_reason_counts": dict(self.review_reason_counts),
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
        review_reason = classify_review_reason(frame, result)
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
                review_reason=review_reason,
                fallback_used=result.fallback_used,
                matched_name=result.card_name == expected_name,
                image_available=frame.path is not None,
                alternatives=tuple(result.alternatives),
                debug=dict(result.debug),
            )
        )

    scored_cases = len(cases)
    exact_name_matches = sum(1 for case in cases if case.matched_name)
    review_count = sum(1 for case in cases if case.needs_review)
    low_confidence_count = sum(1 for case in cases if case.review_reason == "confidence_below_threshold")
    missing_prediction_count = sum(1 for case in cases if case.review_reason == "missing_prediction_for_visible_card")
    fallback_count = sum(1 for case in cases if case.fallback_used)
    missing_image_count = sum(1 for case in cases if not case.image_available)
    average_confidence = sum(case.confidence for case in cases) / scored_cases if scored_cases else 0.0
    name_accuracy = exact_name_matches / scored_cases if scored_cases else 0.0
    confidence_band_counts = summarize_confidence_bands(case.confidence for case in cases)
    review_reason_counts = summarize_review_reasons(case.review_reason for case in cases)
    return RecognitionBenchmarkSummary(
        backend=settings.recognizer_backend,
        scenario_name=context.world.scenario_name,
        total_cases=scored_cases,
        scored_cases=scored_cases,
        exact_name_matches=exact_name_matches,
        name_accuracy=name_accuracy,
        review_count=review_count,
        low_confidence_count=low_confidence_count,
        missing_prediction_count=missing_prediction_count,
        fallback_count=fallback_count,
        missing_image_count=missing_image_count,
        average_confidence=average_confidence,
        confidence_band_counts=confidence_band_counts,
        review_reason_counts=review_reason_counts,
        cases=tuple(cases),
    )


def default_json_path(project_root: Path, backend: str) -> Path:
    return project_root / "data" / "recognition_reports" / f"{backend}_summary.json"


def default_artifact_path(project_root: Path, summary_name: str) -> Path:
    return project_root / "data" / "recognition_reports" / "artifacts" / summary_name


def write_benchmark_artifacts(
    summary: RecognitionBenchmarkSummary,
    artifact_root: Path,
) -> Path:
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest_payload = summary.to_dict()
    for case in summary.cases:
        case_dir = artifact_root / f"{case.pile_key.replace(',', '_')}__{case.frame_id}"
        case_dir.mkdir(parents=True, exist_ok=True)
        case_payload = asdict(case)
        (case_dir / "case.json").write_text(
            json.dumps(case_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if case.frame_path:
            source_path = Path(case.frame_path)
            if source_path.exists():
                shutil.copy2(source_path, case_dir / f"frame{source_path.suffix.lower() or '.jpg'}")
        if case.alternatives:
            (case_dir / "alternatives.json").write_text(
                json.dumps(list(case.alternatives), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        if case.debug:
            (case_dir / "debug.json").write_text(
                json.dumps(case.debug, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            ocr_lines = case.debug.get("ocr_lines")
            if isinstance(ocr_lines, list) and ocr_lines:
                (case_dir / "ocr_lines.txt").write_text(
                    "\n".join(str(line) for line in ocr_lines),
                    encoding="utf-8",
                )
            bbox = case.debug.get("bbox")
            if bbox is not None:
                (case_dir / "bbox.json").write_text(
                    json.dumps({"bbox": bbox}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
    (artifact_root / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact_root
