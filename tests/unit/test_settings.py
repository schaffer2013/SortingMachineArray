from __future__ import annotations

import json

from sorter.config.settings import AppSettings


def test_app_settings_from_env_reads_recognizer_backend_controls(monkeypatch, tmp_path):
    monkeypatch.setenv("SORTER_RECOGNIZER_BACKEND", "fuzzy_enigma")
    monkeypatch.setenv("SORTER_CARD_ENGINE_CONFIG", "config/card_engine/engine.json")
    monkeypatch.setenv("SORTER_CARD_ENGINE_MODE", "small_pool")
    monkeypatch.setenv("SORTER_CARD_ENGINE_AUTO_TRACK_RESULTS", "1")
    monkeypatch.setenv("SORTER_CARD_ENGINE_PREFER_VISUAL_SMALL_POOL", "true")
    monkeypatch.setenv("SORTER_RECOGNITION_MIN_CONFIDENCE", "0.72")
    monkeypatch.setenv("SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK", "1")

    settings = AppSettings.from_env(project_root=tmp_path)

    assert settings.recognizer_backend == "fuzzy_enigma"
    assert settings.card_engine_config_path == tmp_path / "config/card_engine/engine.json"
    assert settings.card_engine_mode == "small_pool"
    assert settings.card_engine_auto_track_results is True
    assert settings.card_engine_prefer_visual_small_pool is True
    assert settings.recognition_min_confidence == 0.72
    assert settings.fuzzy_enigma_sim_truth_fallback is True


def test_app_settings_reads_default_recognition_policy_from_file(monkeypatch, tmp_path):
    policy_path = tmp_path / "config" / "vision" / "recognition_thresholds.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "verification_min_confidence": 0.67,
                "allow_sim_truth_fallback": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("SORTER_RECOGNITION_MIN_CONFIDENCE", raising=False)
    monkeypatch.delenv("SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK", raising=False)

    settings = AppSettings.from_env(project_root=tmp_path)

    assert settings.recognition_thresholds_path == policy_path
    assert settings.recognition_min_confidence == 0.67
    assert settings.fuzzy_enigma_sim_truth_fallback is True
