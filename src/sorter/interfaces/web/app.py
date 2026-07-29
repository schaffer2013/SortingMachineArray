from __future__ import annotations

from collections import deque
from dataclasses import asdict
from datetime import datetime, UTC
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
import base64
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import tomllib
from typing import Any, Callable

from flask import Flask, Response, g, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw, ImageStat

from sorter.application.card_back_detection import (
    detect_card_back,
    refine_card_back_corners_to_truth,
    warp_card_back_image,
)
from sorter.application.card_back_training import (
    CaptureBox,
    CardBackTrainingStore,
    generate_spring_capture_points,
)
from sorter.application.visual_index_refresh import VISUAL_INDEX_REFRESH_DAY_OPTIONS, VisualIndexRefreshManager
from sorter.application.orchestrator import Orchestrator
from sorter.adapters.hardware.marlin_transport import MarlinSerialTransport
from sorter.adapters.hardware.neopixel_lights import NeoPixelLightsAdapter
from sorter.config.calibration import CalibrationProfile
from sorter.domain.models import PileState
from sorter.ports.camera import Frame


HARDWARE_CONTROL_ACTIONS = {
    "initialize",
    "home",
    "home_x",
    "home_y",
    "home_z",
    "home_c",
    "wait_idle",
    "move_xy",
    "jog_xy",
    "move_camera_xy",
    "move_z",
    "jog_z",
    "move_c",
    "jog_c",
    "jog_zc_interface",
    "vacuum_on",
    "vacuum_off",
    "lights",
    "light_profile",
}

MAX_SERIAL_XY_JOG_MM = 25.0
MAX_SERIAL_Z_JOG_MM = 5.0
MAX_SERIAL_C_JOG_MM = 5.0
MAX_SERIAL_ABSOLUTE_Z_MOVE_MM = 5.0
MAX_SERIAL_ABSOLUTE_C_MOVE_MM = 5.0
MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN = 6000.0
MAX_SERIAL_COMBINED_Z_SPEED_MM_PER_S = 30.0
SERIAL_CONNECT_TIMEOUT_SECONDS = 3.0
SERIAL_COMMAND_TIMEOUT_SECONDS = 10.0

MOTION_CONTROL_ACTIONS = {
    "initialize",
    "home",
    "home_x",
    "home_y",
    "home_z",
    "home_c",
    "wait_idle",
    "move_xy",
    "jog_xy",
    "move_camera_xy",
    "move_z",
    "jog_z",
    "move_c",
    "jog_c",
    "jog_zc_interface",
}

RECOGNITION_BACKEND_OPTIONS = (
    "fuzzy_enigma",
    "visual_retrieval",
    "moss_machine",
    "sim_truth",
)


class SerialBoardSession:
    def __init__(
        self,
        event_logger: Callable[[str, dict[str, Any] | None], None] | None = None,
        serial_log_path: Path | None = None,
        shared_transport: MarlinSerialTransport | None = None,
    ):
        self.event_logger = event_logger
        self.serial_log_path = serial_log_path
        self.shared_transport = shared_transport
        self.transport: MarlinSerialTransport | None = None
        self.lights: NeoPixelLightsAdapter | None = None
        self.owns_transport = True
        self.port: str | None = None
        self.baud_rate = 115200
        self.last_error: str | None = None
        self.last_response: list[str] = []
        self.last_endstops: dict[str, str] = {}
        self.serial_command_log: deque[dict[str, Any]] = deque(maxlen=500)
        self.serial_poll_log: deque[dict[str, Any]] = deque(maxlen=500)
        self.controller_fault = False
        self.live_pose: dict[str, float] = {}
        self.last_success_monotonic: float | None = None
        self.connection_state = "disconnected"
        self.state_lock = threading.RLock()
        self.command_lock = threading.Lock()
        self._load_persistent_serial_log()

    def _acquire_command(self, *, poll: bool = False) -> bool:
        if poll:
            return self.command_lock.acquire(blocking=False)
        return self.command_lock.acquire(timeout=10.0)

    def status(self) -> dict[str, Any]:
        with self.state_lock:
            session_open = self.transport is not None
            verified = session_open and self.connection_state == "verified"
            if verified and self.last_success_monotonic is not None:
                if time.monotonic() - self.last_success_monotonic > 5.0:
                    verified = False
                    state = "stale"
                else:
                    state = "verified"
            else:
                state = (
                    self.connection_state
                    if session_open or self.connection_state in {"connecting", "disconnecting", "error", "faulted"}
                    else "disconnected"
                )
            return {
                "connected": verified,
                "session_open": session_open,
                "connection_state": state,
                "controller_fault": self.controller_fault,
                "busy": self.command_lock.locked(),
                "port": self.port,
                "baud_rate": self.baud_rate,
                "last_error": self.last_error,
                "last_response": self.last_response,
                "last_endstops": self.last_endstops,
                "serial_command_log": list(self.serial_command_log),
                "serial_poll_log": list(self.serial_poll_log),
                "live_pose": self.live_pose,
            }

    def list_ports(self) -> list[dict[str, str]]:
        try:
            from serial.tools import list_ports
        except Exception as exc:
            self.last_error = f"pyserial is required for serial port discovery: {exc}"
            return []
        ports = []
        for port in list_ports.comports():
            ports.append(
                {
                    "device": port.device,
                    "description": port.description or "",
                    "hwid": port.hwid or "",
                }
            )
        return ports

    def auto_connect(self) -> dict[str, Any]:
        if self.status()["session_open"]:
            return {"ok": True, "message": f"Already connected to {self.port}", **self.status()}
        ports = self.list_ports()
        self._record_event("serial.auto_connect.start", {"ports": ports})
        for item in sorted(ports, key=_port_auto_score, reverse=True):
            try:
                return self.connect(item["device"])
            except Exception as exc:
                self._record_event("serial.auto_connect.port_failed", {"port": item.get("device"), "error": str(exc)})
                continue
        message = self.last_error or "No serial board responded to M115"
        self._record_event("serial.auto_connect.failed", {"message": message})
        return {"ok": False, "message": message, **self.status()}

    def connect(self, port: str, baud_rate: int = 115200) -> dict[str, Any]:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        started_at = time.monotonic()
        self._record_event("serial.connect.start", {"port": port, "baud_rate": int(baud_rate)})
        try:
            with self.state_lock:
                if self.transport is not None and self.owns_transport:
                    self.transport.close()
                self.transport = None
                self.lights = None
                self.owns_transport = True
                self.port = port
                self.baud_rate = int(baud_rate)
                self.connection_state = "connecting"
                self.last_error = None
            transport, owns_transport = self._transport_for_port(port, int(baud_rate))
            try:
                sent_at = _utc_now_iso()
                response = transport.send_command("M115")
                _set_transport_timeout(transport, SERIAL_COMMAND_TIMEOUT_SECONDS)
            except Exception as exc:
                self._record_serial_command("M115", sent_at, [], ok=False, error=str(exc))
                if owns_transport:
                    transport.close()
                with self.state_lock:
                    self.transport = None
                    self.lights = None
                    self.owns_transport = True
                    self.last_error = str(exc)
                    self.last_response = []
                    self.connection_state = "error"
                self._record_event(
                    "serial.connect.failed",
                    {"port": port, "baud_rate": int(baud_rate), "elapsed_ms": _elapsed_ms(started_at), "error": str(exc)},
                )
                raise
            with self.state_lock:
                self.transport = transport
                self.owns_transport = owns_transport
                self.lights = NeoPixelLightsAdapter(transport=transport)
                self.last_error = None
                self.last_response = response
                self._record_serial_command("M115", sent_at, response, ok=True)
                self.controller_fault = False
                self.last_success_monotonic = time.monotonic()
                self.connection_state = "verified"
            self._record_event(
                "serial.connect.succeeded",
                {
                    "port": port,
                    "baud_rate": int(baud_rate),
                    "elapsed_ms": _elapsed_ms(started_at),
                    "response": response,
                },
            )
            return {"ok": True, "message": f"Connected to {port}", **self.status()}
        finally:
            self.command_lock.release()

    def disconnect(self) -> dict[str, Any]:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        self._record_event("serial.disconnect.start", {"port": self.port, "state": self.connection_state})
        try:
            with self.state_lock:
                transport = self.transport
                owns_transport = self.owns_transport
                self.transport = None
                self.lights = None
                self.owns_transport = True
                self.connection_state = "disconnecting"
            if transport is None:
                with self.state_lock:
                    self.port = None
                    self.connection_state = "disconnected"
                    self.controller_fault = False
                    self.last_error = None
                self._record_event("serial.disconnect.noop", {})
                return {"ok": True, "message": "Already disconnected", **self.status()}
            if transport is not None and owns_transport:
                transport.close()
            with self.state_lock:
                self.port = None
                self.connection_state = "disconnected"
                self.controller_fault = False
                self.last_error = None
            self._record_event("serial.disconnect.succeeded", {})
            return {"ok": True, "message": "Disconnected", **self.status()}
        finally:
            self.command_lock.release()

    def send_command(self, command: str) -> dict[str, Any]:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        try:
            result = self._send_command_locked(command)
        finally:
            self.command_lock.release()
        return {**result, **self.status()}

    def send_status_poll(self, command: str) -> dict[str, Any]:
        if not self._acquire_command(poll=True):
            return {"ok": False, "message": "Skipped status poll; serial board is busy", **self.status()}
        try:
            result = self._send_command_locked(command, log_kind="poll")
        finally:
            self.command_lock.release()
        return {**result, **self.status()}

    def _send_command_locked(self, command: str, *, log_kind: str = "command") -> dict[str, Any]:
        clean_command = command.strip()
        if not clean_command:
            raise ValueError("Marlin command cannot be empty")
        with self.state_lock:
            transport = self.transport
        if transport is None:
            raise ValueError("Serial board is not connected")
        sent_at = _utc_now_iso()
        try:
            response = transport.send_command(clean_command)
        except Exception as exc:
            response = list(getattr(exc, "responses", []))
            is_fault = _is_controller_fault(str(exc))
            with self.state_lock:
                self.last_error = str(exc)
                self._record_serial_command(clean_command, sent_at, response, ok=False, error=str(exc), log_kind=log_kind)
                self.controller_fault = is_fault or self.controller_fault
                self.connection_state = "faulted" if is_fault else "error"
                if self.transport is not None:
                    self.transport.close()
                self.transport = None
                self.lights = None
                self.owns_transport = True
            raise
        pose = _parse_m114(response)
        fault_response = next((line for line in response if _is_controller_fault(line)), None)
        if fault_response is not None:
            with self.state_lock:
                self.last_error = fault_response
                self.last_response = response
                self._record_serial_command(clean_command, sent_at, response, ok=False, error=fault_response, log_kind=log_kind)
                self.controller_fault = True
                self.connection_state = "faulted"
            raise RuntimeError(fault_response)
        with self.state_lock:
            self.last_error = None
            self.last_response = response
            self._record_serial_command(clean_command, sent_at, response, ok=True, log_kind=log_kind)
            self.last_success_monotonic = time.monotonic()
            self.connection_state = "verified"
            if pose:
                self.live_pose.update(pose)
        return {"ok": True, "message": f"Sent {clean_command}", "response": response, **self.status()}

    def send_commands(self, commands: list[str], *, message: str) -> dict[str, Any]:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        try:
            responses: list[str] = []
            for command in commands:
                result = self._send_command_locked(command)
                responses.extend(result["response"])
        finally:
            self.command_lock.release()
        return {"ok": True, "message": message, "response": responses, **self.status()}

    def read_endstops(self, *, poll: bool = False) -> dict[str, Any]:
        if not self._acquire_command(poll=poll):
            if poll:
                return {
                    "ok": False,
                    "message": "Skipped endstop poll; serial board is busy",
                    "endstops": self.last_endstops,
                    **self.status(),
                }
            raise RuntimeError("Serial board is busy with another command")
        try:
            result = self._send_command_locked("M119", log_kind="poll")
            endstops = _parse_m119(result["response"])
            with self.state_lock:
                self.last_endstops = endstops
        finally:
            self.command_lock.release()
        return {"ok": True, "message": "Read endstop states", "endstops": endstops, **self.status()}

    def bltouch(self, action: str) -> dict[str, Any]:
        commands = {
            "deploy": "M401",
            "stow": "M402",
            "reset": "M280 P0 S160",
            "self_test": "M280 P0 S120",
            "probe": "G30",
        }
        command = commands.get(action)
        if command is None:
            raise ValueError(f"Unsupported BLTouch action: {action}")
        result = self.send_command(command)
        result["bltouch_action"] = action
        return result

    def set_lights_status(self, status: str) -> None:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        try:
            with self.state_lock:
                lights = self.lights
            if lights is not None:
                red, green, blue = lights.STATUS_RGB.get(status, lights.STATUS_RGB["warning"])
                lights.last_status = status
                lights.last_profile = status
                lights.last_rgb = (red, green, blue)
                lights.last_command = f"M150 R{red} U{green} B{blue}"
                self._send_command_locked(lights.last_command)
        except Exception as exc:
            with self.state_lock:
                self.last_error = str(exc)
                self.connection_state = "error"
                if self.transport is not None:
                    self.transport.close()
                self.transport = None
                self.lights = None
                self.owns_transport = True
            raise
        finally:
            self.command_lock.release()

    def set_lights_rgb(self, red: int, green: int, blue: int, *, profile_name: str | None = None) -> None:
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        try:
            with self.state_lock:
                lights = self.lights
            if lights is not None:
                r, g, b = (_clamp_channel(red), _clamp_channel(green), _clamp_channel(blue))
                lights.last_status = profile_name or "custom"
                lights.last_profile = profile_name or "custom"
                lights.last_rgb = (r, g, b)
                lights.last_command = f"M150 R{r} U{g} B{b}"
                self._send_command_locked(lights.last_command)
        except Exception as exc:
            with self.state_lock:
                self.last_error = str(exc)
                self.connection_state = "error"
                if self.transport is not None:
                    self.transport.close()
                self.transport = None
                self.lights = None
                self.owns_transport = True
            raise
        finally:
            self.command_lock.release()

    def set_neopixel_pixels(self, pixels: list[tuple[int, int, int]]) -> dict[str, Any]:
        if len(pixels) != 16:
            raise ValueError("NeoPixel display requires exactly 16 pixels")
        if not self._acquire_command():
            raise RuntimeError("Serial board is busy with another command")
        try:
            responses: list[str] = []
            for index, (red, green, blue) in enumerate(pixels):
                command = (
                    f"M150 I{index} "
                    f"R{_clamp_channel(red)} U{_clamp_channel(green)} B{_clamp_channel(blue)}"
                )
                result = self._send_command_locked(command)
                responses.extend(result["response"])
            return {"ok": True, "message": "Applied 16-pixel NeoPixel display", "response": responses, **self.status()}
        finally:
            self.command_lock.release()

    def _record_serial_command(
        self,
        command: str,
        sent_at: str,
        response: list[str],
        *,
        ok: bool,
        error: str | None = None,
        log_kind: str = "command",
    ) -> None:
        entry = {
            "sent_at": sent_at,
            "command": command,
            "response": list(response),
            "ok": ok,
            "error": error,
        }
        if log_kind == "poll":
            self.serial_poll_log.append(entry)
        else:
            self.serial_command_log.append(entry)
        self._append_persistent_serial_log({**entry, "kind": log_kind})
        self._record_event(
            f"serial.{log_kind}",
            {
                "command": command,
                "ok": ok,
                "error": error,
                "response": list(response)[-10:],
                "port": self.port,
                "connection_state": self.connection_state,
            },
        )

    def _record_event(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.event_logger is None:
            return
        try:
            self.event_logger(event, details or {})
        except Exception:
            pass

    def _transport_for_port(self, port: str, baud_rate: int) -> tuple[MarlinSerialTransport, bool]:
        shared = self.shared_transport
        if shared is not None and str(getattr(shared, "serial_port", "")) == str(port):
            shared.baud_rate = baud_rate
            shared.timeout_seconds = SERIAL_CONNECT_TIMEOUT_SECONDS
            return shared, False
        return (
            MarlinSerialTransport(
                serial_port=port,
                baud_rate=baud_rate,
                timeout_seconds=SERIAL_CONNECT_TIMEOUT_SECONDS,
            ),
            True,
        )

    def _append_persistent_serial_log(self, entry: dict[str, Any]) -> None:
        if self.serial_log_path is None:
            return
        try:
            self.serial_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.serial_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_json_safe(entry), sort_keys=True) + "\n")
        except Exception:
            pass

    def _load_persistent_serial_log(self) -> None:
        if self.serial_log_path is None or not self.serial_log_path.exists():
            return
        try:
            lines = self.serial_log_path.read_text(encoding="utf-8").splitlines()[-1000:]
            for line in lines:
                if not line.strip():
                    continue
                entry = json.loads(line)
                kind = entry.pop("kind", "command")
                if kind == "poll":
                    self.serial_poll_log.append(entry)
                else:
                    self.serial_command_log.append(entry)
        except Exception:
            return


