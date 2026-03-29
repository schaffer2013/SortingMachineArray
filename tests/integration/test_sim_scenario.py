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
        sort_policy_path=root / "config/sort_policies/default_color_then_alpha.json",
    )
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    result = orchestrator.run_once(calibration)
    assert result["status"] in {"COMPLETED", "FAULTED"}
    assert result["seq"] >= 0
    assert "metrics" in result
    assert result["metrics"]["scan_count"] >= 0


def test_small_stack_generated_runtime_fixture_does_not_fault_before_first_move(tmp_path):
    root = Path(__file__).resolve().parents[2]
    settings = AppSettings(
        mode="sim",
        random_seed=42,
        scenario_fixture=root / "scenarios/fixtures/small_stack.json",
        card_catalog_path=root / "data/card_catalog/cards.json",
        sqlite_path=tmp_path / "runs.sqlite3",
        calibration_path=root / "config/calibration.json",
        sort_policy_path=root / "config/sort_policies/default_color_then_alpha.json",
        sim_card_list_path=root / "config/sim_card_lists/default_cards.json",
        generated_runtime_fixture_path=tmp_path / "generated" / "runtime_fixture.json",
        auto_image_sync=False,
        project_root=root,
        recognizer_backend="sim_truth",
    )
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    result = orchestrator.run_once(calibration)

    assert result["status"] != "FAULTED"
