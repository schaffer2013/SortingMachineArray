from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from sorter.application.recognition_benchmark import (
    RecognitionBenchmarkCase,
    RecognitionBenchmarkSummary,
    default_portable_report_path,
    run_sim_recognition_benchmark,
    write_benchmark_artifacts,
    write_portable_report,
)
from sorter.domain.enums import PileRole
from sorter.domain.models import MachineSnapshot, PileId, PileState
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


def test_run_sim_recognition_benchmark_summarizes_review_reasons_and_confidence_bands(monkeypatch, tmp_path):
    pile_a = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10)
    pile_b = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10)
    snapshot = MachineSnapshot(
        piles={
            pile_a.pile_id.as_key(): pile_a,
            pile_b.pile_id.as_key(): pile_b,
        }
    )
    frame_path = tmp_path / "card.jpg"
    frame_path.write_bytes(b"fake-image")
    frames = {
        "0,0": Frame(
            frame_id="frame-a",
            path=str(frame_path),
            pile_id=pile_a.pile_id,
            metadata={"card_name": "Opt"},
        ),
        "1,0": Frame(
            frame_id="frame-b",
            path=str(frame_path),
            pile_id=pile_b.pile_id,
            metadata={"card_name": "Island"},
        ),
    }
    results = {
        "frame-a": RecognitionResult(
            card_name="Opt",
            confidence=0.91,
            backend="fuzzy_enigma",
            requested_mode="greenfield",
            effective_mode="greenfield",
            mode_features=("prefer_visual_small_pool",),
            needs_review=False,
        ),
        "frame-b": RecognitionResult(
            card_name=None,
            confidence=0.22,
            backend="fuzzy_enigma",
            requested_mode="small_pool",
            effective_mode="greenfield",
            mode_features=("has_candidate_pool",),
            needs_review=True,
            debug={"policy": {"reason": "missing_prediction_for_visible_card"}},
        ),
    }

    context = SimpleNamespace(
        world=SimpleNamespace(snapshot=snapshot, scenario_name="demo"),
        camera=SimpleNamespace(capture_top_card=lambda pile_id: frames[pile_id.as_key()]),
        recognizer=SimpleNamespace(recognize_top_card=lambda frame: results[frame.frame_id]),
    )
    monkeypatch.setattr(
        "sorter.application.recognition_benchmark.build_sim_runtime_context",
        lambda settings: context,
    )

    summary = run_sim_recognition_benchmark(
        SimpleNamespace(recognizer_backend="fuzzy_enigma", card_engine_mode="greenfield")
    )

    assert summary.scored_cases == 2
    assert summary.review_count == 1
    assert summary.low_confidence_count == 0
    assert summary.missing_prediction_count == 1
    assert summary.confidence_band_counts == {
        "lt_050": 1,
        "050_to_069": 0,
        "070_to_084": 0,
        "085_plus": 1,
    }
    assert summary.review_reason_counts == {"missing_prediction_for_visible_card": 1}
    assert summary.review_family_counts == {"policy": 1}
    assert summary.effective_mode_counts == {"greenfield": 2}
    assert summary.requested_mode == "greenfield"
    assert summary.mode_request_options == {"mode": "greenfield", "use_expected_label": False}
    assert summary.cases[0].requested_mode == "greenfield"
    assert summary.cases[1].effective_mode == "greenfield"
    assert summary.cases[1].review_reason == "missing_prediction_for_visible_card"
    assert summary.cases[0].mode_request == {"mode": "greenfield"}


