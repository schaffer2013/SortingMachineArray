from pathlib import Path

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.settings import AppSettings
from sorter.config.calibration import CalibrationProfile


def test_small_stack_runs_headless(tmp_path):
    root = Path(__file__).resolve().parents[2]
    settings = AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=root / "scenarios/fixtures/small_stack.json",
        card_catalog_path=root / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "runs.sqlite3",
        calibration_path=root / "config/calibration.json",
    )
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    result = orchestrator.run_once(calibration)
    assert result["status"] in {"COMPLETED", "FAULTED"}
    assert result["seq"] >= 0
