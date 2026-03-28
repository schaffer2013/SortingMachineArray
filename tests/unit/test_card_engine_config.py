from __future__ import annotations

from sorter.config.card_engine import (
    default_benchmark_card_engine_config_path,
    default_runtime_card_engine_config_path,
    resolve_card_engine_config_path,
)
from sorter.config.settings import AppSettings


def _settings(tmp_path, *, card_engine_config_path=None) -> AppSettings:
    return AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=tmp_path / "scenarios/fixtures/small_stack.json",
        card_catalog_path=tmp_path / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "data/runs.sqlite3",
        calibration_path=tmp_path / "config/calibration.json",
        sort_policy_path=tmp_path / "config/sort_policies/default_color_then_alpha.json",
        project_root=tmp_path,
        card_engine_config_path=card_engine_config_path,
    )


def test_resolve_card_engine_config_path_prefers_benchmark_default_for_benchmark_runs(tmp_path):
    benchmark_path = default_benchmark_card_engine_config_path(tmp_path)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_path.write_text("{}", encoding="utf-8")

    resolved = resolve_card_engine_config_path(_settings(tmp_path), for_benchmark=True)

    assert resolved == benchmark_path


def test_resolve_card_engine_config_path_falls_back_to_runtime_default(tmp_path):
    runtime_path = default_runtime_card_engine_config_path(tmp_path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text("{}", encoding="utf-8")

    resolved = resolve_card_engine_config_path(_settings(tmp_path))

    assert resolved == runtime_path
