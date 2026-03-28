from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sorter.config.settings import AppSettings


DEFAULT_CARD_ENGINE_CONFIG = Path("config/card_engine/engine.json")
DEFAULT_CARD_ENGINE_BENCHMARK_CONFIG = Path("config/card_engine/benchmark.engine.json")


def default_runtime_card_engine_config_path(project_root: Path) -> Path:
    return project_root / DEFAULT_CARD_ENGINE_CONFIG


def default_benchmark_card_engine_config_path(project_root: Path) -> Path:
    return project_root / DEFAULT_CARD_ENGINE_BENCHMARK_CONFIG


def resolve_card_engine_config_path(
    settings: AppSettings,
    *,
    for_benchmark: bool = False,
    override_path: Path | None = None,
) -> Path | None:
    if override_path is not None:
        return override_path
    if settings.project_root is None:
        return settings.card_engine_config_path
    if for_benchmark:
        benchmark_path = default_benchmark_card_engine_config_path(settings.project_root)
        if benchmark_path.exists():
            return benchmark_path
    runtime_path = default_runtime_card_engine_config_path(settings.project_root)
    if settings.card_engine_config_path is not None:
        return settings.card_engine_config_path
    if runtime_path.exists():
        return runtime_path
    return None