def test_run_sim_recognition_benchmark_can_attach_expected_card_requests(monkeypatch, tmp_path):
    pile = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10)
    snapshot = MachineSnapshot(piles={pile.pile_id.as_key(): pile})
    frame_path = tmp_path / "card.jpg"
    frame_path.write_bytes(b"fake-image")
    captured_frames: list[Frame] = []

    def _recognize(frame: Frame) -> RecognitionResult:
        captured_frames.append(frame)
        return RecognitionResult(
            card_name="Alpha",
            confidence=0.82,
            backend="fuzzy_enigma",
            requested_mode="small_pool",
            effective_mode="small_pool",
        )

    context = SimpleNamespace(
        world=SimpleNamespace(snapshot=snapshot, scenario_name="demo"),
        camera=SimpleNamespace(
            capture_top_card=lambda pile_id: Frame(
                frame_id="frame-a",
                path=str(frame_path),
                pile_id=pile_id,
                metadata={
                    "card_name": "Alpha",
                    "set_code": "lea",
                    "scryfall_id": "alpha-printing-id",
                    "oracle_id": "alpha-oracle-id",
                },
            )
        ),
        recognizer=SimpleNamespace(recognize_top_card=_recognize),
    )
    monkeypatch.setattr(
        "sorter.application.recognition_benchmark.build_sim_runtime_context",
        lambda settings: context,
    )

    summary = run_sim_recognition_benchmark(
        SimpleNamespace(recognizer_backend="fuzzy_enigma", card_engine_mode="small_pool"),
        use_expected_label=True,
    )

    assert summary.mode_request_options == {
        "mode": "small_pool",
        "use_expected_label": True,
        "use_tracked_pool": False,
    }
    assert captured_frames
    assert captured_frames[0].metadata["recognition_request"] == {
        "mode": "small_pool",
        "expected_card": {
            "scryfall_id": "alpha-printing-id",
            "oracle_id": "alpha-oracle-id",
            "name": "Alpha",
            "set_code": "lea",
        },
        "use_tracked_pool": False,
    }
    assert summary.cases[0].mode_request == {
        "mode": "small_pool",
        "expected_card": {
            "scryfall_id": "alpha-printing-id",
            "oracle_id": "alpha-oracle-id",
            "name": "Alpha",
            "set_code": "lea",
        },
        "use_tracked_pool": False,
    }


def test_write_benchmark_artifacts_exports_case_debug_files(tmp_path):
    frame_path = tmp_path / "source.jpg"
    frame_path.write_bytes(b"fake-image")
    summary = RecognitionBenchmarkSummary(
        schema_version=1,
        report_type="benchmark",
        generated_at_utc="2026-03-28T12:00:00+00:00",
        backend="fuzzy_enigma",
        scenario_name="demo",
        requested_mode="greenfield",
        mode_request_options={"mode": "greenfield", "use_expected_label": False},
        total_cases=1,
        scored_cases=1,
        exact_name_matches=1,
        name_accuracy=1.0,
        review_count=0,
        low_confidence_count=0,
        missing_prediction_count=0,
        fallback_count=0,
        missing_image_count=0,
        average_confidence=0.88,
        confidence_band_counts={"lt_050": 0, "050_to_069": 0, "070_to_084": 0, "085_plus": 1},
        review_reason_counts={},
        effective_mode_counts={"greenfield": 1},
        cases=(
            RecognitionBenchmarkCase(
                pile_key="0,0",
                frame_id="frame-1",
                frame_path=str(frame_path),
                expected_name="Opt",
                expected_scryfall_id="expected-id",
                expected_oracle_id="expected-oracle",
                predicted_name="Opt",
                predicted_scryfall_id="predicted-id",
                predicted_oracle_id="predicted-oracle",
                confidence=0.88,
                backend="fuzzy_enigma",
                requested_mode="greenfield",
                effective_mode="greenfield",
                mode_features=("prefer_visual_small_pool",),
                needs_review=False,
                review_reason=None,
                fallback_used=False,
                matched_name=True,
                image_available=True,
                alternatives=({"name": "Opt", "score": 0.88},),
                mode_request={"mode": "greenfield"},
                debug={"ocr_lines": ["Opt"], "bbox": [1, 2, 3, 4], "active_roi": "title"},
            ),
        ),
    )

    artifact_root = write_benchmark_artifacts(summary, tmp_path / "artifacts")
    case_dir = artifact_root / "0_0__frame-1"

    assert json.loads((artifact_root / "manifest.json").read_text(encoding="utf-8"))["backend"] == "fuzzy_enigma"
    assert (case_dir / "frame.jpg").exists()
    assert (case_dir / "case.json").exists()
    assert (case_dir / "alternatives.json").exists()
    assert (case_dir / "debug.json").exists()
    assert (case_dir / "ocr_lines.txt").read_text(encoding="utf-8") == "Opt"
    assert json.loads((case_dir / "bbox.json").read_text(encoding="utf-8")) == {"bbox": [1, 2, 3, 4]}


