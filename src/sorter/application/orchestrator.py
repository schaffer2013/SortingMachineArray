from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
import logging
import uuid
from typing import Any, Callable
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


logger = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    motion: MotionPort
    camera: CameraPort
    vacuum: VacuumPort
    lights: LightsPort
    recognizer: RecognizerPort
    catalog: CardCatalogPort
    run_store: RunStorePort
    world: Any

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
        logger.info(
            "run started: run_id=%s scenario=%s seed=%s",
            run_id,
            self.world.scenario_name,
            self.world.seed,
        )

        while True:
            if should_stop and should_stop():
                self.lights.set_status("idle")
                self.run_store.finish_run(run_id, "STOPPED")
                logger.info("run stopped: run_id=%s seq=%s", run_id, seq)
                return {"run_id": run_id, "status": "STOPPED", "seq": seq}

            next_move = workflow.plan_next(rank_lookup)
            if next_move is None:
                workflow.update_step()
                if workflow.step.name == "FINISH":
                    logger.debug("workflow reached FINISH step: run_id=%s seq=%s", run_id, seq)
                    break
                next_move = workflow.plan_next(rank_lookup)
                if next_move is None:
                    logger.debug(
                        "no move available after step update: run_id=%s step=%s seq=%s",
                        run_id,
                        workflow.step.name,
                        seq,
                    )
                    self.lights.set_status("fault")
                    self.run_store.finish_run(run_id, "FAULTED")
                    logger.warning(
                        "run faulted: run_id=%s seq=%s reason=no_move_available step=%s",
                        run_id,
                        seq,
                        workflow.step.name,
                    )
                    return {"run_id": run_id, "status": "FAULTED", "seq": seq}

            seq += 1
            logger.debug(
                "executing move: run_id=%s seq=%s step=%s from=%s to=%s",
                run_id,
                seq,
                workflow.step.name,
                next_move.from_pile.as_key(),
                next_move.to_pile.as_key(),
            )
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
            logger.debug(
                "move verification: run_id=%s seq=%s verified=%s confidence=%.3f card=%s",
                run_id,
                seq,
                verified,
                confidence,
                card_name,
            )
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
                logger.warning(
                    "run faulted: run_id=%s seq=%s card=%s confidence=%.3f",
                    run_id,
                    seq,
                    card_name,
                    confidence,
                )
                return {"run_id": run_id, "status": "FAULTED", "seq": seq}

        self.lights.set_status("idle")
        self.run_store.finish_run(run_id, "COMPLETED")
        logger.info("run completed: run_id=%s seq=%s", run_id, seq)
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
            logger.debug(
                "command: run_id=%s seq=%s name=%s payload=%s",
                run_id,
                seq,
                command.name,
                command.payload,
            )
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
