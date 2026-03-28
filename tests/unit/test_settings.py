from __future__ import annotations

from sorter.config.settings import AppSettings


def test_app_settings_from_env_reads_recognizer_backend_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("SORTER_RECOGNIZER_BACKEND", "fuzzy_enigma")
    monkeypatch.setenv("SORTER_CARD_ENGINE_CONFIG", "config/card_engine/engine.json")
    monkeypatch.setenv("SORTER_CARD_ENGINE_MODE", "small_pool")
    monkeypatch.setenv("SORTER_CARD_ENGINE_AUTO_TRACK_RESULTS", "1")
    monkeypatch.setenv("SORTER_CARD_ENGINE_PREFER_VISUAL_SMALL_POOL", "true")

    settings = AppSettings.from_env(project_root=tmp_path)

    assert settings.recognizer_backend == "fuzzy_enigma"
    assert settings.card_engine_config_path == tmp_path / "config/card_engine/engine.json"
    assert settings.card_engine_mode == "small_pool"
    assert settings.card_engine_auto_track_results is True
    assert settings.card_engine_prefer_visual_small_pool is True