def _port_auto_score(port: dict[str, str]) -> tuple[int, str]:
    text = " ".join([port.get("device", ""), port.get("description", ""), port.get("hwid", "")]).lower()
    score = 0
    if "usb" in text:
        score += 10
    if "bluetooth" in text or "bthenum" in text:
        score -= 20
    if "unknown" in text:
        score -= 5
    return (score, port.get("device", ""))


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


def _set_transport_timeout(transport: MarlinSerialTransport, timeout_seconds: float) -> None:
    transport.timeout_seconds = timeout_seconds
    try:
        connection = transport.open()
        setattr(connection, "timeout", timeout_seconds)
    except Exception:
        pass


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


def _request_debug_payload() -> dict[str, Any] | None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return _trim_debug_payload(payload)
        return {"value": _json_safe(payload)}
    if request.form or request.files:
        return {
            "form": _trim_debug_payload(dict(request.form.items())),
            "files": {
                name: {
                    "filename": storage.filename,
                    "content_type": storage.content_type,
                }
                for name, storage in request.files.items()
            },
        }
    content_length = request.content_length
    if content_length:
        return {"content_length": content_length, "content_type": request.content_type}
    return None


def _trim_debug_payload(payload: dict[str, Any], *, max_value_length: int = 500) -> dict[str, Any]:
    trimmed: dict[str, Any] = {}
    for key, value in payload.items():
        safe_value = _json_safe(value)
        if isinstance(safe_value, str) and len(safe_value) > max_value_length:
            trimmed[key] = f"{safe_value[:max_value_length]}...<truncated>"
        else:
            trimmed[key] = safe_value
    return trimmed


def _is_controller_fault(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            "printer halted",
            "printer stopped",
            "kill() called",
            "//action:notification stopped",
        )
    )


def _parse_m119(lines: list[str]) -> dict[str, str]:
    endstops: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        name, state = line.split(":", 1)
        normalized_name = name.strip()
        normalized_state = state.strip()
        if normalized_name and normalized_state.lower() in {"open", "triggered"}:
            endstops[normalized_name] = normalized_state.lower()
    return endstops


def _parse_m114(lines: list[str]) -> dict[str, float]:
    pose: dict[str, float] = {}
    for line in lines:
        position_part = line.split(" Count ", 1)[0]
        for token in position_part.split():
            if ":" not in token:
                continue
            axis, value = token.split(":", 1)
            normalized_axis = axis.strip().lower()
            if normalized_axis not in {"x", "y", "z", "c", "w"}:
                continue
            try:
                pose["c" if normalized_axis == "w" else normalized_axis] = float(value)
            except ValueError:
                continue
    return pose


