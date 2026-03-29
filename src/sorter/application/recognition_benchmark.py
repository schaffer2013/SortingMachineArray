from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, UTC
import json
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

from sorter.application.recognition_reporting import (
    classify_review_reason,
    recommend_recovery_action,
    summarize_confidence_bands,
    summarize_review_families,
    summarize_review_reasons,
    review_reason_family,
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
    requested_mode: str | None
    effective_mode: str | None
    mode_flags: dict[str, bool] = field(default_factory=dict)
    mode_features: tuple[str, ...] = field(default_factory=tuple)
    pipeline_summary: dict = field(default_factory=dict)
    failure_code: str | None = None
    engine_review_reason: str | None = None
    needs_review: bool = False
    review_reason: str | None = None
    review_family: str | None = None
    recovery_action: str | None = None
    fallback_used: bool = False
    matched_name: bool = False
    image_available: bool = False
    alternatives: tuple[dict, ...] = field(default_factory=tuple)
    debug: dict = field(default_factory=dict)
    mode_request: dict[str, object] = field(default_factory=dict)
    pile_number: int | None = None
    pile_label: str | None = None


@dataclass(frozen=True)
class RecognitionBenchmarkSummary:
    schema_version: int
    report_type: str
    generated_at_utc: str
    backend: str
    scenario_name: str
    requested_mode: str | None
    mode_request_options: dict[str, object]
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
    confidence_band_counts: dict[str, int] = field(default_factory=dict)
    review_reason_counts: dict[str, int] = field(default_factory=dict)
    review_family_counts: dict[str, int] = field(default_factory=dict)
    effective_mode_counts: dict[str, int] = field(default_factory=dict)
    cases: tuple[RecognitionBenchmarkCase, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "report_type": self.report_type,
            "generated_at_utc": self.generated_at_utc,
            "backend": self.backend,
            "scenario_name": self.scenario_name,
            "requested_mode": self.requested_mode,
            "mode_request_options": dict(self.mode_request_options),
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
            "review_family_counts": dict(self.review_family_counts),
            "effective_mode_counts": dict(self.effective_mode_counts),
            "cases": [asdict(case) for case in self.cases],
        }


def run_sim_recognition_benchmark(
    settings: AppSettings,
    *,
    pile_keys: Iterable[str] | None = None,
    include_empty: bool = False,
    report_type: str = "benchmark",
    use_expected_label: bool = False,
    use_tracked_pool: bool | None = None,
    track_result: bool | None = None,
    prefer_visual_small_pool: bool | None = None,
) -> RecognitionBenchmarkSummary:
    context = build_sim_runtime_context(settings)
    selected_piles = set(pile_keys) if pile_keys is not None else None
    cases: list[RecognitionBenchmarkCase] = []
    mode_request_options = _mode_request_options(
        settings,
        use_expected_label=use_expected_label,
        use_tracked_pool=use_tracked_pool,
        track_result=track_result,
        prefer_visual_small_pool=prefer_visual_small_pool,
    )

    ordered_piles = sorted(
        context.world.snapshot.piles.values(),
        key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()),
    )
    for index, pile in enumerate(ordered_piles, start=1):
        pile_key = pile.pile_id.as_key()
        if selected_piles is not None and pile_key not in selected_piles and str(index) not in selected_piles:
            continue
        frame = context.camera.capture_top_card(pile.pile_id)
        frame = _frame_with_recognition_request(
            frame,
            settings,
            use_expected_label=use_expected_label,
            use_tracked_pool=use_tracked_pool,
            track_result=track_result,
            prefer_visual_small_pool=prefer_visual_small_pool,
        )
        expected_name = frame.metadata.get("card_name")
        if expected_name is None and not include_empty:
            continue
        result = context.recognizer.recognize_top_card(frame)
        review_reason = classify_review_reason(frame, result)
        review_family = review_reason_family(review_reason)
        recovery_action = recommend_recovery_action(frame, result)
        cases.append(
            RecognitionBenchmarkCase(
                pile_key=pile_key,
                pile_number=index,
                pile_label=f"Pile {index}",
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
                requested_mode=result.requested_mode,
                effective_mode=result.effective_mode,
                mode_flags=dict(result.mode_flags),
                mode_features=tuple(result.mode_features),
                pipeline_summary=dict(result.pipeline_summary),
                failure_code=result.failure_code,
                engine_review_reason=result.review_reason,
                needs_review=result.needs_review,
                review_reason=review_reason,
                review_family=review_family,
                recovery_action=recovery_action,
                fallback_used=result.fallback_used,
                matched_name=result.card_name == expected_name,
                image_available=frame.path is not None,
                alternatives=tuple(result.alternatives),
                mode_request=_serialize_mode_request(frame.metadata.get("recognition_request")),
                debug=dict(result.debug),
            )
        )

    requested_mode = getattr(settings, "card_engine_mode", None) if settings.recognizer_backend == "fuzzy_enigma" else None
    if requested_mode is None:
        requested_modes = {case.requested_mode for case in cases if case.requested_mode}
        if len(requested_modes) == 1:
            requested_mode = next(iter(requested_modes))
    return summarize_recognition_cases(
        cases,
        backend=settings.recognizer_backend,
        scenario_name=context.world.scenario_name,
        report_type=report_type,
        requested_mode=requested_mode,
        mode_request_options=mode_request_options,
    )


