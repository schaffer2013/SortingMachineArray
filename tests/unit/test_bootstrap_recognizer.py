from __future__ import annotations

from pathlib import Path

from sorter.bootstrap import _build_recognizer
from sorter.config.settings import AppSettings
from sorter.adapters.recognition.policy_recognizer import PolicyRecognizerAdapter


def _settings(tmp_path: Path, *, recognizer_backend: str) -> AppSettings:
    return AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=tmp_path / "scenarios/fixtures/small_stack.json",
        card_catalog_path=tmp_path / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "data/runs.sqlite3",
        calibration_path=tmp_path / "config/calibration.json",
        sort_policy_path=tmp_path / "config/sort_policies/default_color_then_alpha.json",
        project_root=tmp_path,
        recognizer_backend=recognizer_backend,
        card_engine_config_path=tmp_path / "config/card_engine/engine.json",
        card_engine_mode="greenfield",
        card_engine_auto_track_results=True,
        card_engine_prefer_visual_small_pool=True,
        recognition_min_confidence=0.77,
        fuzzy_enigma_sim_truth_fallback=False,
    )


def test_build_recognizer_selects_sim_truth_backend(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    class FakeSimRecognizer:
        def __init__(self, world, catalog):
            seen["world"] = world
            seen["catalog"] = catalog

    monkeypatch.setattr("sorter.bootstrap.SimRecognizerAdapter", FakeSimRecognizer)

    recognizer = _build_recognizer(_settings(tmp_path, recognizer_backend="sim_truth"), world="world", catalog="catalog")

    assert isinstance(recognizer, FakeSimRecognizer)
    assert seen["world"] == "world"
    assert seen["catalog"] == "catalog"


def test_build_recognizer_selects_fuzzy_enigma_backend(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    class FakeFuzzyRecognizer:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("sorter.bootstrap.FuzzyEnigmaRecognizerAdapter", FakeFuzzyRecognizer)

    recognizer = _build_recognizer(_settings(tmp_path, recognizer_backend="fuzzy_enigma"), world="world", catalog="catalog")

    assert isinstance(recognizer, PolicyRecognizerAdapter)
    assert isinstance(recognizer.primary, FakeFuzzyRecognizer)
    assert recognizer.fallback is None
    assert recognizer.min_confidence == 0.77
    assert seen["project_root"] == tmp_path
    assert seen["config_path"] == tmp_path / "config/card_engine/engine.json"
    assert seen["mode"] == "greenfield"
    assert seen["auto_track_results"] is True
    assert seen["prefer_visual_small_pool"] is True


def test_build_recognizer_can_enable_sim_truth_fallback(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    class FakeFuzzyRecognizer:
        def __init__(self, **kwargs):
            seen["fuzzy_kwargs"] = kwargs

    class FakeSimRecognizer:
        def __init__(self, world, catalog):
            seen["fallback_world"] = world
            seen["fallback_catalog"] = catalog

    settings = _settings(tmp_path, recognizer_backend="fuzzy_enigma")
    settings = AppSettings(**{**settings.__dict__, "fuzzy_enigma_sim_truth_fallback": True})

    monkeypatch.setattr("sorter.bootstrap.FuzzyEnigmaRecognizerAdapter", FakeFuzzyRecognizer)
    monkeypatch.setattr("sorter.bootstrap.SimRecognizerAdapter", FakeSimRecognizer)

    recognizer = _build_recognizer(settings, world="world", catalog="catalog")

    assert isinstance(recognizer, PolicyRecognizerAdapter)
    assert isinstance(recognizer.primary, FakeFuzzyRecognizer)
    assert isinstance(recognizer.fallback, FakeSimRecognizer)
    assert seen["fallback_world"] == "world"
    assert seen["fallback_catalog"] == "catalog"
