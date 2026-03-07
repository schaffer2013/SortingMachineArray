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
    sort_policy_path: Path
    sim_card_list_path: Path | None = None
    generated_runtime_fixture_path: Path | None = None
    slow_ms: int = 0
    auto_image_sync: bool = True
    project_root: Path | None = None

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
        sort_policy_path = root / _setting(
            "SORTER_SORT_POLICY",
            "config/sort_policies/default_color_then_alpha.json",
        )
        sim_card_list_raw = _setting("SORTER_SIM_CARD_LIST", "config/sim_card_lists/default_cards.json")
        sim_card_list_path = None if sim_card_list_raw.lower() in {"", "none", "null"} else (root / sim_card_list_raw)
        runtime_fixture_path = root / _setting("SORTER_RUNTIME_FIXTURE", "data/generated/runtime_fixture.json")
        slow_ms = int(_setting("SORTER_SLOW_MS", "0"))
        auto_image_sync = _setting("SORTER_AUTO_IMAGE_SYNC", "1") not in {"0", "false", "False"}
        return AppSettings(
            mode=mode,
            random_seed=seed,
            scenario_fixture=scenario,
            card_catalog_path=catalog,
            sqlite_path=sqlite_path,
            calibration_path=calibration_path,
            sort_policy_path=sort_policy_path,
            sim_card_list_path=sim_card_list_path,
            generated_runtime_fixture_path=runtime_fixture_path,
            slow_ms=slow_ms,
            auto_image_sync=auto_image_sync,
            project_root=root,
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