def summarize_recognition_cases(
    cases: Iterable[RecognitionBenchmarkCase],
    *,
    backend: str,
    scenario_name: str,
    report_type: str,
    requested_mode: str | None,
    mode_request_options: dict[str, object] | None = None,
) -> RecognitionBenchmarkSummary:
    case_tuple = tuple(cases)
    scored_cases = len(case_tuple)
    exact_name_matches = sum(1 for case in case_tuple if case.matched_name)
    review_count = sum(1 for case in case_tuple if case.needs_review)
    low_confidence_count = sum(1 for case in case_tuple if case.review_reason == "confidence_below_threshold")
    missing_prediction_count = sum(1 for case in case_tuple if case.review_reason == "missing_prediction_for_visible_card")
    fallback_count = sum(1 for case in case_tuple if case.fallback_used)
    missing_image_count = sum(1 for case in case_tuple if not case.image_available)
    average_confidence = sum(case.confidence for case in case_tuple) / scored_cases if scored_cases else 0.0
    name_accuracy = exact_name_matches / scored_cases if scored_cases else 0.0
    confidence_band_counts = summarize_confidence_bands(case.confidence for case in case_tuple)
    review_reason_counts = summarize_review_reasons(case.review_reason for case in case_tuple)
    review_family_counts = summarize_review_families(case.review_reason for case in case_tuple)
    effective_mode_counts = summarize_review_reasons(case.effective_mode for case in case_tuple)
    return RecognitionBenchmarkSummary(
        schema_version=1,
        report_type=report_type,
        generated_at_utc=datetime.now(UTC).isoformat(),
        backend=backend,
        scenario_name=scenario_name,
        requested_mode=requested_mode,
        mode_request_options=dict(mode_request_options or {}),
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
        review_family_counts=review_family_counts,
        effective_mode_counts=effective_mode_counts,
        cases=case_tuple,
    )


def _frame_with_recognition_request(
    frame,
    settings: AppSettings,
    *,
    use_expected_label: bool,
    use_tracked_pool: bool | None,
    track_result: bool | None,
    prefer_visual_small_pool: bool | None,
):
    if settings.recognizer_backend != "fuzzy_enigma":
        return frame

    request: dict[str, object] = {}
    if settings.card_engine_mode:
            request["mode"] = settings.card_engine_mode
    if use_expected_label:
        expected_card = _expected_card_payload(frame)
        if expected_card:
            request["expected_card"] = expected_card
    if use_tracked_pool is not None:
        request["use_tracked_pool"] = use_tracked_pool
    elif settings.card_engine_mode == "small_pool" and use_expected_label:
        # Let small-pool experiments constrain by expected label instead of requiring pre-seeded tracking state.
        request["use_tracked_pool"] = False
    if track_result is not None:
        request["track_result"] = track_result
    if prefer_visual_small_pool is not None:
        request["prefer_visual_small_pool"] = prefer_visual_small_pool

    if not request:
        return frame
    metadata = dict(frame.metadata)
    metadata["recognition_request"] = request
    return replace(frame, metadata=metadata)


def _expected_card_payload(frame) -> dict[str, str] | None:
    scryfall_id = frame.metadata.get("scryfall_id")
    oracle_id = frame.metadata.get("oracle_id")
    name = frame.metadata.get("card_name")
    if not isinstance(name, str) and not isinstance(scryfall_id, str) and not isinstance(oracle_id, str):
        return None
    payload: dict[str, str] = {}
    if isinstance(scryfall_id, str) and scryfall_id.strip():
        payload["scryfall_id"] = scryfall_id.strip()
    if isinstance(oracle_id, str) and oracle_id.strip():
        payload["oracle_id"] = oracle_id.strip()
    if isinstance(name, str) and name.strip():
        payload["name"] = name.strip()
    set_code = frame.metadata.get("set_code")
    collector_number = frame.metadata.get("collector_number")
    if isinstance(set_code, str) and set_code.strip():
        payload["set_code"] = set_code.strip()
    if isinstance(collector_number, str) and collector_number.strip():
        payload["collector_number"] = collector_number.strip()
    return payload or None


def _mode_request_options(
    settings: AppSettings,
    *,
    use_expected_label: bool,
    use_tracked_pool: bool | None,
    track_result: bool | None,
    prefer_visual_small_pool: bool | None,
) -> dict[str, object]:
    if settings.recognizer_backend != "fuzzy_enigma":
        return {}
    options: dict[str, object] = {
        "mode": settings.card_engine_mode,
        "use_expected_label": use_expected_label,
    }
    if use_tracked_pool is not None:
        options["use_tracked_pool"] = use_tracked_pool
    elif settings.card_engine_mode == "small_pool" and use_expected_label:
        options["use_tracked_pool"] = False
    if track_result is not None:
        options["track_result"] = track_result
    if prefer_visual_small_pool is not None:
        options["prefer_visual_small_pool"] = prefer_visual_small_pool
    return options