class WebRuntime:
    def __init__(
        self,
        orchestrator: Orchestrator,
        calibration: CalibrationProfile,
        slow_ms: int = 0,
        light_profiles_path: Path | None = None,
        light_profiles_seed_path: Path | None = None,
        calibration_path: Path | None = None,
        runtime_mode: str = "hardware",
    ):
        self.orchestrator = orchestrator
        self.calibration = calibration
        self.slow_ms = max(0, slow_ms)
        self.stop_event = threading.Event()
        self.run_thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_manual_recognition: dict[str, Any] | None = None
        self.last_card_back_detection: dict[str, Any] | None = None
        self.machine_initialized = False
        self.homed_axes: set[str] = set()
        self.light_profiles_path = light_profiles_path
        self.light_profiles_seed_path = light_profiles_seed_path
        self.calibration_path = calibration_path
        self.repo_root = _repo_root()
        self.visual_index = VisualIndexRefreshManager(project_root=self.repo_root)
        self.control_audit_path = self.repo_root / "data" / "logs" / "control_audit.jsonl"
        self.debug_events_path = self.repo_root / "data" / "logs" / "debug_events.jsonl"
        self.serial_log_path = self.repo_root / "data" / "logs" / "serial_commands.jsonl"
        self.saved_positions_path = self.repo_root / "local_data" / "saved_positions.json"
        self.card_back_training = CardBackTrainingStore(self.repo_root / "local_data" / "card_back_training")
        self.light_profiles = self._load_light_profiles()
        self.runtime_mode = runtime_mode
        self.hardware_runtime = bool(getattr(orchestrator, "hardware_runtime", False))
        self.shared_marlin_transport = self._shared_marlin_transport()
        self.serial_board = SerialBoardSession(
            event_logger=self.record_debug_event,
            serial_log_path=self.serial_log_path,
            shared_transport=self.shared_marlin_transport,
        )
        self.lock = threading.RLock()

    def start_run(self) -> dict[str, Any]:
        with self.lock:
            if self.runtime_mode != "simulation" and not self.hardware_runtime:
                return {
                    "ok": False,
                    "message": "Automated runs require Simulation runtime until the hardware run path is implemented",
                }
            if self.run_thread and self.run_thread.is_alive():
                return {"ok": False, "message": "Run already active"}
            if not self.machine_initialized:
                return {"ok": False, "message": "Initialize machine before starting a run"}
            self.stop_event.clear()
            self.last_result = None
            self.last_error = None
            self.run_thread = threading.Thread(target=self._run_worker, daemon=True)
            self.run_thread.start()
            return {"ok": True, "message": "Run started"}

    def stop_run(self) -> None:
        self.stop_event.set()

    def _run_worker(self) -> None:
        try:
            result = self.orchestrator.run_once(
                self.calibration,
                should_stop=lambda: self.stop_event.is_set(),
                per_command_delay_s=self.slow_ms / 1000.0,
            )
            with self.lock:
                self.last_result = result
        except Exception as exc:  # pragma: no cover - surfaced to UI
            with self.lock:
                self.last_error = str(exc)

    def status(self) -> dict[str, Any]:
        snapshot = self.orchestrator.world.snapshot
        run_state = snapshot.run_state
        with self.lock:
            serial_status = self.serial_board.status()
            live_connected = self.runtime_mode == "hardware" and bool(serial_status["connected"])
            session_open = bool(serial_status.get("session_open"))
            runtime_target = "simulation" if self.runtime_mode == "simulation" else (
                "hardware_direct" if self.hardware_runtime else ("hardware_serial" if live_connected else "hardware_unavailable")
            )
            pose = asdict(snapshot.pose)
            if live_connected:
                live_pose = serial_status.get("live_pose", {})
                pose = {
                    **pose,
                    "x_mm": float(live_pose.get("x", pose["x_mm"])),
                    "y_mm": float(live_pose.get("y", pose["y_mm"])),
                    "z_mm": float(live_pose.get("z", pose["z_mm"])),
                    "c_mm": float(live_pose.get("c", pose["c_mm"])),
                }
            active = bool(self.run_thread and self.run_thread.is_alive())
            if active:
                lifecycle = "RUNNING"
            elif self.last_result:
                lifecycle = str(self.last_result.get("status", "DONE"))
            else:
                lifecycle = "IDLE"
            return {
                "lifecycle": lifecycle,
                "runtime_mode": self.runtime_mode,
                "runtime_target": runtime_target,
                "runtime_message": (
                    "Simulation"
                    if self.runtime_mode == "simulation"
                    else (
                        "Hardware: direct Pi"
                        if self.hardware_runtime
                        else f"Hardware: live {serial_status['port']}"
                        if live_connected
                        else (
                        f"Hardware: {serial_status.get('connection_state')} {serial_status.get('port')}"
                        if session_open
                        else "Hardware: connect serial board"
                        )
                    )
                ),
                "phase": run_state.phase,
                "active_command": run_state.active_command,
                "pose": pose,
                "metrics": asdict(run_state.metrics),
                "vacuum_on": bool(self.orchestrator.vacuum.is_on()),
                "lights_status": getattr(self.orchestrator.lights, "status", getattr(self.orchestrator.lights, "last_status", "unknown")),
                "lights_profile": getattr(self.orchestrator.lights, "last_profile", None),
                "lights_rgb": list(getattr(self.orchestrator.lights, "last_rgb", ())),
                "last_result": self.last_result,
                "last_error": self.last_error,
                "last_recognition": getattr(self.orchestrator, "last_recognition", None),
                "last_manual_recognition": self.last_manual_recognition,
                "last_card_back_detection": self.last_card_back_detection,
                "machine_initialized": self.machine_initialized,
                "calibration": self.calibration_payload(),
                "serial_board": serial_status,
            }

    def set_runtime_mode(self, mode: str) -> dict[str, Any]:
        normalized = mode.strip().lower()
        if normalized not in {"hardware", "simulation"}:
            raise ValueError("Runtime mode must be 'hardware' or 'simulation'")
        with self.lock:
            self.runtime_mode = normalized
        return {"ok": True, "runtime_mode": normalized, "status": self.status()}

    def calibration_payload(self) -> dict[str, Any]:
        return self.calibration.to_json_dict()

    def card_back_training_summary(self) -> dict[str, Any]:
        return self.card_back_training.summary()

    def create_card_back_training_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = self.card_back_training.create_model(
            str(payload.get("name", "")),
            base_model_id=payload.get("base_model_id") or None,
            notes=str(payload.get("notes", "")),
        )
        return {"ok": True, "model": model, "summary": self.card_back_training_summary()}

    def set_active_card_back_training_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = self.card_back_training.set_active_model(str(payload.get("model_id", "")))
        return {"ok": True, "model": model, "summary": self.card_back_training_summary()}

    def delete_card_back_training_model(self, model_id: str) -> dict[str, Any]:
        result = self.card_back_training.delete_model(model_id)
        return {"ok": True, **result}

    def generate_card_back_capture_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_box = payload.get("box") if isinstance(payload.get("box"), dict) else payload
        capture_box = CaptureBox.from_payload(raw_box)
        count = int(payload.get("count", payload.get("point_count", 12)))
        seed = payload.get("seed")
        seed_value = int(seed) if seed not in (None, "") else None
        points = generate_spring_capture_points(capture_box, count, seed=seed_value)
        rng = random.Random(seed_value)
        light_min = max(0, min(255, int(payload.get("light_min", 0))))
        light_max = max(light_min, min(255, int(payload.get("light_max", 96))))
        plan = [
            {
                "index": index,
                "point": point,
                "lighting": {"mode": "random_pixels", "pixels": self._random_training_pixels(rng, light_min, light_max)},
                "split": "staged",
            }
            for index, point in enumerate(points, start=1)
        ]
        return {"ok": True, "box": raw_box, "seed": seed_value, "count": len(plan), "plan": plan}

    def capture_card_back_training_sample(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = str(payload.get("model_id") or self.card_back_training_summary().get("active_model_id") or "")
        if not model_id:
            raise ValueError("Create or select a training model before capturing samples")
        point = payload.get("point") if isinstance(payload.get("point"), dict) else None
        lighting = payload.get("lighting") if isinstance(payload.get("lighting"), dict) else {}
        settle_ms = max(0, min(5000, int(payload.get("settle_ms", 120))))
        if payload.get("execute_motion") and point:
            self.control(
                "move_camera_xy",
                {
                    "x_mm": float(point["x_mm"]),
                    "y_mm": float(point["y_mm"]),
                    "z_mm": float(point["z_mm"]),
                    "coordinate_space": "camera",
                    "confirm_large_move": True,
                },
            )
            self.control("wait_idle", {})
            time.sleep(1.0)
        if lighting.get("pixels"):
            self._set_light_pixels(lighting["pixels"], profile_name="training-capture")
        elif all(key in lighting for key in ("red", "green", "blue")):
            self._set_light_rgb(lighting["red"], lighting["green"], lighting["blue"], profile_name="training-capture")
        if settle_ms:
            time.sleep(settle_ms / 1000)
        image = self.latest_camera_image()
        detection = payload.get("detection") if isinstance(payload.get("detection"), dict) else None
        if detection is None and payload.get("run_detection", True):
            detection = self._detect_card_back_with_method(image, str(payload.get("detection_method") or "original"))
        sample = self.card_back_training.capture_sample(
            model_id,
            image,
            point=point,
            lighting=lighting,
            detection=detection,
            expected_crop=payload.get("expected_crop") if isinstance(payload.get("expected_crop"), dict) else None,
            truth_corners=payload.get("truth_corners_px") if isinstance(payload.get("truth_corners_px"), dict) else None,
            split=str(payload.get("split", "staged")),
        )
        self.record_debug_event(
            "camera.card_back.training_capture",
            {"model_id": model_id, "sample_id": sample["sample_id"], "split": sample["split"], "point": sample.get("point")},
        )
        return {"ok": True, "sample": sample, "summary": self.card_back_training_summary()}

    def update_card_back_training_sample(self, model_id: str, sample_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        sample = self.card_back_training.update_sample_label(model_id, sample_id, payload)
        return {"ok": True, "sample": sample, "summary": self.card_back_training_summary()}

    def delete_card_back_training_sample(self, model_id: str, sample_id: str) -> dict[str, Any]:
        result = self.card_back_training.delete_sample(model_id, sample_id)
        return {"ok": True, **result, "summary": self.card_back_training_summary()}

    def register_card_back_training_run(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.card_back_training.register_training_run(model_id, payload)
        return {"ok": True, **result, "summary": self.card_back_training_summary()}

    def _random_training_pixels(self, rng: random.Random, light_min: int, light_max: int) -> list[list[int]]:
        base = [rng.randint(light_min, light_max) for _ in range(3)]
        jitter = max(6, int((light_max - light_min) * 0.35))
        pixels = []
        for _ in range(16):
            pixels.append([
                _clamp_channel(base[channel] + rng.randint(-jitter, jitter))
                for channel in range(3)
            ])
        return pixels

    def update_calibration(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "camera_offset_x_mm",
            "camera_offset_y_mm",
            "camera_offset_z_mm",
            "min_xy_travel_z_mm",
            "z_home_mm",
            "c_home_mm",
            "safe_z_mm",
            "pick_z_mm",
            "place_z_mm",
            "probe_enabled",
            "probe_retract_z_mm",
            "probe_place_clearance_mm",
            "probe_max_contact_z_mm",
        }
        updates = {key: payload[key] for key in allowed_fields if key in payload}
        if not updates:
            raise ValueError("No supported calibration fields provided")
        with self.lock:
            self.calibration = self.calibration.with_updates(**updates)
            saved_path = None
            if self.calibration_path is not None:
                self.calibration.save(self.calibration_path)
                saved_path = str(self.calibration_path)
            message = (
                f"Calibration saved to {saved_path}"
                if saved_path
                else "Calibration applied for this running session"
            )
            return {"ok": True, "message": message, "calibration": self.calibration_payload(), "saved_path": saved_path}

    def snapshot(self) -> dict[str, Any]:
        snapshot = self.orchestrator.world.snapshot
        piles = sorted(
            snapshot.piles.values(),
            key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()),
        )
        return {
            "piles": [self._pile_payload(index, pile) for index, pile in enumerate(piles, start=1)],
            "pose": asdict(snapshot.pose),
            "run_state": {
                "phase": snapshot.run_state.phase,
                "active_command": snapshot.run_state.active_command,
                "metrics": asdict(snapshot.run_state.metrics),
            },
        }

    def saved_positions_payload(self) -> dict[str, Any]:
        return {"positions": self._load_saved_positions()}

    def create_saved_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        positions = self._load_saved_positions()
        position = self._saved_position_from_payload(payload)
        position["id"] = self._unique_saved_position_id(position["name"], positions)
        now = _utc_now_iso()
        position["created_at_utc"] = now
        position["updated_at_utc"] = now
        positions.append(position)
        self._save_saved_positions(positions)
        return {"ok": True, "position": position, "positions": positions}

    def update_saved_position(self, position_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        positions = self._load_saved_positions()
        for index, position in enumerate(positions):
            if position.get("id") == position_id:
                updated = {**position, **self._saved_position_from_payload(payload), "id": position_id}
                updated["created_at_utc"] = position.get("created_at_utc") or _utc_now_iso()
                updated["updated_at_utc"] = _utc_now_iso()
                positions[index] = updated
                self._save_saved_positions(positions)
                return {"ok": True, "position": updated, "positions": positions}
        raise ValueError(f"Unknown saved position: {position_id}")

    def delete_saved_position(self, position_id: str) -> dict[str, Any]:
        positions = self._load_saved_positions()
        remaining = [position for position in positions if position.get("id") != position_id]
        if len(remaining) == len(positions):
            raise ValueError(f"Unknown saved position: {position_id}")
        self._save_saved_positions(remaining)
        return {"ok": True, "deleted_position_id": position_id, "positions": remaining}

    def go_to_saved_position(self, position_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not all(axis in self.homed_axes for axis in ("x", "y", "z", "c")):
            raise ValueError("Home all axes before going to a saved XYZ position")
        position = next((item for item in self._load_saved_positions() if item.get("id") == position_id), None)
        if position is None:
            raise ValueError(f"Unknown saved position: {position_id}")
        coordinate_space = str((payload or {}).get("coordinate_space") or "vacuum").strip().lower()
        if coordinate_space not in {"vacuum", "camera"}:
            raise ValueError(f"Unsupported saved position coordinate space: {coordinate_space}")
        action = "move_camera_xy" if coordinate_space == "camera" else "move_xy"
        result = self.control(
            action,
            {
                "x_mm": position["x_mm"],
                "y_mm": position["y_mm"],
                "z_mm": position["z_mm"],
                "coordinate_space": coordinate_space,
                "confirm_large_move": True,
            },
        )
        return {
            "ok": True,
            "position": position,
            "coordinate_space": coordinate_space,
            "message": f"Went to saved {coordinate_space} position {position['name']}: {result.get('message', '')}",
        }

    def _load_saved_positions(self) -> list[dict[str, Any]]:
        if not self.saved_positions_path.exists():
            return []
        with self.saved_positions_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_positions = payload.get("positions", []) if isinstance(payload, dict) else []
        return [
            self._saved_position_from_payload(position, position_id=str(position.get("id", "")))
            for position in raw_positions
            if isinstance(position, dict) and position.get("id")
        ]

    def _save_saved_positions(self, positions: list[dict[str, Any]]) -> None:
        self.saved_positions_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.saved_positions_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps({"positions": positions}, indent=2), encoding="utf-8")
        temp_path.replace(self.saved_positions_path)

    def _saved_position_from_payload(self, payload: dict[str, Any], *, position_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Saved position name is required")
        position = {
            "name": name,
            "x_mm": round(float(payload["x_mm"]), 3),
            "y_mm": round(float(payload["y_mm"]), 3),
            "z_mm": round(float(payload["z_mm"]), 3),
            "notes": str(payload.get("notes") or ""),
        }
        if position_id:
            position["id"] = position_id
        if payload.get("created_at_utc"):
            position["created_at_utc"] = str(payload["created_at_utc"])
        if payload.get("updated_at_utc"):
            position["updated_at_utc"] = str(payload["updated_at_utc"])
        return position

    def _unique_saved_position_id(self, name: str, positions: list[dict[str, Any]]) -> str:
        stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "position"
        candidate = f"{stem}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        existing = {str(position.get("id")) for position in positions}
        suffix = 1
        unique = candidate
        while unique in existing:
            suffix += 1
            unique = f"{candidate}-{suffix}"
        return unique

    def _pile_payload(self, index: int, pile: PileState) -> dict[str, Any]:
        return {
            "number": index,
            "key": pile.pile_id.as_key(),
            "role": pile.role.value,
            "capacity": pile.capacity,
            "count": pile.num_cards() if pile.has_known_count() else None,
            "known_count": pile.has_known_count(),
            "observation_state": pile.observation.state.value,
            "top_card_name": pile.observation.top_card_name,
            "confidence": pile.observation.confidence,
            "x_mm": pile.x_mm,
            "y_mm": pile.y_mm,
            "image_available": bool(self.orchestrator.world.top_card_image_path(pile.pile_id)),
        }

    def initialize_machine(self) -> dict[str, Any]:
        with self.lock:
            travel_z_mm = self.orchestrator.initialize_machine(self.calibration)
            self.machine_initialized = True
            self._mark_axes_homed("x", "y", "z", "c")
            return {
                "ok": True,
                "message": f"Machine initialized and homed; vacuum Z at {travel_z_mm:.2f} mm travel clearance",
            }

    def control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.runtime_mode == "hardware" and action in HARDWARE_CONTROL_ACTIONS:
            return self._hardware_control(action, payload)
        if action == "initialize":
            return self.initialize_machine()
        if action == "home":
            self.orchestrator.motion.home_axes()
            snapshot = self.orchestrator.world.snapshot
            snapshot.pose.x_mm = 0.0
            snapshot.pose.y_mm = 0.0
            snapshot.pose.z_mm = self.calibration.z_home_mm
            snapshot.pose.c_mm = self.calibration.c_home_mm
            self._mark_axes_homed("x", "y", "z", "c")
            self.machine_initialized = False
            return {
                "ok": True,
                "message": (
                    f"Axes homed; X/Y at 0.00 mm, Z at {self.calibration.z_home_mm:.2f} mm, "
                    f"C at {self.calibration.c_home_mm:.2f} mm"
                ),
            }
        if action in {"home_x", "home_y", "home_z", "home_c"}:
            snapshot = self.orchestrator.world.snapshot
            axis = action.removeprefix("home_")
            if axis == "x":
                snapshot.pose.x_mm = 0.0
            elif axis == "y":
                snapshot.pose.y_mm = 0.0
            elif axis == "z":
                snapshot.pose.z_mm = self.calibration.z_home_mm
            elif axis == "c":
                snapshot.pose.c_mm = self.calibration.c_home_mm
            self._mark_axes_homed(axis)
            self.machine_initialized = False
            return {"ok": True, "message": f"Homed {axis.upper()} axis"}
        if action == "wait_idle":
            self.orchestrator.motion.wait_until_idle()
            return {"ok": True, "message": "Motion idle"}
        if action == "move_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_vac_xy_when_safe(self.calibration, x_mm, y_mm)
            z_message = self._apply_optional_z(payload, default_coordinate_space="vacuum")
            return {"ok": True, "message": f"Moved vacuum XY to ({x_mm:.2f}, {y_mm:.2f}){z_message}"}
        if action == "jog_xy":
            dx_mm = float(payload.get("dx_mm", 0.0))
            dy_mm = float(payload.get("dy_mm", 0.0))
            snapshot = self.orchestrator.world.snapshot
            x_mm = float(snapshot.pose.x_mm) + dx_mm
            y_mm = float(snapshot.pose.y_mm) + dy_mm
            self.orchestrator.move_vac_xy_when_safe(self.calibration, x_mm, y_mm)
            return {
                "ok": True,
                "message": f"Jogged vacuum XY by ({dx_mm:.2f}, {dy_mm:.2f}) to ({x_mm:.2f}, {y_mm:.2f})",
            }
        if action == "move_camera_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_camera_to_vacuum_xy_when_safe(self.calibration, x_mm, y_mm)
            target_x_mm, target_y_mm = self.calibration.camera_baseline_xy_for_vacuum_target(x_mm, y_mm)
            z_message = self._apply_optional_z(payload, default_coordinate_space="camera")
            return {
                "ok": True,
                "message": (
                    f"Moved camera over ({x_mm:.2f}, {y_mm:.2f}) "
                    f"using vacuum baseline ({target_x_mm:.2f}, {target_y_mm:.2f}){z_message}"
                ),
            }
        if action == "move_z":
            z_mm, z_label = self._vacuum_z_from_payload(payload)
            self.orchestrator.move_vac_z(z_mm)
            return {"ok": True, "message": f"Moved {z_label} Z to vacuum Z {z_mm:.2f}"}
        if action == "jog_z":
            dz_mm = float(payload.get("dz_mm", 0.0))
            snapshot = self.orchestrator.world.snapshot
            z_mm = float(snapshot.pose.z_mm) + dz_mm
            self.orchestrator.move_vac_z(z_mm)
            return {"ok": True, "message": f"Jogged vacuum Z by {dz_mm:.2f} to {z_mm:.2f}"}
        if action == "move_c":
            c_mm = float(payload["c_mm"])
            self._move_c(c_mm)
            return {"ok": True, "message": f"Moved suction C to {c_mm:.2f}"}
        if action == "jog_c":
            dc_mm = float(payload.get("dc_mm", 0.0))
            snapshot = self.orchestrator.world.snapshot
            c_mm = float(getattr(snapshot.pose, "c_mm", 0.0)) + dc_mm
            self._move_c(c_mm)
            return {"ok": True, "message": f"Jogged suction C by {dc_mm:.2f} to {c_mm:.2f}"}
        if action == "jog_zc_interface":
            dz_mm = float(payload.get("dz_mm", 0.0))
            snapshot = self.orchestrator.world.snapshot
            current_z_mm = float(snapshot.pose.z_mm)
            current_c_mm = float(getattr(snapshot.pose, "c_mm", 0.0))
            target_z_mm = current_z_mm + dz_mm
            target_c_mm = current_c_mm - dz_mm
            self._move_zc(target_z_mm, target_c_mm)
            return {
                "ok": True,
                "message": (
                    f"Moved interface Z by {dz_mm:.2f}; coordinated C to {target_c_mm:.2f} "
                    "in the same motion block"
                ),
            }
        if action == "vacuum_on":
            self.orchestrator.vacuum.on()
            return {"ok": True, "message": "Vacuum enabled"}
        if action == "vacuum_off":
            self.orchestrator.vacuum.off()
            return {"ok": True, "message": "Vacuum disabled"}
        if action == "lights":
            status = str(payload.get("status", "idle"))
            self.orchestrator.lights.set_status(status)
            return {"ok": True, "message": f"Lights set to {status}"}
        if action == "light_profile":
            profile_name = str(payload["name"])
            profile = self.light_profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"Unknown light profile: {profile_name}")
            self._apply_light_profile(profile_name, profile)
            return {"ok": True, "message": f"Applied light profile {profile_name}"}
        raise ValueError(f"Unsupported control action: {action}")

    def _mark_axes_homed(self, *axes: str) -> None:
        for axis in axes:
            normalized = str(axis).strip().lower()
            if normalized:
                self.homed_axes.add(normalized)

    def _jog_limit_for_axes(self, limit_mm: float, *axes: str) -> float | None:
        return None if all(axis in self.homed_axes for axis in axes) else limit_mm

    def record_control_audit(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        try:
            status = self.status()
            entry = {
                "at": _utc_now_iso(),
                "action": action,
                "payload": payload,
                "ok": error is None,
                "error": error,
                "result": result,
                "result_message": (result or {}).get("message"),
                "runtime_target": status.get("runtime_target"),
                "pose": status.get("pose"),
                "serial": {
                    "connected": status.get("serial_board", {}).get("connected"),
                    "connection_state": status.get("serial_board", {}).get("connection_state"),
                    "controller_fault": status.get("serial_board", {}).get("controller_fault"),
                    "live_pose": status.get("serial_board", {}).get("live_pose"),
                    "last_response": status.get("serial_board", {}).get("last_response"),
                },
            }
            self.control_audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.control_audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        except Exception:
            return

    def record_debug_event(self, event: str, details: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": _utc_now_iso(),
            "event": str(event),
            "details": _json_safe(details or {}),
        }
        try:
            self.debug_events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.debug_events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        except Exception:
            return

    def _hardware_control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        serial_status = self.serial_board.status()
        if self.hardware_runtime and serial_status["session_open"] and action in MOTION_CONTROL_ACTIONS:
            return self._hardware_serial_control(action, payload)
        if self.hardware_runtime:
            return self._direct_hardware_control(action, payload)
        if action in {"vacuum_on", "vacuum_off"}:
            raise ValueError("Vacuum hardware control is not wired yet; select Simulation runtime to use simulated vacuum")
        if not serial_status["connected"]:
            raise ValueError("Hardware runtime selected, but the serial board is not verified live")
        if action in MOTION_CONTROL_ACTIONS:
            return self._hardware_serial_control(action, payload)
        if action == "lights":
            status = str(payload.get("status", "idle"))
            self.serial_board.set_lights_status(status)
            self.orchestrator.lights.set_status(status)
            return {"ok": True, "message": f"Live board lights set to {status}"}
        if action == "light_profile":
            profile_name = str(payload["name"])
            profile = self.light_profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"Unknown light profile: {profile_name}")
            self.serial_board.set_lights_rgb(profile["red"], profile["green"], profile["blue"], profile_name=profile_name)
            setter = getattr(self.orchestrator.lights, "set_rgb", None)
            if callable(setter):
                setter(profile["red"], profile["green"], profile["blue"], profile_name=profile_name)
            else:
                self.orchestrator.lights.set_status(profile_name)
            return {"ok": True, "message": f"Applied live board light profile {profile_name}"}
        raise ValueError(f"Unsupported hardware control action: {action}")

    def _direct_hardware_control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action in MOTION_CONTROL_ACTIONS:
            return self._direct_motion_control(action, payload)
        if action == "vacuum_on":
            self.orchestrator.vacuum.on()
            self.orchestrator.world.snapshot.pose.vacuum_on = True
            return {"ok": True, "message": "Vacuum enabled"}
        if action == "vacuum_off":
            self.orchestrator.vacuum.off()
            self.orchestrator.world.snapshot.pose.vacuum_on = False
            return {"ok": True, "message": "Vacuum disabled"}
        if action == "lights":
            status = str(payload.get("status", "idle"))
            self.orchestrator.lights.set_status(status)
            return {"ok": True, "message": f"Lights set to {status}"}
        if action == "light_profile":
            profile_name = str(payload["name"])
            profile = self.light_profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"Unknown light profile: {profile_name}")
            setter = getattr(self.orchestrator.lights, "set_rgb", None)
            if not callable(setter):
                raise ValueError("Direct hardware lights do not support RGB profiles")
            setter(profile["red"], profile["green"], profile["blue"], profile_name=profile_name)
            return {"ok": True, "message": f"Applied light profile {profile_name}"}
        raise ValueError(f"Unsupported direct hardware action: {action}")

    def _direct_motion_control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.orchestrator.world.snapshot
        if action == "initialize":
            return self.initialize_machine()
        if action == "home":
            self.orchestrator.motion.home_axes()
            snapshot.pose.x_mm = 0.0
            snapshot.pose.y_mm = 0.0
            snapshot.pose.z_mm = self.calibration.z_home_mm
            snapshot.pose.c_mm = self.calibration.c_home_mm
            self._mark_axes_homed("x", "y", "z", "c")
            self.machine_initialized = False
            return {"ok": True, "message": "Axes homed"}
        if action in {"home_x", "home_y", "home_z", "home_c"}:
            axis = action.removeprefix("home_").upper()
            self.orchestrator.motion.transport.send_command(f"G28 {axis}")
            if axis == "X":
                snapshot.pose.x_mm = 0.0
            elif axis == "Y":
                snapshot.pose.y_mm = 0.0
            elif axis == "Z":
                snapshot.pose.z_mm = self.calibration.z_home_mm
            elif axis == "C":
                snapshot.pose.c_mm = self.calibration.c_home_mm
            self._mark_axes_homed(axis.lower())
            self.machine_initialized = False
            return {"ok": True, "message": f"Homed {axis} axis"}
        if action == "wait_idle":
            self.orchestrator.motion.wait_until_idle()
            return {"ok": True, "message": "Motion idle"}
        if action == "move_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_vac_xy_when_safe(self.calibration, x_mm, y_mm)
            z_message = self._apply_optional_z(payload, default_coordinate_space="vacuum")
            return {"ok": True, "message": f"Moved vacuum XY to ({x_mm:.2f}, {y_mm:.2f}){z_message}"}
        if action == "move_camera_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_camera_to_vacuum_xy_when_safe(self.calibration, x_mm, y_mm)
            z_message = self._apply_optional_z(payload, default_coordinate_space="camera")
            return {"ok": True, "message": f"Moved camera over ({x_mm:.2f}, {y_mm:.2f}){z_message}"}
        if action == "move_z":
            z_mm, z_label = self._vacuum_z_from_payload(payload)
            self.orchestrator.move_vac_z(z_mm)
            return {"ok": True, "message": f"Moved {z_label} Z to vacuum Z {z_mm:.2f}"}
        if action == "move_c":
            c_mm = float(payload["c_mm"])
            self._move_c(c_mm)
            return {"ok": True, "message": f"Moved suction C to {c_mm:.2f}"}
        if action == "jog_xy":
            dx_mm = _bounded_jog_delta(payload.get("dx_mm", 0.0), axis="X", limit_mm=MAX_SERIAL_XY_JOG_MM)
            dy_mm = _bounded_jog_delta(payload.get("dy_mm", 0.0), axis="Y", limit_mm=MAX_SERIAL_XY_JOG_MM)
            if float(snapshot.pose.z_mm) < self.calibration.min_xy_travel_z_mm:
                raise ValueError(
                    f"Refusing XY jog while Z is below {self.calibration.min_xy_travel_z_mm:.2f} mm travel clearance"
                )
            commands = ["G91", f"G1 X{_format_mm(dx_mm)} Y{_format_mm(dy_mm)} F600", "M400", "G90"]
            self._send_direct_motion_commands(commands)
            snapshot.pose.x_mm = float(snapshot.pose.x_mm) + dx_mm
            snapshot.pose.y_mm = float(snapshot.pose.y_mm) + dy_mm
            return {"ok": True, "message": f"Jogged vacuum XY by ({dx_mm:.2f}, {dy_mm:.2f})", "commands": commands}
        if action == "jog_z":
            dz_mm = _bounded_jog_delta(
                payload.get("dz_mm", 0.0),
                axis="Z",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_Z_JOG_MM, "z"),
            )
            commands = ["G91", f"G1 Z{_format_mm(dz_mm)} F300", "M400", "G90"]
            self._send_direct_motion_commands(commands)
            snapshot.pose.z_mm = float(snapshot.pose.z_mm) + dz_mm
            return {"ok": True, "message": f"Jogged vacuum Z by {dz_mm:.2f}", "commands": commands}
        if action == "jog_c":
            dc_mm = _bounded_jog_delta(
                payload.get("dc_mm", 0.0),
                axis="C",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_C_JOG_MM, "c"),
            )
            commands = ["G91", f"G1 C{_format_mm(dc_mm)} F300", "M400", "G90"]
            self._send_direct_motion_commands(commands)
            snapshot.pose.c_mm = float(snapshot.pose.c_mm) + dc_mm
            return {"ok": True, "message": f"Jogged suction C by {dc_mm:.2f}", "commands": commands}
        if action == "jog_zc_interface":
            dz_mm = _bounded_jog_delta(
                payload.get("dz_mm", 0.0),
                axis="Z/C",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_Z_JOG_MM, "z", "c"),
            )
            commands = ["G91", f"G1 Z{_format_mm(dz_mm)} C{_format_mm(-dz_mm)} F300", "M400", "G90"]
            self._send_direct_motion_commands(commands)
            snapshot.pose.z_mm = float(snapshot.pose.z_mm) + dz_mm
            snapshot.pose.c_mm = float(snapshot.pose.c_mm) - dz_mm
            return {"ok": True, "message": "Jogged Z/C interface", "commands": commands}
        raise ValueError(f"Unsupported direct motion action: {action}")

    def _send_direct_motion_commands(self, commands: list[str]) -> None:
        transport = getattr(self.orchestrator.motion, "transport", None)
        if transport is None:
            raise RuntimeError("Direct hardware motion transport is not configured")
        for command in commands:
            transport.send_command(command)

    def apply_neopixel_display(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.runtime_mode != "hardware":
            raise ValueError("Pixel-by-pixel NeoPixel display requires Hardware runtime")
        if not self.serial_board.status()["connected"]:
            raise ValueError("Hardware runtime selected, but the serial board is not verified live")
        raw_pixels = payload.get("pixels")
        if not isinstance(raw_pixels, list):
            raise ValueError("pixels must be a list of 16 RGB triples")
        pixels: list[tuple[int, int, int]] = []
        for index, raw_pixel in enumerate(raw_pixels):
            if not isinstance(raw_pixel, list) or len(raw_pixel) != 3:
                raise ValueError(f"pixels[{index}] must be an RGB triple")
            pixels.append((int(raw_pixel[0]), int(raw_pixel[1]), int(raw_pixel[2])))
        return self.serial_board.set_neopixel_pixels(pixels)

    def optimize_lighting(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_samples = max(3, min(24, int(payload.get("max_samples", 12))))
        settle_ms = max(0, min(2000, int(payload.get("settle_ms", 150))))
        target_brightness = max(20.0, min(235.0, float(payload.get("target_brightness", 122))))
        mode = str(payload.get("mode") or "solid_ring").strip().lower()
        crop = _normalize_crop_payload(payload.get("crop"))
        if mode in {"single_led", "single-led", "pixel", "one_led", "one-led"}:
            return self._optimize_single_led_lighting(
                max_samples=max_samples,
                settle_ms=settle_ms,
                target_brightness=target_brightness,
                crop=crop,
            )
        candidates = self._lighting_candidates(max_samples)
        results: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        previous_rgb = tuple(getattr(self.orchestrator.lights, "last_rgb", (0, 0, 16)) or (0, 0, 16))
        for red, green, blue in candidates:
            self._set_light_rgb(red, green, blue, profile_name="optimizing")
            if settle_ms:
                time.sleep(settle_ms / 1000)
            image = self._capture_optimizer_image()
            image = _crop_image(image, crop)
            score = self._score_lighting_frame(image, target_brightness=target_brightness)
            sample = {
                "red": red,
                "green": green,
                "blue": blue,
                **score,
            }
            results.append(sample)
            if best is None or sample["score"] > best["score"]:
                best = sample
        if best is None:
            self._set_light_rgb(*previous_rgb, profile_name="custom")
            raise RuntimeError("No lighting candidates were sampled")
        self._set_light_rgb(best["red"], best["green"], best["blue"], profile_name="optimized")
        return {
            "ok": True,
            "message": f"Optimized lighting to RGB {best['red']}, {best['green']}, {best['blue']}",
            "mode": "solid_ring",
            "best": best,
            "samples": results,
            "target_brightness": target_brightness,
            "settle_ms": settle_ms,
            "crop": crop,
            "status": self.status(),
        }

    def _optimize_single_led_lighting(
        self,
        *,
        max_samples: int,
        settle_ms: int,
        target_brightness: float,
        crop: dict[str, float] | None,
    ) -> dict[str, Any]:
        candidates = self._single_led_lighting_candidates(max_samples)
        results: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        previous_rgb = tuple(getattr(self.orchestrator.lights, "last_rgb", (0, 0, 16)) or (0, 0, 16))
        for candidate in candidates:
            self._set_light_pixels(candidate["pixels"], profile_name="optimizing-single-led")
            if settle_ms:
                time.sleep(settle_ms / 1000)
            image = self._capture_optimizer_image()
            image = _crop_image(image, crop)
            score = self._score_lighting_frame(image, target_brightness=target_brightness)
            sample = {
                "led_index": candidate["led_index"],
                "red": candidate["red"],
                "green": candidate["green"],
                "blue": candidate["blue"],
                "pixels": candidate["pixels"],
                **score,
            }
            results.append(sample)
            if best is None or sample["score"] > best["score"]:
                best = sample
        if best is None:
            self._set_light_rgb(*previous_rgb, profile_name="custom")
            raise RuntimeError("No single-LED lighting candidates were sampled")
        self._set_light_pixels(best["pixels"], profile_name="optimized-single-led")
        return {
            "ok": True,
            "message": (
                f"Optimized lighting to LED {best['led_index']} RGB "
                f"{best['red']}, {best['green']}, {best['blue']}"
            ),
            "mode": "single_led",
            "best": best,
            "samples": results,
            "target_brightness": target_brightness,
            "settle_ms": settle_ms,
            "crop": crop,
            "status": self.status(),
        }

    def _capture_optimizer_image(self) -> Image.Image:
        frame = self.orchestrator.camera.capture_frame()
        if frame.path is None:
            raise RuntimeError("Camera adapter did not return a frame path")
        image_path = Path(frame.path)
        if not image_path.exists():
            raise RuntimeError(f"Captured frame path does not exist: {image_path}")
        return Image.open(image_path).convert("RGB")

    def _set_light_rgb(self, red: int, green: int, blue: int, *, profile_name: str) -> None:
        r, g, b = (_clamp_channel(red), _clamp_channel(green), _clamp_channel(blue))
        if self.runtime_mode == "hardware" and not self.hardware_runtime:
            if not self.serial_board.status()["connected"]:
                raise ValueError("Hardware runtime selected, but the serial board is not verified live")
            self.serial_board.set_lights_rgb(r, g, b, profile_name=profile_name)
        setter = getattr(self.orchestrator.lights, "set_rgb", None)
        if callable(setter):
            setter(r, g, b, profile_name=profile_name)
            return
        self.orchestrator.lights.set_status(profile_name)

    def _set_light_pixels(self, pixels: list[list[int]], *, profile_name: str) -> None:
        if len(pixels) != 16:
            raise ValueError("NeoPixel display requires exactly 16 pixels")
        normalized = [
            [_clamp_channel(pixel[0]), _clamp_channel(pixel[1]), _clamp_channel(pixel[2])]
            for pixel in pixels
        ]
        if self.runtime_mode == "hardware" and not self.hardware_runtime:
            if not self.serial_board.status()["connected"]:
                raise ValueError("Hardware runtime selected, but the serial board is not verified live")
            self.serial_board.set_neopixel_pixels([tuple(pixel) for pixel in normalized])
        else:
            setter = getattr(self.orchestrator.lights, "set_pixels", None)
            if callable(setter):
                setter(normalized, profile_name=profile_name)
                return
        setattr(self.orchestrator.lights, "last_profile", profile_name)
        setattr(self.orchestrator.lights, "status", profile_name)
        setattr(self.orchestrator.lights, "last_pixels", normalized)
        lit_pixels = [pixel for pixel in normalized if any(pixel)]
        if len(lit_pixels) == 1:
            setattr(self.orchestrator.lights, "last_rgb", tuple(lit_pixels[0]))

    def _lighting_candidates(self, max_samples: int) -> list[tuple[int, int, int]]:
        levels = [24, 48, 72, 96, 128, 160, 192, 224]
        candidates: list[tuple[int, int, int]] = []
        for level in levels:
            candidates.append((level, level, level))
        for level in (72, 112, 160, 208):
            candidates.append((level, int(level * 0.88), int(level * 0.62)))
            candidates.append((int(level * 0.70), int(level * 0.86), level))
        unique: list[tuple[int, int, int]] = []
        seen: set[tuple[int, int, int]] = set()
        for candidate in candidates:
            normalized = tuple(_clamp_channel(channel) for channel in candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique[:max_samples]

    def _single_led_lighting_candidates(self, max_samples: int) -> list[dict[str, Any]]:
        color_passes = [
            (96, 96, 96),
            (64, 64, 64),
            (128, 128, 128),
            (96, 84, 60),
            (67, 83, 96),
            (160, 160, 160),
        ]
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[int, int, int, int]] = set()
        for red, green, blue in color_passes:
            for led_index in range(16):
                normalized = (_clamp_channel(red), _clamp_channel(green), _clamp_channel(blue))
                key = (led_index, *normalized)
                if key in seen:
                    continue
                seen.add(key)
                pixels = [[0, 0, 0] for _ in range(16)]
                pixels[led_index] = [normalized[0], normalized[1], normalized[2]]
                candidates.append({
                    "led_index": led_index,
                    "red": normalized[0],
                    "green": normalized[1],
                    "blue": normalized[2],
                    "pixels": pixels,
                })
        return candidates[:max_samples]

    def _score_lighting_frame(self, image: Image.Image, *, target_brightness: float) -> dict[str, float]:
        sample = image.convert("RGB")
        sample.thumbnail((320, 320))
        grayscale = sample.convert("L")
        gray_stat = ImageStat.Stat(grayscale)
        rgb_stat = ImageStat.Stat(sample)
        mean = float(gray_stat.mean[0])
        contrast = float(gray_stat.stddev[0])
        channel_spread = float(max(rgb_stat.mean) - min(rgb_stat.mean))
        pixels = list(sample.getdata())
        pixel_count = max(1, len(pixels))
        clipped_pixels = sum(
            1
            for red, green, blue in pixels
            if red >= 245 or green >= 245 or blue >= 245 or max(red, green, blue) - min(red, green, blue) >= 185
        )
        glare_fraction = clipped_pixels / pixel_count
        exposure_error = abs(mean - target_brightness)
        exposure_score = max(0.0, 1.0 - (exposure_error / 128.0))
        contrast_score = min(1.0, contrast / 64.0)
        color_balance_score = max(0.0, 1.0 - (channel_spread / 128.0))
        clipping_penalty = 0.25 if mean < 28.0 or mean > 227.0 else 0.0
        glare_penalty = min(0.45, glare_fraction * 3.5)
        score = (
            (exposure_score * 0.52)
            + (contrast_score * 0.28)
            + (color_balance_score * 0.12)
            + ((1.0 - min(1.0, glare_fraction * 8.0)) * 0.08)
            - clipping_penalty
            - glare_penalty
        )
        return {
            "score": round(max(0.0, score), 4),
            "mean_brightness": round(mean, 2),
            "contrast": round(contrast, 2),
            "channel_spread": round(channel_spread, 2),
            "exposure_error": round(exposure_error, 2),
            "glare_fraction": round(glare_fraction, 4),
        }

    def _hardware_serial_control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "initialize":
            result = self.serial_board.send_commands(
                ["G28 Z C", "G28 X Y", "M114"],
                message="Live board initialized and homed",
            )
            self._mark_axes_homed("x", "y", "z", "c")
            return result
        if action == "home":
            result = self.serial_board.send_commands(["G28 Z C", "G28 X Y", "M114"], message="Live board axes homed")
            self._mark_axes_homed("x", "y", "z", "c")
            return result
        if action in {"home_x", "home_y", "home_z", "home_c"}:
            axis = action.removeprefix("home_").upper()
            result = self.serial_board.send_commands([f"G28 {axis}", "M114"], message=f"Live board homed {axis}")
            self._mark_axes_homed(axis.lower())
            return result
        if action == "wait_idle":
            return self.serial_board.send_commands(["M400", "M114"], message="Live board idle")
        if action in {"move_xy", "move_camera_xy"}:
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            z_mm = self._optional_vacuum_z_from_payload(
                payload,
                default_coordinate_space="camera" if action == "move_camera_xy" else "vacuum",
            )
            if action == "move_camera_xy":
                x_mm, y_mm = self.calibration.camera_baseline_xy_for_vacuum_target(x_mm, y_mm)
            command = f"G1 X{_format_mm(x_mm)} Y{_format_mm(y_mm)}"
            if z_mm is not None:
                current_z = self._optional_serial_live_axis_position("z")
                self._reject_large_absolute_move(
                    axis="Z",
                    target_mm=z_mm,
                    current_mm=current_z,
                    limit_mm=MAX_SERIAL_ABSOLUTE_Z_MOVE_MM,
                    confirmed=bool(payload.get("confirm_large_move")),
                )
                feedrate_mm_per_min = _live_xyz_feedrate_mm_per_min(
                    current_x_mm=self._optional_serial_live_axis_position("x"),
                    current_y_mm=self._optional_serial_live_axis_position("y"),
                    current_z_mm=current_z,
                    target_x_mm=x_mm,
                    target_y_mm=y_mm,
                    target_z_mm=z_mm,
                )
                command += f" Z{_format_mm(z_mm)}"
            else:
                feedrate_mm_per_min = MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN
            command += f" F{_format_feedrate(feedrate_mm_per_min)}"
            return self.serial_board.send_commands(
                ["G90", command, "M400", "M114"],
                message=(
                    f"Live board moved XY to ({x_mm:.2f}, {y_mm:.2f})"
                    + (f" and vacuum Z to {z_mm:.2f}" if z_mm is not None else "")
                ),
            )
        if action == "jog_xy":
            dx_mm = _bounded_jog_delta(payload.get("dx_mm", 0.0), axis="X", limit_mm=MAX_SERIAL_XY_JOG_MM)
            dy_mm = _bounded_jog_delta(payload.get("dy_mm", 0.0), axis="Y", limit_mm=MAX_SERIAL_XY_JOG_MM)
            current_x = self._optional_serial_live_axis_position("x")
            current_y = self._optional_serial_live_axis_position("y")
            if current_x is None or current_y is None:
                return self.serial_board.send_commands(
                    ["G91", f"G1 X{_format_mm(dx_mm)} Y{_format_mm(dy_mm)} F600", "M400", "G90", "M114"],
                    message=f"Live board jogged XY by ({dx_mm:.2f}, {dy_mm:.2f})",
                )
            target_x = current_x + dx_mm
            target_y = current_y + dy_mm
            return self.serial_board.send_commands(
                ["G90", f"G1 X{_format_mm(target_x)} Y{_format_mm(target_y)} F600", "M400", "M114"],
                message=f"Live board jogged XY by ({dx_mm:.2f}, {dy_mm:.2f}) to ({target_x:.2f}, {target_y:.2f})",
            )
        if action == "move_z":
            z_mm, z_label = self._vacuum_z_from_payload(payload)
            self._reject_large_absolute_move(
                axis="Z",
                target_mm=z_mm,
                current_mm=self._optional_serial_live_axis_position("z"),
                limit_mm=MAX_SERIAL_ABSOLUTE_Z_MOVE_MM,
                confirmed=bool(payload.get("confirm_large_move")),
            )
            return self.serial_board.send_commands(
                ["G90", f"G1 Z{_format_mm(z_mm)} F1200", "M400", "M114"],
                message=f"Live board moved {z_label} Z to vacuum Z {z_mm:.2f}",
            )
        if action == "jog_z":
            dz_mm = _bounded_jog_delta(
                payload.get("dz_mm", 0.0),
                axis="Z",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_Z_JOG_MM, "z"),
            )
            current_z = self._optional_serial_live_axis_position("z")
            if current_z is None:
                return self.serial_board.send_commands(
                    ["G91", f"G1 Z{_format_mm(dz_mm)} F300", "M400", "G90", "M114"],
                    message=f"Live board jogged Z by {dz_mm:.2f}",
                )
            target_z = current_z + dz_mm
            return self.serial_board.send_commands(
                ["G90", f"G1 Z{_format_mm(target_z)} F300", "M400", "M114"],
                message=f"Live board jogged Z by {dz_mm:.2f} to {target_z:.2f}",
            )
        if action == "move_c":
            c_mm = float(payload["c_mm"])
            self._reject_large_absolute_move(
                axis="C",
                target_mm=c_mm,
                current_mm=self._optional_serial_live_axis_position("c"),
                limit_mm=MAX_SERIAL_ABSOLUTE_C_MOVE_MM,
                confirmed=bool(payload.get("confirm_large_move")),
            )
            return self.serial_board.send_commands(
                ["G90", f"G1 C{_format_mm(c_mm)} F1200", "M400", "M114"],
                message=f"Live board moved C to {c_mm:.2f}",
            )
        if action == "jog_c":
            dc_mm = _bounded_jog_delta(
                payload.get("dc_mm", 0.0),
                axis="C",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_C_JOG_MM, "c"),
            )
            current_c = self._optional_serial_live_axis_position("c")
            if current_c is None:
                return self.serial_board.send_commands(
                    ["G91", f"G1 C{_format_mm(dc_mm)} F300", "M400", "G90", "M114"],
                    message=f"Live board jogged C by {dc_mm:.2f}",
                )
            target_c = current_c + dc_mm
            return self.serial_board.send_commands(
                ["G90", f"G1 C{_format_mm(target_c)} F300", "M400", "M114"],
                message=f"Live board jogged C by {dc_mm:.2f} to {target_c:.2f}",
            )
        if action == "jog_zc_interface":
            dz_mm = _bounded_jog_delta(
                payload.get("dz_mm", 0.0),
                axis="Z/C",
                limit_mm=self._jog_limit_for_axes(MAX_SERIAL_Z_JOG_MM, "z", "c"),
            )
            current_z = self._optional_serial_live_axis_position("z")
            current_c = self._optional_serial_live_axis_position("c")
            if current_z is None or current_c is None:
                return self.serial_board.send_commands(
                    ["G91", f"G1 Z{_format_mm(dz_mm)} C{_format_mm(-dz_mm)} F300", "M400", "G90", "M114"],
                    message=f"Live board moved interface Z by {dz_mm:.2f}",
                )
            target_z = current_z + dz_mm
            target_c = current_c - dz_mm
            return self.serial_board.send_commands(
                ["G90", f"G1 Z{_format_mm(target_z)} C{_format_mm(target_c)} F300", "M400", "M114"],
                message=f"Live board moved interface Z by {dz_mm:.2f} to Z {target_z:.2f} / C {target_c:.2f}",
            )
        raise ValueError(f"Unsupported live serial control action: {action}")

    def _shared_marlin_transport(self) -> MarlinSerialTransport | None:
        motion = getattr(self.orchestrator, "motion", None)
        transport = getattr(motion, "transport", None)
        if isinstance(transport, MarlinSerialTransport):
            return transport
        return None

    def _optional_serial_live_axis_position(self, axis: str) -> float | None:
        live_pose = self.serial_board.status().get("live_pose", {})
        value = live_pose.get(axis)
        if value is None:
            return None
        return float(value)

    def _vacuum_z_from_payload(self, payload: dict[str, Any]) -> tuple[float, str]:
        requested_z = float(payload["z_mm"])
        coordinate_space = str(payload.get("coordinate_space", "vacuum")).strip().lower()
        if coordinate_space == "camera":
            return requested_z - float(self.calibration.camera_offset_z_mm), "camera"
        if coordinate_space not in {"", "vacuum", "nozzle"}:
            raise ValueError(f"Unsupported Z coordinate space: {coordinate_space}")
        return requested_z, "vacuum"

    def _optional_vacuum_z_from_payload(
        self,
        payload: dict[str, Any],
        *,
        default_coordinate_space: str,
    ) -> float | None:
        if "z_mm" not in payload or payload.get("z_mm") in {None, ""}:
            return None
        next_payload = dict(payload)
        next_payload.setdefault("coordinate_space", default_coordinate_space)
        z_mm, _ = self._vacuum_z_from_payload(next_payload)
        return z_mm

    def _apply_optional_z(self, payload: dict[str, Any], *, default_coordinate_space: str) -> str:
        z_mm = self._optional_vacuum_z_from_payload(payload, default_coordinate_space=default_coordinate_space)
        if z_mm is None:
            return ""
        self.orchestrator.move_vac_z(z_mm)
        return f" and vacuum Z to {z_mm:.2f}"

    def _reject_large_absolute_move(
        self,
        *,
        axis: str,
        target_mm: float,
        current_mm: float | None,
        limit_mm: float,
        confirmed: bool,
    ) -> None:
        if current_mm is None or confirmed:
            return
        delta_mm = target_mm - current_mm
        if abs(delta_mm) > limit_mm:
            raise ValueError(
                f"Refusing {axis} absolute move from {current_mm:.2f} to {target_mm:.2f} mm "
                f"({delta_mm:.2f} mm); use jog or confirm_large_move"
            )

    def _load_light_profiles(self) -> dict[str, dict[str, int]]:
        default_profiles = {
            name: {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}
            for name, rgb in getattr(self.orchestrator.lights, "STATUS_RGB", {}).items()
        }
        if not default_profiles:
            default_profiles = {
                "idle": {"red": 0, "green": 0, "blue": 16},
                "running": {"red": 0, "green": 16, "blue": 0},
                "warning": {"red": 16, "green": 8, "blue": 0},
                "fault": {"red": 16, "green": 0, "blue": 0},
            }
        source_path = self.light_profiles_path if self.light_profiles_path and self.light_profiles_path.exists() else self.light_profiles_seed_path
        if source_path is None or not source_path.exists():
            return default_profiles
        with source_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        loaded = {
            str(item["name"]): {
                "red": int(item["red"]),
                "green": int(item["green"]),
                "blue": int(item["blue"]),
            }
            for item in raw.get("profiles", [])
            if "pixels" not in item
        }
        return loaded or default_profiles

    def _load_pixel_profiles(self) -> dict[str, list[list[int]]]:
        if self.light_profiles_path is None or not self.light_profiles_path.exists():
            return {}
        with self.light_profiles_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        profiles: dict[str, list[list[int]]] = {}
        for item in raw.get("profiles", []):
            if "name" not in item:
                continue
            pixels = item.get("pixels")
            if not isinstance(pixels, list) or len(pixels) != 16:
                continue
            profile_name = str(item["name"])
            profiles[profile_name] = [
                [_clamp_channel(pixel[0]), _clamp_channel(pixel[1]), _clamp_channel(pixel[2])]
                for pixel in pixels
                if isinstance(pixel, list) and len(pixel) == 3
            ]
            if len(profiles[profile_name]) != 16:
                profiles.pop(profile_name, None)
        return profiles

    def _save_light_profiles(self) -> None:
        if self.light_profiles_path is None:
            return
        self.light_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        pixel_profiles = self._load_pixel_profiles()
        payload = {
            "profiles": [
                {"name": name, **channels}
                for name, channels in sorted(self.light_profiles.items())
            ] + [
                {"name": name, "pixels": pixels}
                for name, pixels in sorted(pixel_profiles.items())
            ]
        }
        with self.light_profiles_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    def list_light_profiles(self) -> list[dict[str, int | str]]:
        return [{"name": name, **channels} for name, channels in sorted(self.light_profiles.items())]

    def create_light_profile(self, name: str, red: int, green: int, blue: int) -> dict[str, Any]:
        normalized_name = name.strip().lower()
        if not normalized_name:
            raise ValueError("Profile name is required")
        channels = {
            "red": _clamp_channel(red),
            "green": _clamp_channel(green),
            "blue": _clamp_channel(blue),
        }
        self.light_profiles[normalized_name] = channels
        self._save_light_profiles()
        return {"name": normalized_name, **channels}

    def delete_light_profile(self, name: str) -> None:
        normalized_name = name.strip().lower()
        if normalized_name not in self.light_profiles:
            raise ValueError(f"Unknown light profile: {normalized_name}")
        self.light_profiles.pop(normalized_name)
        self._save_light_profiles()

    def list_pixel_profiles(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "pixels": pixels}
            for name, pixels in sorted(self._load_pixel_profiles().items())
        ]

    def list_neopixel_profile_options(self) -> list[dict[str, Any]]:
        solid_profiles = [
            {
                "name": name,
                "kind": "solid",
                "red": channels["red"],
                "green": channels["green"],
                "blue": channels["blue"],
                "pixels": [[channels["red"], channels["green"], channels["blue"]] for _ in range(16)],
            }
            for name, channels in sorted(self.light_profiles.items())
        ]
        pixel_profiles = [
            {"name": name, "kind": "pixel", "pixels": pixels}
            for name, pixels in sorted(self._load_pixel_profiles().items())
        ]
        return solid_profiles + pixel_profiles

    def create_pixel_profile(self, name: str, raw_pixels: list[Any]) -> dict[str, Any]:
        normalized_name = name.strip().lower()
        if not normalized_name:
            raise ValueError("Profile name is required")
        if not isinstance(raw_pixels, list) or len(raw_pixels) != 16:
            raise ValueError("Pixel profile requires exactly 16 RGB triples")
        pixels: list[list[int]] = []
        for index, raw_pixel in enumerate(raw_pixels):
            if not isinstance(raw_pixel, list) or len(raw_pixel) != 3:
                raise ValueError(f"pixels[{index}] must be an RGB triple")
            pixels.append([_clamp_channel(raw_pixel[0]), _clamp_channel(raw_pixel[1]), _clamp_channel(raw_pixel[2])])
        pixel_profiles = self._load_pixel_profiles()
        pixel_profiles[normalized_name] = pixels
        if self.light_profiles_path is None:
            return {"name": normalized_name, "pixels": pixels}
        self.light_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                {"name": name, **channels}
                for name, channels in sorted(self.light_profiles.items())
            ] + [
                {"name": profile_name, "pixels": profile_pixels}
                for profile_name, profile_pixels in sorted(pixel_profiles.items())
            ]
        }
        with self.light_profiles_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        return {"name": normalized_name, "pixels": pixels}

    def delete_pixel_profile(self, name: str) -> None:
        normalized_name = name.strip().lower()
        pixel_profiles = self._load_pixel_profiles()
        if normalized_name not in pixel_profiles:
            raise ValueError(f"Unknown pixel profile: {normalized_name}")
        pixel_profiles.pop(normalized_name)
        if self.light_profiles_path is None:
            return
        self.light_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                {"name": profile_name, **channels}
                for profile_name, channels in sorted(self.light_profiles.items())
            ] + [
                {"name": profile_name, "pixels": profile_pixels}
                for profile_name, profile_pixels in sorted(pixel_profiles.items())
            ]
        }
        with self.light_profiles_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    def delete_neopixel_profile(self, kind: str, name: str) -> None:
        if kind == "solid":
            self.delete_light_profile(name)
            return
        if kind == "pixel":
            self.delete_pixel_profile(name)
            return
        raise ValueError(f"Unknown profile kind: {kind}")

    def _apply_light_profile(self, name: str, channels: dict[str, int]) -> None:
        setter = getattr(self.orchestrator.lights, "set_rgb", None)
        if callable(setter):
            setter(channels["red"], channels["green"], channels["blue"], profile_name=name)
            return
        self.orchestrator.lights.set_status(name)

    def validate_card(self, query: str) -> dict[str, Any]:
        normalized = query.strip().lower()
        cards = self.orchestrator.catalog.all_cards()
        exact = next((card for card in cards if card.name.lower() == normalized), None)
        suggestions = [
            card.name
            for card in cards
            if normalized and normalized in card.name.lower()
        ][:8]
        return {
            "valid": exact is not None,
            "match": asdict(exact) if exact else None,
            "suggestions": suggestions,
        }

    def recognize_uploaded_image(self, image_path: Path, request_payload: dict[str, Any]) -> dict[str, Any]:
        return self._recognize_image(image_path, request_payload, camera_id="web_upload", source_mode="manual_web")

    def recognize_camera_image(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        image = self.latest_camera_image()
        image = _crop_image(image, _normalize_crop_payload(request_payload.get("crop")))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as handle:
            temp_path = Path(handle.name)
        image.save(temp_path, format="JPEG", quality=92)
        return self._recognize_image(temp_path, request_payload, camera_id="web_camera", source_mode="camera_web")

    def detect_card_back_from_camera(self, request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        image = self.latest_camera_image()
        payload = self._detect_card_back_with_method(image, str((request_payload or {}).get("detection_method") or "original"))
        payload["captured_at_utc"] = datetime.now(UTC).isoformat()
        self.last_card_back_detection = {key: value for key, value in payload.items() if key != "warped_image_data_url"}
        self.record_debug_event(
            "camera.card_back.detect",
            {
                "found": payload.get("found"),
                "confidence": payload.get("confidence"),
                "center_px": payload.get("center_px"),
                "rotation_degrees": payload.get("rotation_degrees"),
                "detection_method": payload.get("detection_method"),
            },
        )
        return payload

    def _detect_card_back_with_method(self, image: Image.Image, method: str) -> dict[str, Any]:
        normalized_method = method or "original"
        if normalized_method.startswith("model:"):
            payload = self._detect_card_back_with_training_model(image, normalized_method.split(":", 1)[1])
        else:
            payload = detect_card_back(image).to_json()
            payload["detection_method"] = "opencv" if normalized_method == "opencv" else "original"
            if normalized_method != "opencv" and payload.get("found") and payload.get("corners_px"):
                initial_corners = payload["corners_px"]
                refined_corners, refinement = self._refine_card_back_corners(image, initial_corners)
                payload["initial_corners_px"] = initial_corners
                payload["corners_px"] = [list(point) for point in refined_corners]
                payload["corner_refinement"] = refinement
        if payload.get("found") and payload.get("corners_px"):
            warped = warp_card_back_image(image, payload["corners_px"])
            buffer = BytesIO()
            warped.save(buffer, format="JPEG", quality=88)
            payload["warped_image_data_url"] = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
            payload["warped_image_size"] = [warped.width, warped.height]
        return payload

    def _detect_card_back_with_training_model(self, image: Image.Image, model_id: str) -> dict[str, Any]:
        template = self.card_back_training.latest_corner_template(model_id)
        source_width, source_height = template["image_size"]
        scale_x = image.width / max(1.0, float(source_width))
        scale_y = image.height / max(1.0, float(source_height))
        corners = [
            [round(float(point[0]) * scale_x, 2), round(float(point[1]) * scale_y, 2)]
            for point in template["corners_px"]
        ]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        area = max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))
        return {
            "found": True,
            "confidence": 0.55,
            "image_width": image.width,
            "image_height": image.height,
            "center_px": [round((min(xs) + max(xs)) / 2, 2), round((min(ys) + max(ys)) / 2, 2)],
            "component_bbox_px": [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)],
            "estimated_card_bbox_px": [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)],
            "corners_px": corners,
            "rotation_degrees": None,
            "skew_degrees": None,
            "area_fraction": round(area / max(1, image.width * image.height), 5),
            "message": f"Seeded corners from training model {model_id}",
            "detection_method": f"model:{model_id}",
            "model_template_sample_id": template["sample_id"],
        }

    def _refine_card_back_corners(
        self,
        image: Image.Image,
        corners: list[list[float]] | tuple[tuple[float, float], ...],
    ) -> tuple[tuple[tuple[float, float], ...], dict[str, Any]]:
        truth_path = self.repo_root / "src" / "sorter" / "interfaces" / "web" / "static" / "card-back-truth.jpg"
        if not truth_path.exists():
            return tuple((float(point[0]), float(point[1])) for point in corners), {
                "applied": False,
                "method": "bounded_corner_search",
                "message": f"Truth image not found: {truth_path}",
            }
        try:
            with Image.open(truth_path) as truth_image:
                return refine_card_back_corners_to_truth(image, corners, truth_image)
        except Exception as exc:
            return tuple((float(point[0]), float(point[1])) for point in corners), {
                "applied": False,
                "method": "bounded_corner_search",
                "message": f"Corner refinement failed: {exc}",
            }

    def _recognize_image(
        self,
        image_path: Path,
        request_payload: dict[str, Any],
        *,
        camera_id: str,
        source_mode: str,
    ) -> dict[str, Any]:
        frame = Frame(
            frame_id=f"web-{int(time.time() * 1000)}",
            path=str(image_path),
            pile_id=None,
            metadata={"recognition_request": request_payload},
            captured_at_utc=datetime.now(UTC).isoformat(),
            camera_id=camera_id,
            source_mode=source_mode,
        )
        result = self.orchestrator.recognizer.recognize_top_card(frame)
        payload = asdict(result)
        self.last_manual_recognition = payload
        self.orchestrator.last_recognition = {
            "backend": result.backend,
            "requested_mode": result.requested_mode,
            "effective_mode": result.effective_mode,
            "fallback_used": result.fallback_used,
            "card_name": result.card_name,
            "confidence": result.confidence,
            "failure_code": result.failure_code,
            "review_reason": result.review_reason,
        }
        return payload

    def latest_camera_image(self) -> Image.Image:
        frame = None
        try:
            frame = self.orchestrator.camera.capture_frame()
        except Exception:
            frame = None

        if frame and frame.path:
            image_path = Path(frame.path)
            if image_path.exists():
                return Image.open(image_path).convert("RGB")

        snapshot = self.orchestrator.world.snapshot
        current_pile = next(
            (
                pile
                for pile in sorted(snapshot.piles.values(), key=lambda p: (p.y_mm, p.x_mm, p.pile_id.as_key()))
                if self.orchestrator.world.top_card_image_path(pile.pile_id)
            ),
            None,
        )
        if current_pile is not None:
            path = self.orchestrator.world.top_card_image_path(current_pile.pile_id)
            if path and Path(path).exists():
                return Image.open(path).convert("RGB")
        return self._placeholder_camera_image()

    def _placeholder_camera_image(self) -> Image.Image:
        image = Image.new("RGB", (960, 540), "#111827")
        draw = ImageDraw.Draw(image)
        draw.rectangle((28, 28, 932, 512), outline="#334155", width=3)
        draw.text((54, 72), "Camera preview unavailable", fill="#f8fafc")
        draw.text((54, 112), "The current adapter did not return a frame path.", fill="#cbd5e1")
        draw.text((54, 152), "In sim mode this falls back to card imagery; hardware streaming needs camera capture wiring.", fill="#94a3b8")
        return image

    def recent_runs(self, limit: int = 12) -> list[dict[str, Any]]:
        db_path = getattr(self.orchestrator.run_store, "db_path", None)
        if not db_path:
            return []
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, mode, scenario_name, status, started_at, finished_at, result_metrics_json
                FROM runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "mode": row["mode"],
                "scenario_name": row["scenario_name"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "metrics": json.loads(row["result_metrics_json"]) if row["result_metrics_json"] else None,
            }
            for row in rows
        ]

    def capabilities(self) -> list[dict[str, str]]:
        status = self.status()
        serial_status = status.get("serial_board", {})
        serial_connected = bool(serial_status.get("connected"))
        hardware_direct = status.get("runtime_target") == "hardware_direct"
        simulation = status.get("runtime_target") == "simulation"
        camera_capability = self._camera_capability()
        recognition_capability = self._recognition_capability()
        collection_capability = self._collection_capability()
        motion_ready = simulation or serial_connected
        hardware_ready = hardware_direct and serial_connected
        return [
            {
                "name": "Automated sorting run",
                "status": "ready" if simulation else "partial",
                "detail": (
                    "End-to-end automated run is active in simulation."
                    if simulation
                    else "Hardware runtime is live, but automated hardware runs remain supervised."
                ),
            },
            {
                "name": "Live machine status",
                "status": "ready",
                "detail": f"Runtime is {status.get('runtime_mode')}; phase {status.get('phase')}; command {status.get('active_command') or 'idle'}.",
            },
            {
                "name": "Motion control",
                "status": "ready" if motion_ready else "blocked",
                "detail": (
                    "XY/Z/C controls are available."
                    if motion_ready
                    else f"Serial controller is {serial_status.get('connection_state', 'disconnected')}; verify it on System before moving."
                ),
            },
            {
                "name": "Vacuum and lights",
                "status": "ready" if simulation or hardware_direct else "partial",
                "detail": (
                    f"Vacuum is {'on' if status.get('vacuum_on') else 'off'}; lights profile is {status.get('lights_profile') or status.get('lights_status')}."
                    if simulation or hardware_direct
                    else "Manual I/O controls are present, but hardware runtime is not active."
                ),
            },
            recognition_capability,
            {"name": "Card validation", "status": "ready", "detail": "Catalog-backed exact validation with suggestions is available."},
            {"name": "Run history", "status": "ready", "detail": "SQLite-backed recent run summaries and metrics are available."},
            camera_capability,
            {
                "name": "Operator review workflow",
                "status": "partial",
                "detail": "Recognition evidence is shown here; use the collection service UI for correction and confirmation.",
            },
            {
                "name": "Hardware runtime",
                "status": "ready" if hardware_ready else ("partial" if hardware_direct else "blocked"),
                "detail": (
                    f"Direct Pi adapters are active and Marlin is verified on {serial_status.get('port')}."
                    if hardware_ready
                    else "Direct Pi adapters are active, but the Marlin controller is not verified."
                    if hardware_direct
                    else "Hardware runtime is not active."
                ),
            },
            collection_capability,
        ]

    def _camera_capability(self) -> dict[str, str]:
        try:
            frame = self.orchestrator.camera.capture_frame()
        except Exception as exc:
            return {
                "name": "Camera preview",
                "status": "blocked",
                "detail": f"Camera capture failed: {exc}",
            }
        if frame.path and Path(frame.path).exists():
            return {
                "name": "Camera preview",
                "status": "ready",
                "detail": f"Live camera capture is returning frames from {frame.camera_id}.",
            }
        return {
            "name": "Camera preview",
            "status": "partial",
            "detail": "Camera endpoint is available, but the active adapter did not return a frame path.",
        }

    def _recognition_capability(self) -> dict[str, str]:
        last_recognition = getattr(self.orchestrator, "last_recognition", None) or self.last_manual_recognition or {}
        failure_code = last_recognition.get("failure_code")
        if failure_code == "database_missing" or self._moss_assets_missing():
            return {
                "name": "Card recognition",
                "status": "blocked",
                "detail": "Moss Machine database assets are missing; copy unified_card_database.db and phash_cards_1.db to the Moss cache on the Pi.",
            }
        if failure_code:
            return {
                "name": "Card recognition",
                "status": "partial",
                "detail": f"Recognition is callable, but the last attempt failed with {failure_code}.",
            }
        return {
            "name": "Card recognition",
            "status": "ready",
            "detail": "Manual upload and live-camera recognition are available.",
        }

    def _moss_assets_missing(self) -> bool:
        cache_dir = self.repo_root / "third_party" / "fuzzy-enigma-card-recognition" / "data" / "cache" / "moss-machine"
        recognition_dir = (
            self.repo_root
            / "third_party"
            / "fuzzy-enigma-card-recognition"
            / "third_party"
            / "moss-machine"
            / "Current version"
            / "recognition_data"
        )
        required = ("unified_card_database.db", "phash_cards_1.db")
        return not all((cache_dir / name).exists() or (recognition_dir / name).exists() for name in required)

    def _collection_capability(self) -> dict[str, str]:
        status = self.collection_service_status()
        if not status["configured"]:
            return {
                "name": "Collection service",
                "status": "blocked",
                "detail": "Set SORTER_COLLECTION_SERVICE_URL and SORTER_COLLECTION_ID to connect the vendored collection service.",
            }
        if not status["available"]:
            return {
                "name": "Collection service",
                "status": "blocked",
                "detail": f"Configured at {status['base_url']}, but health checks fail: {status.get('message') or 'unavailable'}",
            }
        return {
            "name": "Collection service",
            "status": "ready",
            "detail": f"Collection service is healthy at {status['base_url']}.",
        }

    def collection_service_status(self) -> dict[str, Any]:
        collection_service = getattr(self.orchestrator, "collection_service", None)
        status_reader = getattr(collection_service, "system_status", None)
        if callable(status_reader):
            return status_reader()
        return {
            "configured": False,
            "available": False,
            "status": "unconfigured",
            "base_url": None,
            "collection_id": None,
            "ui_url": None,
            "review_url": None,
            "collections": [],
            "summary": None,
            "message": "Collection service URL is not configured.",
        }

    def _move_c(self, c_mm: float) -> None:
        mover = getattr(self.orchestrator.motion, "move_c", None)
        if not callable(mover):
            raise ValueError("C axis is not supported by the configured motion adapter")
        mover(float(c_mm))
        self.orchestrator.world.snapshot.pose.c_mm = float(c_mm)

    def _move_zc(self, z_mm: float, c_mm: float) -> None:
        mover = getattr(self.orchestrator.motion, "move_zc", None)
        if not callable(mover):
            raise ValueError("Coordinated Z/C motion is not supported by the configured motion adapter")
        mover(float(z_mm), float(c_mm))
        self.orchestrator.world.snapshot.pose.z_mm = float(z_mm)
        self.orchestrator.world.snapshot.pose.c_mm = float(c_mm)

    def system_info(self, refresh_remote: bool = False, refresh_visual_index: bool = False) -> dict[str, Any]:
        runtime_status = self.status()
        current_sha = _git(["rev-parse", "--short", "HEAD"], cwd=self.repo_root)
        current_branch = _git(["branch", "--show-current"], cwd=self.repo_root, default="detached")
        package_version = _package_version()
        dirty = bool(_git(["status", "--porcelain"], cwd=self.repo_root))
        fetch_error = None
        if refresh_remote:
            fetch = _run_git(["fetch", "origin", "main"], cwd=self.repo_root, timeout=30)
            if fetch.returncode != 0:
                fetch_error = fetch.stderr.strip() or fetch.stdout.strip() or "Unable to fetch origin/main"
        remote_sha = _git(["rev-parse", "--short", "origin/main"], cwd=self.repo_root)
        commits_behind = _count_commits(f"HEAD..origin/main", cwd=self.repo_root)
        commits_ahead = _count_commits("origin/main..HEAD", cwd=self.repo_root)
        update_available = commits_behind > 0
        can_update = update_available and current_branch == "main" and not dirty and fetch_error is None
        reason = None
        if not update_available:
            reason = "Already up to date"
        elif current_branch != "main":
            reason = "Switch to main before updating from the web UI"
        elif dirty:
            reason = "Commit or stash local changes before updating"
        elif fetch_error:
            reason = fetch_error
        visual_index = self.visual_index.status(
            running=runtime_status["lifecycle"] == "RUNNING",
            auto_start=refresh_visual_index,
        )
        return {
            "version": f"{package_version}-{current_sha}",
            "package_version": package_version,
            "current_sha": current_sha,
            "current_branch": current_branch,
            "dirty": dirty,
            "remote": "origin/main",
            "remote_sha": remote_sha,
            "commits_behind": commits_behind,
            "commits_ahead": commits_ahead,
            "update_available": update_available,
            "can_update": can_update,
            "message": reason,
            "restart_required": False,
            "submodules": [
                _submodule_status(
                    self.repo_root,
                    "fuzzy-enigma",
                    "third_party/fuzzy-enigma-card-recognition",
                    "Card recognition",
                ),
                _submodule_status(
                    self.repo_root,
                    "magic-the-collecting",
                    "third_party/magic-the-collecting",
                    "Collection and review service",
                ),
            ],
            "visual_index": visual_index,
            "runtime": runtime_status,
        }

    def update_from_remote(self) -> dict[str, Any]:
        before = self.system_info(refresh_remote=True, refresh_visual_index=False)
        if not before["can_update"]:
            return {"ok": False, **before}
        pull = _run_git(["pull", "--ff-only", "origin", "main"], cwd=self.repo_root, timeout=120)
        if pull.returncode != 0:
            after = self.system_info(refresh_remote=False, refresh_visual_index=False)
            return {
                "ok": False,
                **after,
                "message": pull.stderr.strip() or pull.stdout.strip() or "Update failed",
            }
        deploy = _run_deploy_script(self.repo_root)
        after = self.system_info(refresh_remote=False, refresh_visual_index=False)
        if deploy.returncode != 0:
            return {
                "ok": False,
                **after,
                "message": deploy.stderr.strip() or deploy.stdout.strip() or "Deploy install failed",
                "deploy_returncode": deploy.returncode,
            }
        restart_required = before["current_sha"] != after["current_sha"]
        restart_scheduled = _schedule_web_process_restart() if restart_required else False
        message = (
            "Updated from origin/main, installed dependencies, and restarting the web process."
            if restart_scheduled
            else "Updated from origin/main and installed dependencies. Restart the web process to run the new code."
        )
        return {
            "ok": True,
            **after,
            "message": message,
            "restart_required": restart_required,
            "restart_scheduled": restart_scheduled,
        }

    def visual_index_status(self, refresh_if_idle: bool = True) -> dict[str, Any]:
        runtime_status = self.status()
        return self.visual_index.status(
            running=runtime_status["lifecycle"] == "RUNNING",
            auto_start=refresh_if_idle,
        )

    def refresh_visual_index(self) -> dict[str, Any]:
        return self.visual_index.refresh(force=True)

    def set_visual_index_policy(self, refresh_days: int) -> dict[str, Any]:
        self.visual_index.save_policy(refresh_days)
        return self.visual_index_status(refresh_if_idle=False)


