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
    recommend_recovery_action,
    review_reason_family,
)
from sorter.application.use_cases.execute_move import build_pick_place_sequence
from sorter.domain.events import DomainEvent
from sorter.domain.machine_state import NextMove, WorkflowState
from sorter.domain.models import MachineSnapshot
from sorter.config.calibration import CalibrationProfile
from sorter.ports.motion import MotionPort
from sorter.ports.camera import CameraPort
from sorter.ports.vacuum import VacuumPort
from sorter.ports.lights import LightsPort
from sorter.ports.recognizer import RecognizerPort
from sorter.ports.card_catalog import CardCatalogPort
from sorter.ports.run_store import RunStorePort
from sorter.ports.collection_service import CollectionEvent, CollectionServicePort


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
    collection_service: CollectionServicePort | None = None
    recognition_min_confidence: float = 0.6
    startup_scan_max_retries: int = 1
    verification_max_retries: int = 2
    last_recognition: dict[str, Any] | None = None

    def _run_id(self) -> str:
        return f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _metrics_payload(self, snapshot: MachineSnapshot) -> dict:
        return asdict(snapshot.run_state.metrics)

    def _set_run_substate(self, snapshot: MachineSnapshot, *, phase: str, active_command: str | None = None) -> None:
        snapshot.run_state.phase = phase
        snapshot.run_state.active_command = active_command

    def _pile_reference_xy(self, pile_id, calibration: CalibrationProfile) -> tuple[float, float]:
        pile_slot_number = self._pile_slot_number(pile_id)
        calibrated_xy = self._calibrated_pile_xy(calibration, pile_slot_number)
        if calibrated_xy is not None:
            return calibrated_xy
        pile = self.world.snapshot.get_pile(pile_id)
        if pile is not None:
            return (pile.x_mm, pile.y_mm)
        return self.world.coords.get(pile_id.as_key(), (0.0, 0.0))

    def _pile_slot_number(self, pile_id) -> int | None:
        ordered_piles = sorted(
            self.world.snapshot.piles.values(),
            key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()),
        )
        for index, pile in enumerate(ordered_piles, start=1):
            if pile.pile_id == pile_id:
                return index
        return None

    def _calibrated_pile_xy(self, calibration: CalibrationProfile, pile_slot_number: int | None) -> tuple[float, float] | None:
        if pile_slot_number is None:
            return None
        index = pile_slot_number - 1
        if index < 0 or index >= len(calibration.pile_positions_mm):
            return None
        return calibration.pile_positions_mm[index]

    def _review_payload(
        self,
        *,
        pile_id,
        phase: str,
        attempts: int,
        result,
        reason: str,
    ) -> dict[str, object]:
        pile_number = self._pile_slot_number(pile_id)
        phase_label = "startup discovery" if phase == "startup_scan" else "post-move verification"
        card_name = result.card_name or "(no confident card)"
        return {
            "phase": phase,
            "phase_label": phase_label,
            "pile_number": pile_number,
            "attempts": attempts,
            "recognized_name": card_name,
            "confidence": result.confidence,
            "reason": reason,
            "action": f"Check pile {pile_number} camera view/top card, then rerun."
            if pile_number is not None
            else "Check the camera view/top card, then rerun.",
        }

    def _camera_target_xy(self, pile_id, calibration: CalibrationProfile) -> tuple[float, float]:
        pile_x_mm, pile_y_mm = self._pile_reference_xy(pile_id, calibration)
        return calibration.camera_baseline_xy_for_vacuum_target(pile_x_mm, pile_y_mm)

    def _picker_target_xy(self, pile_id, calibration: CalibrationProfile) -> tuple[float, float]:
        return self._pile_reference_xy(pile_id, calibration)

    def _move_xy_when_safe(
        self,
        snapshot: MachineSnapshot,
        calibration: CalibrationProfile,
        x_mm: float,
        y_mm: float,
    ) -> None:
        calibration.assert_xy_travel_safe(snapshot.pose.z_mm)
        self.motion.move_xy(x_mm, y_mm)
        snapshot.pose.x_mm = x_mm
        snapshot.pose.y_mm = y_mm

    def move_vac_xy_when_safe(self, calibration: CalibrationProfile, x_mm: float, y_mm: float) -> None:
        self._move_xy_when_safe(self.world.snapshot, calibration, float(x_mm), float(y_mm))

    def move_camera_to_vacuum_xy_when_safe(self, calibration: CalibrationProfile, x_mm: float, y_mm: float) -> None:
        target_x_mm, target_y_mm = calibration.camera_baseline_xy_for_vacuum_target(x_mm, y_mm)
        self._move_xy_when_safe(self.world.snapshot, calibration, target_x_mm, target_y_mm)

    def move_vac_z(self, z_mm: float) -> None:
        self.motion.move_z(float(z_mm))
        self.world.snapshot.pose.z_mm = float(z_mm)

    def initialize_machine(self, calibration: CalibrationProfile) -> float:
        snapshot = self.world.snapshot
        self._set_run_substate(snapshot, phase="INITIALIZING", active_command="VacuumOff")
        self.vacuum.off()
        self.lights.set_status("running")
        self._set_run_substate(snapshot, phase="INITIALIZING", active_command="HomeAxes")
        self.motion.home_axes()
        snapshot.pose.x_mm = 0.0
        snapshot.pose.y_mm = 0.0
        snapshot.pose.z_mm = calibration.z_home_mm
        snapshot.pose.c_mm = calibration.c_home_mm
        travel_z_mm = calibration.xy_travel_z_mm()
        self._set_run_substate(snapshot, phase="INITIALIZING", active_command="MoveZToTravelClearance")
        self.move_vac_z(travel_z_mm)
        self._set_run_substate(snapshot, phase="INITIALIZING", active_command="WaitUntilIdle")
        self.motion.wait_until_idle()
        self.lights.set_status("idle")
        self._set_run_substate(snapshot, phase="IDLE", active_command=None)
        return travel_z_mm

    def _move_camera_over_pile(
        self,
        snapshot: MachineSnapshot,
        pile_id,
        calibration: CalibrationProfile,
        *,
        phase: str,
        active_command: str,
    ) -> None:
        target_x_mm, target_y_mm = self._camera_target_xy(pile_id, calibration)
        self._set_run_substate(snapshot, phase=phase, active_command=active_command)
        self._move_xy_when_safe(snapshot, calibration, target_x_mm, target_y_mm)

    def _move_picker_over_pile(
        self,
        snapshot: MachineSnapshot,
        pile_id,
        calibration: CalibrationProfile,
        *,
        phase: str,
        active_command: str,
    ) -> None:
        target_x_mm, target_y_mm = self._picker_target_xy(pile_id, calibration)
        self._set_run_substate(snapshot, phase=phase, active_command=active_command)
        self._move_xy_when_safe(snapshot, calibration, target_x_mm, target_y_mm)

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

    def _emit_collection_event(self, *, run_id: str, seq: int, event_type: str, payload: dict[str, Any]) -> None:
        if self.collection_service is None:
            return
        self.collection_service.record_event(
            CollectionEvent(run_id=run_id, sequence=seq, event_type=event_type, payload=payload)
        )

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
        phase_name = "VERIFYING" if phase == "verification" else "DISCOVERING"
        while True:
            attempts += 1
            self._set_run_substate(self.world.snapshot, phase=phase_name, active_command="CaptureFrame")
            frame = self.camera.capture_top_card(pile_id)
            self._set_run_substate(self.world.snapshot, phase=phase_name, active_command="RecognizeTopCard")
            result = self.recognizer.recognize_top_card(frame)
            self.last_recognition = {
                "backend": result.backend,
                "requested_mode": result.requested_mode,
                "effective_mode": result.effective_mode,
                "fallback_used": result.fallback_used,
                "card_name": result.card_name,
                "confidence": result.confidence,
                "failure_code": result.failure_code,
                "review_reason": result.review_reason,
            }
            self.world.snapshot.run_state.metrics.scan_count += 1
            increment_counter(
                self.world.snapshot.run_state.metrics.confidence_band_counts,
                confidence_band_for(result.confidence),
            )
            review_reason = classify_review_reason(frame, result)
            review_family = review_reason_family(review_reason)
            recovery_action = recommend_recovery_action(frame, result)
            if review_reason is not None:
                increment_counter(self.world.snapshot.run_state.metrics.review_reason_counts, review_reason)
            if review_family is not None:
                increment_counter(self.world.snapshot.run_state.metrics.review_family_counts, review_family)
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
                        "review_family": review_family,
                        "recovery_action": recovery_action,
                        "failure_code": result.failure_code,
                        "engine_review_reason": result.review_reason,
                        "requested_mode": result.requested_mode,
                        "effective_mode": result.effective_mode,
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
        self.last_recognition = None
        self._set_run_substate(snapshot, phase="DISCOVERING", active_command="StartupScan")
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
            calibration,
            should_stop=should_stop,
            per_command_delay_s=per_command_delay_s,
        )
        if startup_status is not None:
            return startup_status
        workflow = WorkflowState(snapshot)

        while True:
            if should_stop and should_stop():
                self._set_run_substate(snapshot, phase="IDLE", active_command=None)
                self.lights.set_status("idle")
                self._finish_run(run_id, "STOPPED", snapshot)
                logger.info("run stopped: run_id=%s seq=%s", run_id, seq)
                return {"run_id": run_id, "status": "STOPPED", "seq": seq, "metrics": self._metrics_payload(snapshot)}

            self._set_run_substate(snapshot, phase="PLANNING", active_command="PlanNextMove")
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
                    self._set_run_substate(snapshot, phase="FAULTED", active_command="NoMoveAvailable")
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
            self.run_store.append_event(
                run_id,
                seq,
                DomainEvent.now("command", {"name": "MoveToVerificationXY", "payload": {"pile": next_move.from_pile.as_key()}}),
            )
            self._move_camera_over_pile(
                snapshot,
                next_move.from_pile,
                calibration,
                phase="VERIFYING",
                active_command="MoveToVerificationXY",
            )
            if per_command_delay_s > 0:
                time.sleep(per_command_delay_s)
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
                "review_reason": classify_review_reason(verification.frame, verification_result),
                "review_family": review_reason_family(classify_review_reason(verification.frame, verification_result)),
                "recovery_action": recommend_recovery_action(verification.frame, verification_result),
                "failure_code": verification_result.failure_code,
                "engine_review_reason": verification_result.review_reason,
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
                self._set_run_substate(snapshot, phase="FAULTED", active_command="ReviewRequired")
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
                    "review": self._review_payload(
                        pile_id=next_move.from_pile,
                        phase="verification",
                        attempts=verification.attempts,
                        result=verification_result,
                        reason=verification.reason,
                    ),
                }

        self._set_run_substate(snapshot, phase="COMPLETED", active_command=None)
        self.lights.set_status("idle")
        self._finish_run(run_id, "COMPLETED", snapshot)
        logger.info("run completed: run_id=%s seq=%s", run_id, seq)
        return {"run_id": run_id, "status": "COMPLETED", "seq": seq, "metrics": self._metrics_payload(snapshot)}

    def _perform_startup_discovery_scan(
        self,
        run_id: str,
        snapshot: MachineSnapshot,
        calibration: CalibrationProfile,
        should_stop: Callable[[], bool] | None = None,
        per_command_delay_s: float = 0.0,
    ) -> dict | None:
        self._set_run_substate(snapshot, phase="DISCOVERING", active_command="StartupScan")
        logger.info("startup discovery scan started: run_id=%s piles=%s", run_id, len(snapshot.piles))
        for pile in snapshot.piles.values():
            if should_stop and should_stop():
                self._set_run_substate(snapshot, phase="IDLE", active_command=None)
                self.lights.set_status("idle")
                self._finish_run(run_id, "STOPPED", snapshot)
                logger.info("run stopped during startup scan: run_id=%s pile=%s", run_id, pile.pile_id.as_key())
                return {"run_id": run_id, "status": "STOPPED", "seq": 0, "metrics": self._metrics_payload(snapshot)}

            self.run_store.append_event(
                run_id,
                0,
                DomainEvent.now("command", {"name": "MoveToDiscoveryXY", "payload": {"pile": pile.pile_id.as_key()}}),
            )
            self._set_run_substate(snapshot, phase="DISCOVERING", active_command="MoveToDiscoveryXY")
            logger.debug(
                "startup discovery move: run_id=%s pile=%s",
                run_id,
                pile.pile_id.as_key(),
            )
            self._move_camera_over_pile(
                snapshot,
                pile.pile_id,
                calibration,
                phase="DISCOVERING",
                active_command="MoveToDiscoveryXY",
            )
            if per_command_delay_s > 0:
                time.sleep(per_command_delay_s)

            self.run_store.append_event(
                run_id,
                0,
                DomainEvent.now("command", {"name": "CaptureDiscovery", "payload": {"pile": pile.pile_id.as_key()}}),
            )
            self._set_run_substate(snapshot, phase="DISCOVERING", active_command="CaptureDiscovery")
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
                        "review_reason": classify_review_reason(observation.frame, result),
                        "review_family": review_reason_family(classify_review_reason(observation.frame, result)),
                        "recovery_action": recommend_recovery_action(observation.frame, result),
                        "failure_code": result.failure_code,
                        "engine_review_reason": result.review_reason,
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
                self._set_run_substate(snapshot, phase="FAULTED", active_command="StartupReviewRequired")
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
                    "review": self._review_payload(
                        pile_id=pile.pile_id,
                        phase="startup_scan",
                        attempts=observation.attempts,
                        result=result,
                        reason=observation.reason,
                    ),
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
            self._set_run_substate(snapshot, phase="EXECUTING", active_command=command.name)
            self.run_store.append_event(run_id, seq, DomainEvent.now("command", {"name": command.name, "payload": command.payload}))
            logger.debug(
                "command: run_id=%s seq=%s name=%s payload=%s",
                run_id,
                seq,
                command.name,
                command.payload,
            )
            if command.name == "MoveToSourceXY":
                self._move_picker_over_pile(
                    snapshot,
                    next_move.from_pile,
                    calibration,
                    phase="EXECUTING",
                    active_command=command.name,
                )
            elif command.name == "MoveToDestXY":
                self._move_picker_over_pile(
                    snapshot,
                    next_move.to_pile,
                    calibration,
                    phase="EXECUTING",
                    active_command=command.name,
                )
            elif command.name == "MoveZ":
                self.move_vac_z(float(command.payload["z_mm"]))
            elif command.name == "VacuumOn":
                self.vacuum.on()
                self.world.pick_from(next_move.from_pile)
            elif command.name == "VacuumOff":
                self.vacuum.off()
                self.world.place_to(next_move.to_pile)
            if per_command_delay_s > 0:
                time.sleep(per_command_delay_s)
        snapshot.run_state.metrics.move_count += 1