def _serialize_mode_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, object] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            out[str(key)] = item
            continue
        if isinstance(item, dict):
            nested: dict[str, object] = {}
            for nested_key, nested_item in item.items():
                if isinstance(nested_item, (str, int, float, bool)) and nested_item is not None:
                    nested[str(nested_key)] = nested_item
            out[str(key)] = nested
    return out


def default_json_path(project_root: Path, backend: str) -> Path:
    return project_root / "data" / "recognition_reports" / f"{backend}_summary.json"


def default_artifact_path(project_root: Path, summary_name: str) -> Path:
    return project_root / "data" / "recognition_reports" / "artifacts" / summary_name


def default_portable_report_path(project_root: Path, summary_name: str) -> Path:
    return project_root / "data" / "recognition_reports" / "portable" / f"{summary_name}.portable.json"


def write_benchmark_artifacts(
    summary: RecognitionBenchmarkSummary,
    artifact_root: Path,
) -> Path:
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest_payload = summary.to_dict()
    for case in summary.cases:
        case_prefix = f"pile_{case.pile_number}" if case.pile_number is not None else case.pile_key.replace(",", "_")
        case_dir = artifact_root / f"{case_prefix}__{case.frame_id}"
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


def write_portable_report(
    summary: RecognitionBenchmarkSummary,
    output_path: Path,
    *,
    artifact_root: Path | None = None,
    card_engine_config_path: str | None = None,
    project_root: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_root_str = str(artifact_root) if artifact_root is not None else None
    payload = {
        "schema_version": 2,
        "report_type": summary.report_type,
        "generated_at_utc": summary.generated_at_utc,
        "backend": summary.backend,
        "scenario_name": summary.scenario_name,
        "requested_mode": summary.requested_mode,
        "mode_request_options": dict(summary.mode_request_options),
        "card_engine_config_path": card_engine_config_path,
        "submodule_sha": detect_submodule_sha(project_root) if project_root is not None else None,
        "summary": {
            "total_cases": summary.total_cases,
            "scored_cases": summary.scored_cases,
            "exact_name_matches": summary.exact_name_matches,
            "name_accuracy": summary.name_accuracy,
            "review_count": summary.review_count,
            "low_confidence_count": summary.low_confidence_count,
            "missing_prediction_count": summary.missing_prediction_count,
            "fallback_count": summary.fallback_count,
            "missing_image_count": summary.missing_image_count,
            "average_confidence": summary.average_confidence,
            "confidence_band_counts": dict(summary.confidence_band_counts),
            "review_reason_counts": dict(summary.review_reason_counts),
            "review_family_counts": dict(summary.review_family_counts),
            "effective_mode_counts": dict(summary.effective_mode_counts),
        },
        "success_cases": [
            _portable_case_dict(case, artifact_root_str=artifact_root_str)
            for case in summary.cases
            if not case.needs_review
        ],
        "failure_cases": [
            _portable_case_dict(case, artifact_root_str=artifact_root_str)
            for case in summary.cases
            if case.needs_review
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def detect_submodule_sha(project_root: Path) -> str | None:
    submodule_path = project_root / "third_party" / "fuzzy-enigma-card-recognition"
    if not submodule_path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(submodule_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = result.stdout.strip()
    return sha or None


def _portable_case_dict(case: RecognitionBenchmarkCase, *, artifact_root_str: str | None) -> dict:
    artifact_dir = None
    if artifact_root_str is not None:
        case_prefix = f"pile_{case.pile_number}" if case.pile_number is not None else case.pile_key.replace(",", "_")
        artifact_dir = str(Path(artifact_root_str) / f"{case_prefix}__{case.frame_id}")
    return {
        "pile_key": case.pile_key,
        "pile_number": case.pile_number,
        "pile_label": case.pile_label,
        "frame_id": case.frame_id,
        "frame_path": case.frame_path,
        "artifact_dir": artifact_dir,
        "expected_name": case.expected_name,
        "expected_scryfall_id": case.expected_scryfall_id,
        "expected_oracle_id": case.expected_oracle_id,
        "predicted_name": case.predicted_name,
        "predicted_scryfall_id": case.predicted_scryfall_id,
        "predicted_oracle_id": case.predicted_oracle_id,
        "confidence": case.confidence,
        "backend": case.backend,
        "requested_mode": case.requested_mode,
        "effective_mode": case.effective_mode,
        "mode_flags": dict(case.mode_flags),
        "mode_features": list(case.mode_features),
        "pipeline_summary": dict(case.pipeline_summary),
        "failure_code": case.failure_code,
        "engine_review_reason": case.engine_review_reason,
        "mode_request": dict(case.mode_request),
        "needs_review": case.needs_review,
        "review_reason": case.review_reason,
        "review_family": case.review_family,
        "recovery_action": case.recovery_action,
        "fallback_used": case.fallback_used,
        "matched_name": case.matched_name,
        "image_available": case.image_available,
        "alternatives": list(case.alternatives),
    }
