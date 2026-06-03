from __future__ import annotations

from sorter.application.use_cases.execute_move import build_pick_place_sequence
from sorter.config.calibration import CalibrationProfile
from sorter.domain.machine_state import NextMove
from sorter.domain.models import PileId


def test_pick_place_sequence_raises_to_xy_clearance_before_xy_moves() -> None:
    calibration = CalibrationProfile(
        safe_z_mm=2.0,
        pick_z_mm=0.5,
        place_z_mm=0.75,
        camera_offset_x_mm=0.0,
        camera_offset_y_mm=0.0,
        min_xy_travel_z_mm=4.0,
        pile_positions_mm=(),
    )
    move = NextMove(from_pile=PileId(0, 0), to_pile=PileId(1, 0))

    commands = build_pick_place_sequence(move, calibration)

    assert [command.name for command in commands[:2]] == ["MoveZ", "MoveToSourceXY"]
    assert commands[0].payload == {"z_mm": 4.0}
    assert commands[4].payload == {"z_mm": 4.0}
    assert commands[5].name == "MoveToDestXY"
    assert commands[8].payload == {"z_mm": 4.0}
