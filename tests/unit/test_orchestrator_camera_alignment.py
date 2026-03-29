from __future__ import annotations

from types import SimpleNamespace

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.enums import PileRole
from sorter.domain.models import MachineSnapshot, PileId, PileState, RunState


class RecordingMotion:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []

    def move_xy(self, x_mm: float, y_mm: float) -> None:
        self.moves.append((x_mm, y_mm))


def test_move_camera_over_pile_uses_camera_offset() -> None:
    pile_id = PileId(1, 0)
    snapshot = MachineSnapshot(
        piles={
            pile_id.as_key(): PileState(
                pile_id=pile_id,
                role=PileRole.FEEDER,
                capacity=85,
                x_mm=200.0,
                y_mm=100.0,
            )
        },
        run_state=RunState(),
    )
    world = SimpleNamespace(snapshot=snapshot, coords={pile_id.as_key(): (200.0, 100.0)})
    motion = RecordingMotion()
    orchestrator = Orchestrator(
        motion=motion,
        camera=SimpleNamespace(),
        vacuum=SimpleNamespace(),
        lights=SimpleNamespace(),
        recognizer=SimpleNamespace(),
        catalog=SimpleNamespace(),
        run_store=SimpleNamespace(),
        world=world,
    )
    calibration = CalibrationProfile(
        safe_z_mm=0.0,
        pick_z_mm=5.0,
        place_z_mm=5.0,
        camera_offset_x_mm=14.0,
        camera_offset_y_mm=-6.0,
        pile_xy_mm={pile_id.as_key(): (240.0, 160.0)},
    )

    orchestrator._move_camera_over_pile(
        snapshot,
        pile_id,
        calibration,
        phase="DISCOVERING",
        active_command="MoveToDiscoveryXY",
    )

    assert motion.moves == [(226.0, 166.0)]
    assert snapshot.pose.x_mm == 226.0
    assert snapshot.pose.y_mm == 166.0
    assert snapshot.run_state.phase == "DISCOVERING"
    assert snapshot.run_state.active_command == "MoveToDiscoveryXY"


def test_move_picker_over_pile_uses_calibrated_reference_without_camera_offset() -> None:
    pile_id = PileId(1, 0)
    snapshot = MachineSnapshot(
        piles={
            pile_id.as_key(): PileState(
                pile_id=pile_id,
                role=PileRole.FEEDER,
                capacity=85,
                x_mm=200.0,
                y_mm=100.0,
            )
        },
        run_state=RunState(),
    )
    world = SimpleNamespace(snapshot=snapshot, coords={pile_id.as_key(): (200.0, 100.0)})
    motion = RecordingMotion()
    orchestrator = Orchestrator(
        motion=motion,
        camera=SimpleNamespace(),
        vacuum=SimpleNamespace(),
        lights=SimpleNamespace(),
        recognizer=SimpleNamespace(),
        catalog=SimpleNamespace(),
        run_store=SimpleNamespace(),
        world=world,
    )
    calibration = CalibrationProfile(
        safe_z_mm=0.0,
        pick_z_mm=5.0,
        place_z_mm=5.0,
        camera_offset_x_mm=14.0,
        camera_offset_y_mm=-6.0,
        pile_xy_mm={pile_id.as_key(): (240.0, 160.0)},
    )

    orchestrator._move_picker_over_pile(
        snapshot,
        pile_id,
        calibration,
        phase="EXECUTING",
        active_command="MoveToSourceXY",
    )

    assert motion.moves == [(240.0, 160.0)]
    assert snapshot.pose.x_mm == 240.0
    assert snapshot.pose.y_mm == 160.0
    assert snapshot.run_state.phase == "EXECUTING"
    assert snapshot.run_state.active_command == "MoveToSourceXY"
