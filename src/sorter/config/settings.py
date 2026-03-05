from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os


@dataclass(frozen=True)
class AppSettings:
    mode: str
    random_seed: int
    scenario_fixture: Path
    card_catalog_path: Path
    sqlite_path: Path
    calibration_path: Path
    slow_ms: int = 0

    @staticmethod
    def from_env(project_root: Path | None = None) -> "AppSettings":
        root = project_root or Path(__file__).resolve().parents[3]
        mode = os.getenv("SORTER_MODE", "sim").lower()
        seed = int(os.getenv("SORTER_SEED", "42"))
        scenario = root / os.getenv("SORTER_SCENARIO", "scenarios/fixtures/small_stack.json")
        catalog = root / os.getenv("SORTER_CATALOG", "data/card_catalog/cards.json")
        sqlite_path = root / os.getenv("SORTER_RUN_DB", "data/runs.sqlite3")
        calibration_path = root / os.getenv("SORTER_CALIBRATION", "config/calibration.json")
        slow_ms = int(os.getenv("SORTER_SLOW_MS", "0"))
        return AppSettings(
            mode=mode,
            random_seed=seed,
            scenario_fixture=scenario,
            card_catalog_path=catalog,
            sqlite_path=sqlite_path,
            calibration_path=calibration_path,
            slow_ms=slow_ms,
        )


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
