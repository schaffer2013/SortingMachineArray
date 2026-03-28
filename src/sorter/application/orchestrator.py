from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, UTC
import logging
import uuid
from typing import Any, Callable
import time

from sorter.application.recognition_reporting import (
    classify_review_reason,
    confidence_band_for,
    increment_counter,
)
from sorter.application.use_cases.execute_move import build_pick_place_sequence
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


@dataclass(frozen=True)
class ObservationCycle:
    accepted: bool
    frame: Any
    result: Any
    attempts: int
    reason: str


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
    startup_scan_max_retries: int = 1
    verification_max_retries: int = 2

    def _run_id(self) -> str:
        return f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _metrics_payload(self, snapshot: MachineSnapshot) -> dict:
        return asdict(snapshot.run_state.metrics)

    def _recognition_decision(self, frame, result) -> tuple[bool, str]:
        if result.needs_review:
            return False, "needs_review"
        if result.fallback_used:
            self.world.snapshot.run_state.metrics.fallback_count += 1
        if result.card_name is None:
            if frame.path is None:
                return True, "empty_confirmed"
            return False, "missing_prediction_for_visible_card"
        if result.confidence < self.recognition_min_confidence:
            return False, "confidence_below_threshold"
        return True, "accepted"

    def _observe_pile_with_retries(
        self,
        run_id: str,
        seq: int,
        pile_id,
        *,
        phase: str,
        max_retries: int,
    ) -> ObservationCycle:
        attempts = 0
        while True:
            attempts += 1
            frame = self.camera.capture_top_card(pile_id)
            result = self.recognizer.recognize_top_card(frame)
            self.world.snapshot.run_state.metrics.scan_count += 1
            increment_counter(
                self.world.snapshot.run_state.metrics.confidence_band_counts,
                confidence_band_for(result.confidence),
            )
            review_reason = classify_review_reason(frame, result)
            if review_reason is not None:
                increment_counter(self.world.snapshot.run_state.metrics.review_reason_counts, review_reason)
            accepted, reason = self._recognition_decision(frame, result)
            if not accepted:
                self.world.snapshot.run_state.metrics.low_confidence_count += 1
            observed_name = result.card_name if accepted else None
            self.world.apply_recognition_observation(
                pile_id,
                recognized_name=observed_name,
                confidence=result.confidence,
                frame_id=frame.frame_id,
                observed_at_utc=frame.captured_at_utc,
                source=phase,
            )
            self.run_store.append_event(
                run_id,
                seq,
                DomainEvent.now(
                    "recognition_attempt",
                    {
                        "phase": phase,
                        "pile": pile_id.as_key(),
                        "attempt": attempts,
                        "accepted": accepted,
                        "reason": reason,
                        "card_name": result.card_name,
                        "confidence": result.confidence,
                        "backend": result.backend,
                        "needs_review": result.needs_review,
                        "fallback_used": result.fallback_used,
                        "review_reason": review_reason,
                    },
                ),
            )
            self.run_store.save_frame(run_id, seq, frame, result)
            self.run_store.save_snapshot(run_id, seq, self.world.snapshot)
            if accepted:
                return ObservationCycle(True, frame, result, attempts, reason)
            if attempts > max_retries:
                self.world.snapshot.run_state.metrics.review_required_count += 1
                return ObservationCycle(False, frame, result, attempts, reason)
            self.world.snapshot.run_state.metrics.retry_count += 1
            self.run_store.append_event(
                run_id,
                seq,
                DomainEvent.now(
                    "recognition_retry",
                    {
                        "phase": phase,
                        "pile": pile_id.as_key(),
                        "attempt": attempts,
                        "reason": reason,
                    },
                ),
            )

    def _finish_run(self, run_id: str, status: str, snapshot: MachineSnapshot) -> None:
        self.run_store.finish_run(run_id, status, metrics=self._metrics_payload(snapshot))

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
                self._finish_run(run_id, "STOPPED", snapshot)
                logger.info("run stopped: run_id=%s seq=%s", run_id, seq)
                return {"run_id": run_id, "status": "STOPPED", "seq": seq, "metrics": self._metrics_payload(snapshot)}

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
                    snapshot.run_state.metrics.failures += 1
                    self._finish_run(run_id, "FAULTED", snapshot)
                    logger.warning(
                        "run faulted: run_id=%s seq=%s reason=no_move_available step=%s",
                        run_id,
                        seq,
                        workflow.step.name,
                    )
                    return {"run_id": run_id, "status": "FAULTED", "seq": seq, "metrics": self._metrics_payload(snapshot)}
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
            verification = self._observe_pile_with_retries(
                run_id,
                seq,
                next_move.from_pile,
                phase="verification",
                max_retries=self.verification_max_retries,
            )
            verified = verification.accepted
            verification_result = verification.result
            self.run_store.append_event(run_id, seq, DomainEvent.now("move_verified", {
                "verified": verified,
                "confidence": verification_result.confidence,
                "card_name": verification_result.card_name,
                "backend": verification_result.backend,
                "scryfall_id": verification_result.scryfall_id,
                "oracle_id": verification_result.oracle_id,
                "needs_review": verification_result.needs_review,
                "fallback_used": verification_result.fallback_used,
                "attempts": verification.attempts,
                "reason": verification.reason,
            }))
            logger.debug(
                "move verification: run_id=%s seq=%s verified=%s confidence=%.3f card=%s backend=%s review=%s fallback=%s attempts=%s reason=%s",
                run_id,
                seq,
                verified,
                verification_result.confidence,
                verification_result.card_name,
                verification_result.backend,
                verification_result.needs_review,
                verification_result.fallback_used,
                verification.attempts,
                verification.reason,
            )
            if not verified:
                self.lights.set_status("fault")
                snapshot.run_state.metrics.failures += 1
                self._finish_run(run_id, "REVIEW_REQUIRED", snapshot)
                logger.warning(
                    "run review required: run_id=%s seq=%s card=%s confidence=%.3f backend=%s review=%s reason=%s",
                    run_id,
                    seq,
                    verification_result.card_name,
                    verification_result.confidence,
                    verification_result.backend,
                    verification_result.needs_review,
                    verification.reason,
                )
                return {
                    "run_id": run_id,
                    "status": "REVIEW_REQUIRED",
                    "seq": seq,
                    "metrics": self._metrics_payload(snapshot),
                }

        self.lights.set_status("idle")
        self._finish_run(run_id, "COMPLETED", snapshot)
        logger.info("run completed: run_id=%s seq=%s", run_id, seq)
        return {"run_id": run_id, "status": "COMPLETED", "seq": seq, "metrics": self._metrics_payload(snapshot)}

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
                self._finish_run(run_id, "STOPPED", snapshot)
                logger.info("run stopped during startup scan: run_id=%s pile=%s", run_id, pile.pile_id.as_key())
                return {"run_id": run_id, "status": "STOPPED", "seq": 0, "metrics": self._metrics_payload(snapshot)}

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
            observation = self._observe_pile_with_retries(
                run_id,
                0,
                pile.pile_id,
                phase="startup_scan",
                max_retries=self.startup_scan_max_retries,
            )
            result = observation.result
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
                        "attempts": observation.attempts,
                        "reason": observation.reason,
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
            if not observation.accepted:
                self.lights.set_status("fault")
                snapshot.run_state.metrics.failures += 1
                self._finish_run(run_id, "REVIEW_REQUIRED", snapshot)
                logger.warning(
                    "startup scan review required: run_id=%s pile=%s confidence=%.3f reason=%s",
                    run_id,
                    pile.pile_id.as_key(),
                    result.confidence,
                    observation.reason,
                )
                return {
                    "run_id": run_id,
                    "status": "REVIEW_REQUIRED",
                    "seq": 0,
                    "metrics": self._metrics_payload(snapshot),
                }

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
