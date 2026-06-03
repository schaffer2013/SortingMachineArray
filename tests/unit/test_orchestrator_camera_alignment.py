from __future__ import annotations

from types import SimpleNamespace

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.enums import PileRole
from sorter.domain.models import MachineSnapshot, PileId, PileState, RunState


class RecordingMotion:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []
        self.z_moves: list[float] = []
        self.homed = False
        self.waited = False

    def home_axes(self) -> None:
        self.homed = True

    def move_xy(self, x_mm: float, y_mm: float) -> None:
        self.moves.append((x_mm, y_mm))

    def move_z(self, z_mm: float) -> None:
        self.z_moves.append(z_mm)

    def wait_until_idle(self) -> None:
        self.waited = True


class RecordingVacuum:
    def __init__(self) -> None:
        self.off_called = False

    def off(self) -> None:
        self.off_called = True


class RecordingLights:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def set_status(self, status: str) -> None:
        self.statuses.append(status)


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
        pile_positions_mm=((240.0, 160.0),),
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
        pile_positions_mm=((240.0, 160.0),),
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


def test_move_camera_to_xy_uses_vacuum_baseline_offset() -> None:
    snapshot = MachineSnapshot(piles={}, run_state=RunState())
    snapshot.pose.z_mm = 8.0
    world = SimpleNamespace(snapshot=snapshot, coords={})
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
        camera_offset_x_mm=10.0,
        camera_offset_y_mm=-3.0,
        camera_offset_z_mm=7.0,
        min_xy_travel_z_mm=2.0,
        pile_positions_mm=(),
    )

    orchestrator.move_camera_to_vacuum_xy_when_safe(calibration, 100.0, 50.0)

    assert motion.moves == [(90.0, 53.0)]
    assert snapshot.pose.x_mm == 90.0
    assert snapshot.pose.y_mm == 53.0
    assert calibration.camera_z_for_vacuum_z(snapshot.pose.z_mm) == 15.0


def test_xy_motion_is_blocked_when_vacuum_z_is_below_clearance() -> None:
    snapshot = MachineSnapshot(piles={}, run_state=RunState())
    snapshot.pose.z_mm = 1.5
    world = SimpleNamespace(snapshot=snapshot, coords={})
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
        camera_offset_x_mm=0.0,
        camera_offset_y_mm=0.0,
        min_xy_travel_z_mm=2.0,
        pile_positions_mm=(),
    )

    try:
        orchestrator.move_vac_xy_when_safe(calibration, 100.0, 50.0)
    except ValueError as exc:
        assert "XY travel blocked" in str(exc)
    else:
        raise AssertionError("Expected XY guard to block low-Z travel")

    assert motion.moves == []
    assert snapshot.pose.x_mm == 0.0
    assert snapshot.pose.y_mm == 0.0


def test_initialize_machine_runs_homing_sequence_only_when_called() -> None:
    snapshot = MachineSnapshot(piles={}, run_state=RunState())
    world = SimpleNamespace(snapshot=snapshot, coords={})
    motion = RecordingMotion()
    vacuum = RecordingVacuum()
    lights = RecordingLights()
    orchestrator = Orchestrator(
        motion=motion,
        camera=SimpleNamespace(),
        vacuum=vacuum,
        lights=lights,
        recognizer=SimpleNamespace(),
        catalog=SimpleNamespace(),
        run_store=SimpleNamespace(),
        world=world,
    )
    calibration = CalibrationProfile(
        safe_z_mm=1.0,
        pick_z_mm=0.5,
        place_z_mm=0.75,
        camera_offset_x_mm=0.0,
        camera_offset_y_mm=0.0,
        min_xy_travel_z_mm=4.0,
        pile_positions_mm=(),
    )

    assert motion.homed is False
    assert motion.z_moves == []

    travel_z_mm = orchestrator.initialize_machine(calibration)

    assert travel_z_mm == 4.0
    assert vacuum.off_called is True
    assert motion.homed is True
    assert motion.moves == []
    assert motion.z_moves == [4.0]
    assert motion.waited is True
    assert lights.statuses == ["running", "idle"]
    assert snapshot.pose.x_mm == 0.0
    assert snapshot.pose.y_mm == 0.0
    assert snapshot.pose.z_mm == 4.0
    assert snapshot.run_state.phase == "IDLE"
    assert snapshot.run_state.active_command is None