def test_write_portable_report_splits_success_and_failure_cases(tmp_path):
    summary = RecognitionBenchmarkSummary(
        schema_version=1,
        report_type="benchmark",
        generated_at_utc="2026-03-28T12:00:00+00:00",
        backend="fuzzy_enigma",
        scenario_name="demo",
        requested_mode="small_pool",
        mode_request_options={"mode": "small_pool", "use_expected_label": True, "use_tracked_pool": False},
        total_cases=2,
        scored_cases=2,
        exact_name_matches=1,
        name_accuracy=0.5,
        review_count=1,
        low_confidence_count=1,
        missing_prediction_count=0,
        fallback_count=0,
        missing_image_count=0,
        average_confidence=0.52,
        confidence_band_counts={"lt_050": 1, "050_to_069": 0, "070_to_084": 0, "085_plus": 1},
        review_reason_counts={"confidence_below_threshold": 1},
        review_family_counts={"policy": 1},
        effective_mode_counts={"greenfield": 2},
        cases=(
            RecognitionBenchmarkCase(
                pile_key="0,0",
                frame_id="frame-ok",
                frame_path="C:/tmp/ok.jpg",
                expected_name="Opt",
                expected_scryfall_id=None,
                expected_oracle_id=None,
                predicted_name="Opt",
                predicted_scryfall_id="opt-id",
                predicted_oracle_id="oracle-opt",
                confidence=0.91,
                backend="fuzzy_enigma",
                requested_mode="small_pool",
                effective_mode="greenfield",
                mode_features=("has_candidate_pool",),
                needs_review=False,
                review_reason=None,
                fallback_used=False,
                matched_name=True,
                image_available=True,
                alternatives=(),
                mode_request={"mode": "small_pool"},
                debug={},
            ),
            RecognitionBenchmarkCase(
                pile_key="1,0",
                frame_id="frame-bad",
                frame_path="C:/tmp/bad.jpg",
                expected_name="Island",
                expected_scryfall_id=None,
                expected_oracle_id=None,
                predicted_name="Opt",
                predicted_scryfall_id="opt-id",
                predicted_oracle_id="oracle-opt",
                confidence=0.13,
                backend="fuzzy_enigma",
                requested_mode="small_pool",
                effective_mode="greenfield",
                mode_features=("has_candidate_pool",),
                needs_review=True,
                review_reason="confidence_below_threshold",
                review_family="policy",
                recovery_action="retry_or_operator_review",
                fallback_used=False,
                matched_name=False,
                image_available=True,
                alternatives=(),
                mode_request={"mode": "small_pool"},
                debug={},
            ),
        ),
    )

    output_path = write_portable_report(
        summary,
        default_portable_report_path(tmp_path, "portable-test"),
        artifact_root=tmp_path / "artifacts",
        card_engine_config_path="config/card_engine/benchmark.engine.json",
        project_root=tmp_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["requested_mode"] == "small_pool"
    assert payload["mode_request_options"] == {"mode": "small_pool", "use_expected_label": True, "use_tracked_pool": False}
    assert payload["summary"]["review_count"] == 1
    assert payload["summary"]["effective_mode_counts"] == {"greenfield": 2}
    assert payload["summary"]["review_family_counts"] == {"policy": 1}
    assert len(payload["success_cases"]) == 1
    assert len(payload["failure_cases"]) == 1
    assert payload["failure_cases"][0]["review_reason"] == "confidence_below_threshold"
    assert payload["failure_cases"][0]["review_family"] == "policy"
    assert payload["failure_cases"][0]["recovery_action"] == "retry_or_operator_review"
    assert payload["failure_cases"][0]["requested_mode"] == "small_pool"
    assert payload["failure_cases"][0]["mode_request"] == {"mode": "small_pool"}
