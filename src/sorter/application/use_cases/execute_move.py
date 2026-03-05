from __future__ import annotations

from dataclasses import dataclass

from sorter.domain.commands import MoveZ, VacuumOn, VacuumOff
from sorter.domain.machine_state import NextMove
from sorter.config.calibration import CalibrationProfile


@dataclass(frozen=True)
class CommandRecord:
    name: str
    payload: dict


def build_pick_place_sequence(move: NextMove, calibration: CalibrationProfile) -> list[CommandRecord]:
    return [
        CommandRecord(name="MoveToSourceXY", payload={"pile": move.from_pile.as_key()}),
        CommandRecord(name=MoveZ.__name__, payload={"z_mm": calibration.pick_z_mm}),
        CommandRecord(name=VacuumOn.__name__, payload={}),
        CommandRecord(name=MoveZ.__name__, payload={"z_mm": calibration.safe_z_mm}),
        CommandRecord(name="MoveToDestXY", payload={"pile": move.to_pile.as_key()}),
        CommandRecord(name=MoveZ.__name__, payload={"z_mm": calibration.place_z_mm}),
        CommandRecord(name=VacuumOff.__name__, payload={}),
        CommandRecord(name=MoveZ.__name__, payload={"z_mm": calibration.safe_z_mm}),
        CommandRecord(name="CaptureVerification", payload={"pile": move.from_pile.as_key()}),
    ]
