from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from sorter.application.recognition_benchmark import (
    RecognitionBenchmarkCase,
    RecognitionBenchmarkSummary,
    run_sim_recognition_benchmark,
    write_benchmark_artifacts,
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
            needs_review=False,
        ),
        "frame-b": RecognitionResult(
            card_name=None,
            confidence=0.22,
            backend="fuzzy_enigma",
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

    summary = run_sim_recognition_benchmark(SimpleNamespace(recognizer_backend="fuzzy_enigma"))

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
    assert summary.cases[1].review_reason == "missing_prediction_for_visible_card"


def test_write_benchmark_artifacts_exports_case_debug_files(tmp_path):
    frame_path = tmp_path / "source.jpg"
    frame_path.write_bytes(b"fake-image")
    summary = RecognitionBenchmarkSummary(
        backend="fuzzy_enigma",
        scenario_name="demo",
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
                needs_review=False,
                review_reason=None,
                fallback_used=False,
                matched_name=True,
                image_available=True,
                alternatives=({"name": "Opt", "score": 0.88},),
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
