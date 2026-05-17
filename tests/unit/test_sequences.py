from pathlib import Path

from sorter.application.sequences import (
    SequenceDefinition,
    SequenceExecutionContext,
    SequenceExecutor,
    build_default_registry,
)
from sorter.application.registration import plan_registration_sequence
from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings


def test_registration_sequence_plans_balanced_groups():
    settings = AppSettings.from_env()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    definition = SequenceDefinition.from_file(Path("config/sequences/registration_v1.json"))
    context = SequenceExecutionContext(
        snapshot=orchestrator.world.snapshot,
        calibration=calibration,
    )

    result = SequenceExecutor(build_default_registry()).execute(definition, context)

    groups = result.state["pile_groups"]
    assert len(groups["unregistered"]) == 3
    assert len(groups["registered"]) == 3
    assert result.state["scan_piles"]["occupancy"]
    assert result.state["probe_piles"]["heights_mm"]
    assert result.state["plan_registration_pass"]["per_card_steps"][-1] == "submit_registration_job_async"


def test_registration_entrypoint_uses_default_sequence():
    settings = AppSettings.from_env()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    result = plan_registration_sequence(orchestrator.world.snapshot, calibration)

    assert result.state["sequence"]["name"] == "registration"
    assert result.state["plan_rebalance"]["target_group"] == "unregistered"
