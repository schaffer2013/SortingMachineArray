from pathlib import Path

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings


def test_noisy_sim_fixture_escalates_to_review_required(tmp_path):
    root = Path(__file__).resolve().parents[2]
    settings = AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=root / "tests/noisy_sim/review_required_fixture.json",
        card_catalog_path=root / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "runs.sqlite3",
        calibration_path=root / "config/calibration.json",
        sort_policy_path=root / "config/sort_policies/default_color_then_alpha.json",
        sim_card_list_path=None,
        startup_scan_max_retries=1,
        verification_max_retries=1,
    )
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    result = orchestrator.run_once(calibration)

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["metrics"]["retry_count"] >= 1
    assert result["metrics"]["review_required_count"] == 1
