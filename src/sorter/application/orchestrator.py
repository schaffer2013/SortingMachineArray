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
    recognition_min_confidence: float = 0.6

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
        rank_lookup = self.world.rank_lookup()
        self.run_store.start_run(
            run_id,
            mode="sim",
            scenario_name=self.world.scenario_name,
            config_snapshot={
                "seed": self.world.seed,
                "recognition_min_confidence": self.recognition_min_confidence,
                "recognizer_backend": getattr(self.recognizer, "__class__", type(self.recognizer)).__name__,
            },
        )
        self.lights.set_status("running")
        seq = 0
        logger.info(
            "run started: run_id=%s scenario=%s seed=%s",
            run_id,
            self.world.scenario_name,
            self.world.seed,
        )
        startup_status = self._perform_startup_discovery_scan(
            run_id,
            snapshot,
            should_stop=should_stop,
            per_command_delay_s=per_command_delay_s,
        )
        if startup_status is not None:
            return startup_status
        workflow = LegacyWorkflowState(snapshot)

        while True:
            if should_stop and should_stop():
                self.lights.set_status("idle")
                self.run_store.finish_run(run_id, "STOPPED")
                logger.info("run stopped: run_id=%s seq=%s", run_id, seq)
                return {"run_id": run_id, "status": "STOPPED", "seq": seq}

            next_move = workflow.plan_next(rank_lookup)
            while next_move is None:
                previous_step = workflow.step
                workflow.update_step()
                if workflow.step.name == "FINISH":
                    logger.debug("workflow reached FINISH step: run_id=%s seq=%s", run_id, seq)
                    next_move = None
                    break
                next_move = workflow.plan_next(rank_lookup)
                if next_move is None and workflow.step == previous_step:
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
            if workflow.step.name == "FINISH":
                break

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
            verified, verification_result, verification_frame = verify_move(
                next_move,
                self.camera,
                self.recognizer,
                min_confidence=self.recognition_min_confidence,
            )
            self.run_store.append_event(run_id, seq, DomainEvent.now("move_verified", {
                "verified": verified,
                "confidence": verification_result.confidence,
                "card_name": verification_result.card_name,
                "backend": verification_result.backend,
                "scryfall_id": verification_result.scryfall_id,
                "oracle_id": verification_result.oracle_id,
                "needs_review": verification_result.needs_review,
                "fallback_used": verification_result.fallback_used,
            }))
            logger.debug(
                "move verification: run_id=%s seq=%s verified=%s confidence=%.3f card=%s backend=%s review=%s fallback=%s",
                run_id,
                seq,
                verified,
                verification_result.confidence,
                verification_result.card_name,
                verification_result.backend,
                verification_result.needs_review,
                verification_result.fallback_used,
            )
            self.run_store.save_frame(run_id, seq, verification_frame, verification_result)
            self.run_store.save_snapshot(run_id, seq, snapshot)
            if not verified:
                self.lights.set_status("fault")
                self.run_store.finish_run(run_id, "FAULTED")
                logger.warning(
                    "run faulted: run_id=%s seq=%s card=%s confidence=%.3f backend=%s review=%s",
                    run_id,
                    seq,
                    verification_result.card_name,
                    verification_result.confidence,
                    verification_result.backend,
                    verification_result.needs_review,
                )
                return {"run_id": run_id, "status": "FAULTED", "seq": seq}

        self.lights.set_status("idle")
        self.run_store.finish_run(run_id, "COMPLETED")
        logger.info("run completed: run_id=%s seq=%s", run_id, seq)
        return {"run_id": run_id, "status": "COMPLETED", "seq": seq}

    def _perform_startup_discovery_scan(
        self,
        run_id: str,
        snapshot: MachineSnapshot,
        should_stop: Callable[[], bool] | None = None,
        per_command_delay_s: float = 0.0,
    ) -> dict | None:
        logger.info("startup discovery scan started: run_id=%s piles=%s", run_id, len(snapshot.piles))
        for pile in snapshot.piles.values():
            if should_stop and should_stop():
                self.lights.set_status("idle")
                self.run_store.finish_run(run_id, "STOPPED")
                logger.info("run stopped during startup scan: run_id=%s pile=%s", run_id, pile.pile_id.as_key())
                return {"run_id": run_id, "status": "STOPPED", "seq": 0}

            self.run_store.append_event(
                run_id,
                0,
                DomainEvent.now("command", {"name": "MoveToDiscoveryXY", "payload": {"pile": pile.pile_id.as_key()}}),
            )
            logger.debug(
                "startup discovery move: run_id=%s pile=%s",
                run_id,
                pile.pile_id.as_key(),
            )
            self.world.move_to_pile(pile.pile_id)
            pose = self.motion.get_pose()
            self.motion.move_xy(pose.x_mm, pose.y_mm)
            if per_command_delay_s > 0:
                time.sleep(per_command_delay_s)

            self.run_store.append_event(
                run_id,
                0,
                DomainEvent.now("command", {"name": "CaptureDiscovery", "payload": {"pile": pile.pile_id.as_key()}}),
            )
            frame = self.camera.capture_top_card(pile.pile_id)
            result = self.recognizer.recognize_top_card(frame)
            self.run_store.append_event(
                run_id,
                0,
                DomainEvent.now(
                    "startup_scan",
                    {
                        "pile": pile.pile_id.as_key(),
                        "card_name": result.card_name,
                        "confidence": result.confidence,
                        "backend": result.backend,
                        "scryfall_id": result.scryfall_id,
                        "oracle_id": result.oracle_id,
                        "needs_review": result.needs_review,
                        "fallback_used": result.fallback_used,
                        "empty_confirmed": result.card_name is None,
                    },
                ),
            )
            logger.debug(
                "startup discovery result: run_id=%s pile=%s card=%s confidence=%.3f backend=%s review=%s fallback=%s",
                run_id,
                pile.pile_id.as_key(),
                result.card_name,
                result.confidence,
                result.backend,
                result.needs_review,
                result.fallback_used,
            )
            self.run_store.save_frame(run_id, 0, frame, result)
            self.run_store.save_snapshot(run_id, 0, snapshot)

        logger.info("startup discovery scan completed: run_id=%s", run_id)
        return None

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
