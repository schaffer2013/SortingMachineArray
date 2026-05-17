from __future__ import annotations

from pathlib import Path

from sorter.application.sequences import (
    SequenceDefinition,
    SequenceExecutionContext,
    SequenceExecutor,
    build_default_registry,
)
from sorter.config.calibration import CalibrationProfile
from sorter.domain.models import MachineSnapshot


DEFAULT_REGISTRATION_SEQUENCE_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "sequences" / "registration_v1.json"
)


def plan_registration_sequence(
    snapshot: MachineSnapshot,
    calibration: CalibrationProfile,
    *,
    definition_path: Path | None = None,
) -> SequenceExecutionContext:
    definition = SequenceDefinition.from_file(definition_path or DEFAULT_REGISTRATION_SEQUENCE_PATH)
    context = SequenceExecutionContext(snapshot=snapshot, calibration=calibration)
    return SequenceExecutor(build_default_registry()).execute(definition, context)
