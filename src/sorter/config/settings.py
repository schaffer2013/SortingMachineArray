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
        file_env = _load_env_files(root)

        def _setting(key: str, default: str) -> str:
            return os.getenv(key) or file_env.get(key) or default

        mode = _setting("SORTER_MODE", "sim").lower()
        seed = int(_setting("SORTER_SEED", "42"))
        scenario = root / _setting("SORTER_SCENARIO", "scenarios/fixtures/small_stack.json")
        catalog = root / _setting("SORTER_CATALOG", "data/card_catalog/cards.json")
        sqlite_path = root / _setting("SORTER_RUN_DB", "data/runs.sqlite3")
        calibration_path = root / _setting("SORTER_CALIBRATION", "config/calibration.json")
        slow_ms = int(_setting("SORTER_SLOW_MS", "0"))
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


def _load_env_files(root: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for filename in (".env.example", ".env"):
        env_path = root / filename
        if not env_path.exists():
            continue
        with env_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                merged[key.strip()] = value.strip().strip('"').strip("'")
    return merged