def create_web_app(
    orchestrator: Orchestrator,
    calibration: CalibrationProfile,
    slow_ms: int = 0,
    light_profiles_path: Path | None = None,
    light_profiles_seed_path: Path | None = None,
    calibration_path: Path | None = None,
    runtime_mode: str = "hardware",
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    runtime = WebRuntime(
        orchestrator,
        calibration,
        slow_ms=slow_ms,
        light_profiles_path=light_profiles_path,
        light_profiles_seed_path=light_profiles_seed_path,
        calibration_path=calibration_path,
        runtime_mode=runtime_mode,
    )
    app.config["runtime"] = runtime

    @app.before_request
    def begin_api_debug_event():
        if request.path.startswith("/api/"):
            g.api_started_at = time.monotonic()

    @app.after_request
    def record_api_debug_event(response):
        if request.path.startswith("/api/"):
            started_at = getattr(g, "api_started_at", time.monotonic())
            runtime.record_debug_event(
                "api.call",
                {
                    "method": request.method,
                    "path": request.path,
                    "query": request.query_string.decode("utf-8", errors="replace"),
                    "status_code": response.status_code,
                    "elapsed_ms": _elapsed_ms(started_at),
                    "payload": _request_debug_payload(),
                },
            )
        return response

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/camera")
    def camera():
        return render_template("camera.html")

    @app.get("/machine")
    def machine():
        return render_template("machine.html")

    @app.get("/movement")
    def movement():
        return render_template("movement.html")

    @app.get("/recognition")
    def recognition():
        recognizer = getattr(runtime.orchestrator, "recognizer", None)
        selected_backend = getattr(recognizer, "sorter_backend", None)
        if not isinstance(selected_backend, str) or not selected_backend.strip():
            selected_backend = "fuzzy_enigma"
        return render_template(
            "recognition.html",
            recognition_backends=RECOGNITION_BACKEND_OPTIONS,
            selected_recognition_backend=selected_backend.strip().lower(),
        )

    @app.get("/card-back-training")
    def card_back_training():
        return render_template("card_back_training.html")

    @app.get("/runs")
    def runs():
        return render_template("runs.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/system")
    def system():
        return render_template("system.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(runtime.status())

    @app.get("/api/snapshot")
    def api_snapshot():
        return jsonify(runtime.snapshot())

    @app.get("/api/calibration")
    def api_calibration():
        return jsonify({"calibration": runtime.calibration_payload()})

    @app.post("/api/calibration")
    def api_update_calibration():
        try:
            return jsonify(runtime.update_calibration(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/saved-positions")
    def api_saved_positions():
        try:
            return jsonify(runtime.saved_positions_payload())
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/saved-positions")
    def api_create_saved_position():
        try:
            return jsonify(runtime.create_saved_position(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.patch("/api/saved-positions/<position_id>")
    def api_update_saved_position(position_id: str):
        try:
            return jsonify(runtime.update_saved_position(position_id, request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.delete("/api/saved-positions/<position_id>")
    def api_delete_saved_position(position_id: str):
        try:
            return jsonify(runtime.delete_saved_position(position_id))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/saved-positions/<position_id>/go")
    def api_go_to_saved_position(position_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            result = runtime.go_to_saved_position(position_id, payload)
            runtime.record_control_audit(action="saved_position_go", payload={"position_id": position_id, **payload}, result=result)
            return jsonify(result)
        except Exception as exc:
            runtime.record_control_audit(action="saved_position_go", payload={"position_id": position_id, **payload}, error=str(exc))
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/run/start")
    def api_start():
        return jsonify(runtime.start_run())

    @app.post("/api/run/stop")
    def api_stop():
        runtime.stop_run()
        return jsonify({"ok": True, "message": "Stop requested"})

    @app.post("/api/control/<action>")
    def api_control(action: str):
        payload = request.get_json(silent=True) or {}
        runtime.record_debug_event("api.control.request", {"action": action, "payload": payload})
        try:
            result = runtime.control(action, payload)
            runtime.record_control_audit(action=action, payload=payload, result=result)
            runtime.record_debug_event(
                "api.control.response",
                {"action": action, "ok": True, "message": result.get("message"), "runtime_target": runtime.status().get("runtime_target")},
            )
            return jsonify(result)
        except Exception as exc:
            runtime.record_control_audit(action=action, payload=payload, error=str(exc))
            runtime.record_debug_event("api.control.error", {"action": action, "payload": payload, "error": str(exc)})
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/debug/event")
    def api_debug_event():
        payload = request.get_json(silent=True) or {}
        event = str(payload.get("event", "ui.event"))
        details = payload.get("details", {})
        runtime.record_debug_event(event, details if isinstance(details, dict) else {"value": details})
        return jsonify({"ok": True})

    @app.get("/api/card/validate")
    def api_validate_card():
        return jsonify(runtime.validate_card(request.args.get("q", "")))

    @app.post("/api/recognition/run")
    def api_recognition_run():
        source = request.form.get("source", "upload")
        payload = {
            "mode": _normalize_web_recognition_mode(request.form.get("mode", "greenfield")),
            "backend": request.form.get("backend") or None,
            "prefer_visual_small_pool": request.form.get("prefer_visual_small_pool") == "true",
            "use_tracked_pool": request.form.get("use_tracked_pool") == "true",
            "track_result": request.form.get("track_result") == "true",
        }
        crop = _crop_payload_from_form(request.form)
        if crop is not None:
            payload["crop"] = crop
        moss_threshold = request.form.get("moss_threshold", "").strip()
        if moss_threshold:
            payload["moss_threshold"] = moss_threshold
        expected_name = request.form.get("expected_name", "").strip()
        expected_set = request.form.get("expected_set", "").strip()
        expected_collector = request.form.get("expected_collector", "").strip()
        if expected_name or expected_set or expected_collector:
            payload["expected_card"] = {
                "name": expected_name or None,
                "set_code": expected_set or None,
                "collector_number": expected_collector or None,
            }
        try:
            if source == "camera":
                result = runtime.recognize_camera_image(payload)
            else:
                upload = request.files.get("image")
                if upload is None or not upload.filename:
                    return jsonify({"ok": False, "message": "Image upload required"}), 400
                suffix = Path(upload.filename).suffix or ".png"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                    temp_path = Path(handle.name)
                upload.save(temp_path)
                result = runtime.recognize_uploaded_image(temp_path, payload)
            return jsonify({"ok": True, "result": result})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 500

    @app.get("/api/runs")
    def api_runs():
        return jsonify({"runs": runtime.recent_runs()})

    @app.get("/api/capabilities")
    def api_capabilities():
        return jsonify({"capabilities": runtime.capabilities()})

    @app.get("/api/system")
    def api_system():
        return jsonify(runtime.system_info(refresh_remote=request.args.get("refresh") == "true", refresh_visual_index=not app.testing))

    @app.get("/api/system/visual-index")
    def api_system_visual_index():
        return jsonify(runtime.visual_index_status(refresh_if_idle=not app.testing))

    @app.post("/api/system/visual-index/refresh")
    def api_system_visual_index_refresh():
        return jsonify(runtime.refresh_visual_index())

    @app.post("/api/system/visual-index/policy")
    def api_system_visual_index_policy():
        payload = request.get_json(silent=True) or {}
        try:
            refresh_days = int(payload.get("refresh_days"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "refresh_days must be one of 1, 3, 7, 14, 30, 60, or 90"}), 400
        if refresh_days not in VISUAL_INDEX_REFRESH_DAY_OPTIONS:
            return jsonify({"ok": False, "message": "refresh_days must be one of 1, 3, 7, 14, 30, 60, or 90"}), 400
        try:
            status = runtime.set_visual_index_policy(refresh_days)
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, **status})

    @app.get("/api/collection-service")
    def api_collection_service():
        return jsonify(runtime.collection_service_status())

    @app.post("/api/system/update")
    def api_system_update():
        status_code = 200
        payload = runtime.update_from_remote()
        if not payload.get("ok", False):
            status_code = 409
        return jsonify(payload), status_code

    @app.get("/api/runtime")
    def api_runtime():
        return jsonify({"runtime_mode": runtime.runtime_mode, "status": runtime.status()})

    @app.post("/api/runtime")
    def api_runtime_update():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(runtime.set_runtime_mode(str(payload.get("mode", ""))))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), "status": runtime.status()}), 400

    @app.get("/api/serial/ports")
    def api_serial_ports():
        auto = request.args.get("auto") == "true"
        auto_result = runtime.serial_board.auto_connect() if auto else None
        return jsonify(
            {
                "ports": runtime.serial_board.list_ports(),
                "status": runtime.serial_board.status(),
                "auto": auto_result,
            }
        )

    @app.post("/api/serial/connect")
    def api_serial_connect():
        payload = request.get_json(silent=True) or {}
        port = str(payload.get("port", "")).strip()
        baud_rate = int(payload.get("baud_rate", 115200))
        runtime.record_debug_event("api.serial.connect.request", {"port": port or None, "baud_rate": baud_rate})
        try:
            result = runtime.serial_board.auto_connect() if not port else runtime.serial_board.connect(port, baud_rate)
            runtime.record_debug_event(
                "api.serial.connect.response",
                {"ok": result.get("ok"), "port": result.get("port"), "message": result.get("message"), "state": result.get("connection_state")},
            )
            return jsonify(result)
        except Exception as exc:
            runtime.record_debug_event("api.serial.connect.error", {"port": port or None, "baud_rate": baud_rate, "error": str(exc)})
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/disconnect")
    def api_serial_disconnect():
        runtime.record_debug_event("api.serial.disconnect.request", runtime.serial_board.status())
        try:
            result = runtime.serial_board.disconnect()
            runtime.record_debug_event("api.serial.disconnect.response", {"ok": result.get("ok"), "message": result.get("message")})
            return jsonify(result)
        except Exception as exc:
            runtime.record_debug_event("api.serial.disconnect.error", {"error": str(exc)})
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/send")
    def api_serial_send():
        payload = request.get_json(silent=True) or {}
        command = str(payload.get("command", "")).strip()
        runtime.record_debug_event("api.serial.send.request", {"command": command})
        try:
            result = runtime.serial_board.send_command(command)
            runtime.record_debug_event("api.serial.send.response", {"command": command, "ok": result.get("ok"), "message": result.get("message")})
            return jsonify(result)
        except Exception as exc:
            runtime.record_debug_event("api.serial.send.error", {"command": command, "error": str(exc)})
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.get("/api/serial/endstops")
    def api_serial_endstops():
        try:
            poll = request.args.get("poll") == "true"
            return jsonify(runtime.serial_board.read_endstops(poll=poll))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/heartbeat")
    def api_serial_heartbeat():
        try:
            return jsonify(runtime.serial_board.send_status_poll("M114"))
        except Exception as exc:
            runtime.record_debug_event("api.serial.heartbeat.error", {"error": str(exc)})
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/bltouch/<action>")
    def api_serial_bltouch(action: str):
        runtime.record_debug_event("api.serial.bltouch.request", {"action": action})
        try:
            result = runtime.serial_board.bltouch(action)
            runtime.record_debug_event("api.serial.bltouch.response", {"action": action, "ok": result.get("ok")})
            return jsonify(result)
        except Exception as exc:
            runtime.record_debug_event("api.serial.bltouch.error", {"action": action, "error": str(exc)})
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.get("/api/light-profiles")
    def api_light_profiles():
        return jsonify({"profiles": runtime.list_light_profiles()})

    @app.post("/api/light-profiles")
    def api_create_light_profile():
        payload = request.get_json(silent=True) or {}
        try:
            profile = runtime.create_light_profile(
                str(payload.get("name", "")),
                int(payload.get("red", 0)),
                int(payload.get("green", 0)),
                int(payload.get("blue", 0)),
            )
            return jsonify({"ok": True, "profile": profile})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/neopixel/profiles")
    def api_neopixel_profiles():
        return jsonify({"profiles": runtime.list_pixel_profiles()})

    @app.get("/api/neopixel/profile-options")
    def api_neopixel_profile_options():
        return jsonify({"profiles": runtime.list_neopixel_profile_options()})

    @app.post("/api/neopixel/profiles")
    def api_create_neopixel_profile():
        payload = request.get_json(silent=True) or {}
        try:
            profile = runtime.create_pixel_profile(str(payload.get("name", "")), payload.get("pixels"))
            return jsonify({"ok": True, "profile": profile})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.delete("/api/neopixel/profiles")
    def api_delete_neopixel_profile():
        payload = request.get_json(silent=True) or {}
        try:
            runtime.delete_neopixel_profile(str(payload.get("kind", "")), str(payload.get("name", "")))
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/neopixel/display")
    def api_neopixel_display():
        try:
            return jsonify(runtime.apply_neopixel_display(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), "status": runtime.status()}), 400

    @app.post("/api/lights/optimize")
    def api_lights_optimize():
        try:
            return jsonify(runtime.optimize_lighting(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), "status": runtime.status()}), 400

    @app.post("/api/card-back/detect")
    def api_card_back_detect():
        try:
            return jsonify(runtime.detect_card_back_from_camera(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"found": False, "confidence": 0.0, "message": str(exc), "status": runtime.status()}), 400

    @app.get("/api/card-back-training")
    def api_card_back_training_summary():
        return jsonify(runtime.card_back_training_summary())

    @app.post("/api/card-back-training/models")
    def api_create_card_back_training_model():
        try:
            return jsonify(runtime.create_card_back_training_model(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/card-back-training/models/active")
    def api_set_active_card_back_training_model():
        try:
            return jsonify(runtime.set_active_card_back_training_model(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.delete("/api/card-back-training/models/<model_id>")
    def api_delete_card_back_training_model(model_id: str):
        try:
            return jsonify(runtime.delete_card_back_training_model(model_id))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/card-back-training/plan")
    def api_card_back_training_plan():
        try:
            return jsonify(runtime.generate_card_back_capture_plan(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/card-back-training/capture")
    def api_card_back_training_capture():
        try:
            return jsonify(runtime.capture_card_back_training_sample(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), "status": runtime.status()}), 400

    @app.patch("/api/card-back-training/models/<model_id>/samples/<sample_id>")
    def api_card_back_training_update_sample(model_id: str, sample_id: str):
        try:
            return jsonify(runtime.update_card_back_training_sample(model_id, sample_id, request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.delete("/api/card-back-training/models/<model_id>/samples/<sample_id>")
    def api_card_back_training_delete_sample(model_id: str, sample_id: str):
        try:
            return jsonify(runtime.delete_card_back_training_sample(model_id, sample_id))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/card-back-training/models/<model_id>/samples/<sample_id>/image.jpg")
    def api_card_back_training_sample_image(model_id: str, sample_id: str):
        try:
            return send_file(runtime.card_back_training.sample_image_path(model_id, sample_id), mimetype="image/jpeg")
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 404

    @app.get("/api/card-back-training/models/<model_id>/samples/<sample_id>")
    def api_card_back_training_sample(model_id: str, sample_id: str):
        try:
            return jsonify({"ok": True, "sample": runtime.card_back_training.sample_payload(model_id, sample_id)})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 404

    @app.post("/api/card-back-training/models/<model_id>/training-runs")
    def api_card_back_training_run(model_id: str):
        try:
            return jsonify(runtime.register_card_back_training_run(model_id, request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/camera/frame.jpg")
    def camera_frame():
        image = runtime.latest_camera_image()
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88)
        buffer.seek(0)
        return send_file(buffer, mimetype="image/jpeg")

    @app.get("/camera/stream")
    def camera_stream():
        def generate():
            while True:
                image = runtime.latest_camera_image()
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=82)
                payload = buffer.getvalue()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                    + payload
                    + b"\r\n"
                )
                time.sleep(0.5)

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


def _clamp_channel(value: int) -> int:
    return max(0, min(255, int(value)))


def _crop_payload_from_form(form: Any) -> dict[str, float] | None:
    values: dict[str, float] = {}
    for key in ("left", "top", "right", "bottom"):
        raw = form.get(f"crop_{key}", "")
        if str(raw).strip() == "":
            return None
        try:
            values[key] = float(raw)
        except (TypeError, ValueError):
            return None
    return _normalize_crop_payload(values)


def _normalize_web_recognition_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or "greenfield").strip().lower()
    if mode in {"expected_card", "expected-card"}:
        return "reevaluation"
    return mode or "greenfield"


def _bounded_jog_delta(raw_value: Any, *, axis: str, limit_mm: float | None) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f"{axis} jog distance must be a number") from None
    if limit_mm is not None and abs(value) > limit_mm:
        raise ValueError(f"{axis} jog distance {value:.2f} mm exceeds {limit_mm:.2f} mm per command")
    return value


def _normalize_crop_payload(raw_crop: Any) -> dict[str, float] | None:
    if not isinstance(raw_crop, dict):
        return None
    try:
        left = float(raw_crop.get("left", 0.0))
        top = float(raw_crop.get("top", 0.0))
        right = float(raw_crop.get("right", 1.0))
        bottom = float(raw_crop.get("bottom", 1.0))
    except (TypeError, ValueError):
        return None
    if max(left, top, right, bottom) > 1.0:
        left /= 100.0
        top /= 100.0
        right /= 100.0
        bottom /= 100.0
    left = max(0.0, min(0.98, left))
    top = max(0.0, min(0.98, top))
    right = max(left + 0.01, min(1.0, right))
    bottom = max(top + 0.01, min(1.0, bottom))
    if left <= 0.0 and top <= 0.0 and right >= 1.0 and bottom >= 1.0:
        return None
    return {
        "left": round(left, 4),
        "top": round(top, 4),
        "right": round(right, 4),
        "bottom": round(bottom, 4),
    }


def _crop_image(image: Image.Image, crop: dict[str, float] | None) -> Image.Image:
    if crop is None:
        return image
    width, height = image.size
    left = int(width * crop["left"])
    top = int(height * crop["top"])
    right = int(width * crop["right"])
    bottom = int(height * crop["bottom"])
    if right <= left or bottom <= top:
        return image
    return image.crop((left, top, right, bottom))


def _format_mm(value: float) -> str:
    return f"{float(value):.3f}"


def _format_feedrate(value: float) -> str:
    return f"{float(value):.0f}"


def _live_xyz_feedrate_mm_per_min(
    *,
    current_x_mm: float | None,
    current_y_mm: float | None,
    current_z_mm: float | None,
    target_x_mm: float,
    target_y_mm: float,
    target_z_mm: float,
) -> float:
    max_z_feedrate_mm_per_min = MAX_SERIAL_COMBINED_Z_SPEED_MM_PER_S * 60.0
    if current_z_mm is None:
        return min(MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN, max_z_feedrate_mm_per_min)
    dz_mm = abs(float(target_z_mm) - float(current_z_mm))
    if dz_mm <= 0:
        return MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN
    if current_x_mm is None or current_y_mm is None:
        return min(MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN, max_z_feedrate_mm_per_min)
    dx_mm = float(target_x_mm) - float(current_x_mm)
    dy_mm = float(target_y_mm) - float(current_y_mm)
    move_length_mm = math.sqrt(dx_mm * dx_mm + dy_mm * dy_mm + dz_mm * dz_mm)
    z_limited_feedrate_mm_per_min = max_z_feedrate_mm_per_min * move_length_mm / dz_mm
    return min(MAX_SERIAL_XY_FEEDRATE_MM_PER_MIN, z_limited_feedrate_mm_per_min)


def _package_version() -> str:
    pyproject_path = _repo_root() / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except Exception:
        try:
            return version("card-sorter-testbed")
        except PackageNotFoundError:
            return "0.0.0"


def _repo_root() -> Path:
    found = _git(["rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent)
    return Path(found) if found else Path(__file__).resolve().parents[4]


def _count_commits(revision_range: str, cwd: Path) -> int:
    count = _git(["rev-list", "--count", revision_range], cwd=cwd, default="0")
    try:
        return int(count)
    except ValueError:
        return 0


def _submodule_status(repo_root: Path, name: str, relative_path: str, role: str) -> dict[str, Any]:
    module_path = repo_root / relative_path
    tree_entry = _git(["ls-tree", "HEAD", "--", relative_path], cwd=repo_root)
    parts = tree_entry.split()
    expected_sha = parts[2] if len(parts) >= 3 and parts[0] == "160000" else None
    initialized = module_path.is_dir() and (module_path / ".git").exists()
    actual_sha = _git(["-C", str(module_path), "rev-parse", "HEAD"], cwd=repo_root) if initialized else ""
    return {
        "name": name,
        "role": role,
        "path": relative_path,
        "initialized": initialized,
        "expected_sha": expected_sha,
        "current_sha": actual_sha or expected_sha,
        "at_expected_revision": bool(expected_sha and (not actual_sha or actual_sha == expected_sha)),
    }


def _git(args: list[str], cwd: Path, default: str = "") -> str:
    result = _run_git(args, cwd=cwd)
    if result.returncode != 0:
        return default
    return result.stdout.strip()


def _run_git(args: list[str], cwd: Path, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            ["git", *args],
            returncode=124,
            stdout=exc.stdout or "",
            stderr=f"Git command timed out after {timeout} seconds",
        )


def _run_deploy_script(repo_root: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    script = repo_root / "scripts" / "deploy-rpi-webserver.sh"
    if not script.exists():
        return subprocess.CompletedProcess(
            [str(script), "--no-pull"],
            returncode=127,
            stdout="",
            stderr=f"Deploy script not found: {script}",
        )
    try:
        return subprocess.run(
            ["bash", str(script), "--no-pull"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            [str(script), "--no-pull"],
            returncode=124,
            stdout=exc.stdout or "",
            stderr=f"Deploy script timed out after {timeout} seconds",
        )


def _schedule_web_process_restart(delay_seconds: float = 1.0) -> bool:
    disabled = os.environ.get("SORTER_DISABLE_AUTO_RESTART_AFTER_UPDATE", "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    timer = threading.Timer(delay_seconds, lambda: os._exit(0))
    timer.daemon = True
    timer.start()
    return True
