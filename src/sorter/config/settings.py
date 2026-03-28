from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os

from sorter.config.card_engine import DEFAULT_CARD_ENGINE_CONFIG
from sorter.config.recognition import RecognitionPolicyConfig


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
    sim_image_auto_fetch: bool = False
    allow_external_card_enrichment: bool = False
    project_root: Path | None = None
    recognizer_backend: str = "sim_truth"
    card_engine_config_path: Path | None = None
    card_engine_mode: str = "greenfield"
    card_engine_auto_track_results: bool = False
    card_engine_prefer_visual_small_pool: bool = False
    recognition_thresholds_path: Path | None = None
    recognition_min_confidence: float = 0.6
    fuzzy_enigma_sim_truth_fallback: bool = False
    startup_scan_max_retries: int = 1
    verification_max_retries: int = 2

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
        sim_image_auto_fetch = _setting("SORTER_SIM_IMAGE_AUTO_FETCH", "0") in {"1", "true", "True"}
        recognition_thresholds_path = root / _setting(
            "SORTER_RECOGNITION_THRESHOLDS",
            "config/vision/recognition_thresholds.json",
        )
        recognition_policy = RecognitionPolicyConfig.from_file(recognition_thresholds_path)
        recognizer_backend = _setting("SORTER_RECOGNIZER_BACKEND", "sim_truth").strip().lower()
        card_engine_config_raw = _setting("SORTER_CARD_ENGINE_CONFIG", str(DEFAULT_CARD_ENGINE_CONFIG))
        card_engine_config_path = (
            None
            if card_engine_config_raw.lower() in {"", "none", "null"}
            else (root / card_engine_config_raw)
        )
        card_engine_mode = _setting("SORTER_CARD_ENGINE_MODE", "greenfield").strip().lower()
        card_engine_auto_track_results = _setting("SORTER_CARD_ENGINE_AUTO_TRACK_RESULTS", "0") in {"1", "true", "True"}
        card_engine_prefer_visual_small_pool = _setting(
            "SORTER_CARD_ENGINE_PREFER_VISUAL_SMALL_POOL",
            "0",
        ) in {"1", "true", "True"}
        recognition_min_confidence = float(
            _setting("SORTER_RECOGNITION_MIN_CONFIDENCE", str(recognition_policy.min_confidence))
        )
        fuzzy_enigma_sim_truth_fallback = _setting(
            "SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK",
            "1" if recognition_policy.allow_sim_truth_fallback else "0",
        ) in {"1", "true", "True"}
        allow_external_card_enrichment = _setting(
            "SORTER_ALLOW_EXTERNAL_CARD_ENRICHMENT",
            "0",
        ) in {"1", "true", "True"}
        startup_scan_max_retries = int(
            _setting("SORTER_STARTUP_SCAN_MAX_RETRIES", str(recognition_policy.startup_scan_max_retries))
        )
        verification_max_retries = int(
            _setting("SORTER_VERIFICATION_MAX_RETRIES", str(recognition_policy.verification_max_retries))
        )
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
            sim_image_auto_fetch=sim_image_auto_fetch,
            allow_external_card_enrichment=allow_external_card_enrichment,
            project_root=root,
            recognizer_backend=recognizer_backend,
            card_engine_config_path=card_engine_config_path,
            card_engine_mode=card_engine_mode,
            card_engine_auto_track_results=card_engine_auto_track_results,
            card_engine_prefer_visual_small_pool=card_engine_prefer_visual_small_pool,
            recognition_thresholds_path=recognition_thresholds_path,
            recognition_min_confidence=recognition_min_confidence,
            fuzzy_enigma_sim_truth_fallback=fuzzy_enigma_sim_truth_fallback,
            startup_scan_max_retries=max(0, startup_scan_max_retries),
            verification_max_retries=max(0, verification_max_retries),
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
