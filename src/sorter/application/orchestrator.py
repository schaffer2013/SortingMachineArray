from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
import uuid
from typing import Callable
import time

from sorter.application.use_cases.execute_move import build_pick_place_sequence
from sorter.application.use_cases.verify_move import verify_move
from sorter.domain.events import DomainEvent
from sorter.domain.machine_state import LegacyWorkflowState, NextMove
from sorter.domain.models import MachineSnapshot
from sorter.config.calibration import CalibrationProfile
from sorter.ports.motion import MotionPort
from sorter.ports.camera import CameraPort
from sorter.ports.vacuum import VacuumPort
from sorter.ports.lights import LightsPort
from sorter.ports.recognizer import RecognizerPort
from sorter.ports.card_catalog import CardCatalogPort
from sorter.ports.run_store import RunStorePort


@dataclass
class Orchestrator:
    motion: MotionPort
    camera: CameraPort
    vacuum: VacuumPort
    lights: LightsPort
    recognizer: RecognizerPort
    catalog: CardCatalogPort
    run_store: RunStorePort
    world: any

    def _run_id(self) -> str:
        return f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def run_once(
        self,
        calibration: CalibrationProfile,
        should_stop: Callable[[], bool] | None = None,
        per_command_delay_s: float = 0.0,
    ) -> dict:
        run_id = self._run_id()
        snapshot = self.world.snapshot
        workflow = LegacyWorkflowState(snapshot)
        rank_lookup = self.world.rank_lookup()
        self.run_store.start_run(run_id, mode="sim", scenario_name=self.world.scenario_name, config_snapshot={"seed": self.world.seed})
        self.lights.set_status("running")
        seq = 0

        while True:
            if should_stop and should_stop():
                self.lights.set_status("idle")
                self.run_store.finish_run(run_id, "STOPPED")
                return {"run_id": run_id, "status": "STOPPED", "seq": seq}

            next_move = workflow.plan_next(rank_lookup)
            if next_move is None:
                workflow.update_step()
                if workflow.step.name == "FINISH":
                    break
                next_move = workflow.plan_next(rank_lookup)
                if next_move is None:
                    break

            seq += 1
            self._execute_atomic_move(
                run_id,
                seq,
                snapshot,
                calibration,
                next_move,
                per_command_delay_s=per_command_delay_s,
            )
            verified, confidence, card_name = verify_move(next_move, self.camera, self.recognizer)
            self.run_store.append_event(run_id, seq, DomainEvent.now("move_verified", {
                "verified": verified,
                "confidence": confidence,
                "card_name": card_name,
            }))
            frame = self.camera.capture_top_card(next_move.from_pile)
            self.run_store.save_frame(
                run_id,
                seq,
                frame.frame_id,
                frame.path,
                next_move.from_pile.as_key(),
                card_name,
                confidence,
            )
            self.run_store.save_snapshot(run_id, seq, snapshot)
            if not verified:
                self.lights.set_status("fault")
                self.run_store.finish_run(run_id, "FAULTED")
                return {"run_id": run_id, "status": "FAULTED", "seq": seq}

        self.lights.set_status("idle")
        self.run_store.finish_run(run_id, "COMPLETED")
        return {"run_id": run_id, "status": "COMPLETED", "seq": seq}

    def _execute_atomic_move(
        self,
        run_id: str,
        seq: int,
        snapshot: MachineSnapshot,
        calibration: CalibrationProfile,
        next_move: NextMove,
        per_command_delay_s: float = 0.0,
    ) -> None:
        commands = build_pick_place_sequence(next_move, calibration)
        for command in commands:
            self.run_store.append_event(run_id, seq, DomainEvent.now("command", {"name": command.name, "payload": command.payload}))
            if command.name == "MoveToSourceXY":
                self.world.move_to_pile(next_move.from_pile)
                pose = self.motion.get_pose()
                self.motion.move_xy(pose.x_mm, pose.y_mm)
            elif command.name == "MoveToDestXY":
                self.world.move_to_pile(next_move.to_pile)
                pose = self.motion.get_pose()
                self.motion.move_xy(pose.x_mm, pose.y_mm)
            elif command.name == "MoveZ":
                self.motion.move_z(float(command.payload["z_mm"]))
            elif command.name == "VacuumOn":
                self.vacuum.on()
                self.world.pick_from(next_move.from_pile)
            elif command.name == "VacuumOff":
                self.vacuum.off()
                self.world.place_to(next_move.to_pile)
            if per_command_delay_s > 0:
                time.sleep(per_command_delay_s)
        snapshot.run_state.metrics.move_count += 1
