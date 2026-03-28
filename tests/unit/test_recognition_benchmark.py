from __future__ import annotations

from types import SimpleNamespace

from sorter.application.recognition_benchmark import run_sim_recognition_benchmark
from sorter.config.settings import AppSettings
from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


def _settings(tmp_path) -> AppSettings:
    return AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=tmp_path / "scenarios/fixtures/small_stack.json",
        card_catalog_path=tmp_path / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "data/runs.sqlite3",
        calibration_path=tmp_path / "config/calibration.json",
        sort_policy_path=tmp_path / "config/sort_policies/default_color_then_alpha.json",
        project_root=tmp_path,
        recognizer_backend="fuzzy_enigma",
    )


def test_run_sim_recognition_benchmark_summarizes_cases(monkeypatch, tmp_path):
    piles = [
        SimpleNamespace(pile_id=PileId(0, 0)),
        SimpleNamespace(pile_id=PileId(1, 0)),
    ]
    frames = {
        "0,0": Frame(
            frame_id="frame-1",
            path="C:/tmp/one.jpg",
            pile_id=PileId(0, 0),
            metadata={"card_name": "Opt", "scryfall_id": "opt-id", "oracle_id": "oracle-opt"},
        ),
        "1,0": Frame(
            frame_id="frame-2",
            path=None,
            pile_id=PileId(1, 0),
            metadata={"card_name": "Island", "scryfall_id": "island-id", "oracle_id": "oracle-island"},
        ),
    }
    results = {
        "0,0": RecognitionResult(card_name="Opt", confidence=0.95, backend="fuzzy_enigma"),
        "1,0": RecognitionResult(card_name="Island", confidence=1.0, backend="sim_truth", fallback_used=True),
    }

    context = SimpleNamespace(
        world=SimpleNamespace(scenario_name="demo", snapshot=SimpleNamespace(piles={"0,0": piles[0], "1,0": piles[1]})),
        camera=SimpleNamespace(capture_top_card=lambda pile_id: frames[pile_id.as_key()]),
        recognizer=SimpleNamespace(recognize_top_card=lambda frame: results[frame.pile_id.as_key()]),
    )
    monkeypatch.setattr("sorter.application.recognition_benchmark.build_sim_runtime_context", lambda settings: context)

    summary = run_sim_recognition_benchmark(_settings(tmp_path))

    assert summary.backend == "fuzzy_enigma"
    assert summary.scenario_name == "demo"
    assert summary.total_cases == 2
    assert summary.exact_name_matches == 2
    assert summary.name_accuracy == 1.0
    assert summary.fallback_count == 1
    assert summary.missing_image_count == 1


def test_run_sim_recognition_benchmark_can_skip_empty_cases(monkeypatch, tmp_path):
    context = SimpleNamespace(
        world=SimpleNamespace(
            scenario_name="demo",
            snapshot=SimpleNamespace(piles={"0,0": SimpleNamespace(pile_id=PileId(0, 0))}),
        ),
        camera=SimpleNamespace(
            capture_top_card=lambda pile_id: Frame(frame_id="frame-1", path=None, pile_id=pile_id, metadata={"card_name": None})
        ),
        recognizer=SimpleNamespace(
            recognize_top_card=lambda frame: RecognitionResult(card_name=None, confidence=1.0, backend="sim_truth")
        ),
    )
    monkeypatch.setattr("sorter.application.recognition_benchmark.build_sim_runtime_context", lambda settings: context)

    summary = run_sim_recognition_benchmark(_settings(tmp_path))

    assert summary.total_cases == 0
