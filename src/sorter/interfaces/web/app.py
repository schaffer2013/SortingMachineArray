from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, UTC
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
import tomllib
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw

from sorter.application.orchestrator import Orchestrator
from sorter.adapters.hardware.marlin_transport import MarlinSerialTransport
from sorter.adapters.hardware.neopixel_lights import NeoPixelLightsAdapter
from sorter.config.calibration import CalibrationProfile
from sorter.domain.models import PileState
from sorter.ports.camera import Frame


class SerialBoardSession:
    def __init__(self):
        self.transport: MarlinSerialTransport | None = None
        self.lights: NeoPixelLightsAdapter | None = None
        self.port: str | None = None
        self.baud_rate = 115200
        self.last_error: str | None = None
        self.last_response: list[str] = []
        self.last_endstops: dict[str, str] = {}
        self.live_pose: dict[str, float] = {}
        self.last_success_monotonic: float | None = None
        self.connection_state = "disconnected"
        self.lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        with self.lock:
            session_open = self.transport is not None
            verified = session_open and self.connection_state == "verified"
            if verified and self.last_success_monotonic is not None:
                if time.monotonic() - self.last_success_monotonic > 5.0:
                    verified = False
                    state = "stale"
                else:
                    state = "verified"
            else:
                state = self.connection_state if session_open else "disconnected"
            return {
                "connected": verified,
                "session_open": session_open,
                "connection_state": state,
                "port": self.port,
                "baud_rate": self.baud_rate,
                "last_error": self.last_error,
                "last_response": self.last_response,
                "last_endstops": self.last_endstops,
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
        with self.lock:
            if self.transport is not None:
                return {"ok": True, "message": f"Already connected to {self.port}", **self.status()}
            ports = self.list_ports()
            for item in sorted(ports, key=_port_auto_score, reverse=True):
                try:
                    return self.connect(item["device"])
                except Exception:
                    continue
            message = self.last_error or "No serial board responded to M115"
            return {"ok": False, "message": message, **self.status()}

    def connect(self, port: str, baud_rate: int = 115200) -> dict[str, Any]:
        with self.lock:
            self.disconnect()
            self.port = port
            self.baud_rate = int(baud_rate)
            transport = MarlinSerialTransport(serial_port=port, baud_rate=self.baud_rate, timeout_seconds=60.0)
            try:
                response = transport.send_command("M115")
            except Exception as exc:
                transport.close()
                self.transport = None
                self.lights = None
                self.last_error = str(exc)
                self.last_response = []
                self.connection_state = "error"
                raise
            self.transport = transport
            self.lights = NeoPixelLightsAdapter(transport=transport)
            self.last_error = None
            self.last_response = response
            self.last_success_monotonic = time.monotonic()
            self.connection_state = "verified"
            return {"ok": True, "message": f"Connected to {port}", **self.status()}

    def disconnect(self) -> dict[str, Any]:
        with self.lock:
            if self.transport is not None:
                self.transport.close()
            self.transport = None
            self.lights = None
            self.port = None
            self.connection_state = "disconnected"
            return {"ok": True, "message": "Disconnected", **self.status()}

    def send_command(self, command: str) -> dict[str, Any]:
        with self.lock:
            if self.transport is None:
                raise ValueError("Serial board is not connected")
            try:
                response = self.transport.send_command(command)
            except Exception as exc:
                self.last_error = str(exc)
                self.connection_state = "error"
                if self.transport is not None:
                    self.transport.close()
                self.transport = None
                self.lights = None
                raise
            self.last_error = None
            self.last_response = response
            self.last_success_monotonic = time.monotonic()
            self.connection_state = "verified"
            pose = _parse_m114(response)
            if pose:
                self.live_pose.update(pose)
            return {"ok": True, "message": f"Sent {command.strip()}", "response": response, **self.status()}

    def send_commands(self, commands: list[str], *, message: str) -> dict[str, Any]:
        responses: list[str] = []
        with self.lock:
            for command in commands:
                result = self.send_command(command)
                responses.extend(result["response"])
            return {"ok": True, "message": message, "response": responses, **self.status()}

    def read_endstops(self) -> dict[str, Any]:
        with self.lock:
            result = self.send_command("M119")
            endstops = _parse_m119(result["response"])
            self.last_endstops = endstops
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
        with self.lock:
            if self.lights is not None:
                self.lights.set_status(status)
                self.last_response = list(getattr(self.transport, "command_log", []))[-1:]

    def set_lights_rgb(self, red: int, green: int, blue: int, *, profile_name: str | None = None) -> None:
        with self.lock:
            if self.lights is not None:
                self.lights.set_rgb(red, green, blue, profile_name=profile_name)
                self.last_response = list(getattr(self.transport, "command_log", []))[-1:]


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
        calibration_path: Path | None = None,
    ):
        self.orchestrator = orchestrator
        self.calibration = calibration
        self.slow_ms = max(0, slow_ms)
        self.stop_event = threading.Event()
        self.run_thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_manual_recognition: dict[str, Any] | None = None
        self.machine_initialized = False
        self.light_profiles_path = light_profiles_path
        self.calibration_path = calibration_path
        self.repo_root = _repo_root()
        self.light_profiles = self._load_light_profiles()
        self.serial_board = SerialBoardSession()
        self.lock = threading.RLock()

    def start_run(self) -> dict[str, Any]:
        with self.lock:
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
            live_connected = bool(serial_status["connected"])
            session_open = bool(serial_status.get("session_open"))
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
                "runtime_target": "hardware_serial" if live_connected else "sim",
                "runtime_message": (
                    f"Live board connected on {serial_status['port']}"
                    if live_connected
                    else (
                        f"Serial session is {serial_status.get('connection_state')} on {serial_status.get('port')}; not verified live"
                        if session_open
                        else "SIM BACKED: connect a serial board on System before using controls for hardware"
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
                "machine_initialized": self.machine_initialized,
                "calibration": self.calibration_payload(),
                "serial_board": serial_status,
            }

    def calibration_payload(self) -> dict[str, Any]:
        return self.calibration.to_json_dict()

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
            if self.calibration_path is not None:
                self.calibration.save(self.calibration_path)
            return {"ok": True, "calibration": self.calibration_payload()}

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
            return {
                "ok": True,
                "message": f"Machine initialized and homed; vacuum Z at {travel_z_mm:.2f} mm travel clearance",
            }

    def control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.serial_board.status()["connected"] and action in {
            "initialize",
            "home",
            "wait_idle",
            "move_xy",
            "jog_xy",
            "move_camera_xy",
            "move_z",
            "jog_z",
            "move_c",
            "jog_c",
            "jog_zc_interface",
        }:
            return self._hardware_serial_control(action, payload)
        if action == "initialize":
            return self.initialize_machine()
        if action == "home":
            self.orchestrator.motion.home_axes()
            snapshot = self.orchestrator.world.snapshot
            snapshot.pose.x_mm = 0.0
            snapshot.pose.y_mm = 0.0
            snapshot.pose.z_mm = self.calibration.z_home_mm
            snapshot.pose.c_mm = self.calibration.c_home_mm
            self.machine_initialized = False
            return {
                "ok": True,
                "message": (
                    f"Axes homed; X/Y at 0.00 mm, Z at {self.calibration.z_home_mm:.2f} mm, "
                    f"C at {self.calibration.c_home_mm:.2f} mm"
                ),
            }
        if action == "wait_idle":
            self.orchestrator.motion.wait_until_idle()
            return {"ok": True, "message": "Motion idle"}
        if action == "move_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_vac_xy_when_safe(self.calibration, x_mm, y_mm)
            return {"ok": True, "message": f"Moved vacuum XY to ({x_mm:.2f}, {y_mm:.2f})"}
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
            return {
                "ok": True,
                "message": (
                    f"Moved camera over ({x_mm:.2f}, {y_mm:.2f}) "
                    f"using vacuum baseline ({target_x_mm:.2f}, {target_y_mm:.2f})"
                ),
            }
        if action == "move_z":
            z_mm = float(payload["z_mm"])
            self.orchestrator.move_vac_z(z_mm)
            return {"ok": True, "message": f"Moved vacuum Z to {z_mm:.2f}"}
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
            self.serial_board.set_lights_status(status)
            return {"ok": True, "message": f"Lights set to {status}"}
        if action == "light_profile":
            profile_name = str(payload["name"])
            profile = self.light_profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"Unknown light profile: {profile_name}")
            self._apply_light_profile(profile_name, profile)
            return {"ok": True, "message": f"Applied light profile {profile_name}"}
        raise ValueError(f"Unsupported control action: {action}")

    def _hardware_serial_control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "initialize":
            return self.serial_board.send_commands(
                ["G28 Z", "G28 C", "G28 X Y", "M114"],
                message="Live board initialized and homed",
            )
        if action == "home":
            return self.serial_board.send_commands(["G28", "M114"], message="Live board axes homed")
        if action == "wait_idle":
            return self.serial_board.send_commands(["M400", "M114"], message="Live board idle")
        if action in {"move_xy", "move_camera_xy"}:
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            if action == "move_camera_xy":
                x_mm, y_mm = self.calibration.camera_baseline_xy_for_vacuum_target(x_mm, y_mm)
            return self.serial_board.send_commands(
                [f"G90", f"G1 X{_format_mm(x_mm)} Y{_format_mm(y_mm)} F6000", "M400", "M114"],
                message=f"Live board moved XY to ({x_mm:.2f}, {y_mm:.2f})",
            )
        if action == "jog_xy":
            dx_mm = float(payload.get("dx_mm", 0.0))
            dy_mm = float(payload.get("dy_mm", 0.0))
            return self.serial_board.send_commands(
                ["G91", f"G1 X{_format_mm(dx_mm)} Y{_format_mm(dy_mm)} F600", "M400", "G90", "M114"],
                message=f"Live board jogged XY by ({dx_mm:.2f}, {dy_mm:.2f})",
            )
        if action == "move_z":
            z_mm = float(payload["z_mm"])
            return self.serial_board.send_commands(
                ["G90", f"G1 Z{_format_mm(z_mm)} F1200", "M400", "M114"],
                message=f"Live board moved Z to {z_mm:.2f}",
            )
        if action == "jog_z":
            dz_mm = float(payload.get("dz_mm", 0.0))
            return self.serial_board.send_commands(
                ["G91", f"G1 Z{_format_mm(dz_mm)} F300", "M400", "G90", "M114"],
                message=f"Live board jogged Z by {dz_mm:.2f}",
            )
        if action == "move_c":
            c_mm = float(payload["c_mm"])
            return self.serial_board.send_commands(
                ["G90", f"G1 C{_format_mm(c_mm)} F1200", "M400", "M114"],
                message=f"Live board moved C to {c_mm:.2f}",
            )
        if action == "jog_c":
            dc_mm = float(payload.get("dc_mm", 0.0))
            return self.serial_board.send_commands(
                ["G91", f"G1 C{_format_mm(dc_mm)} F300", "M400", "G90", "M114"],
                message=f"Live board jogged C by {dc_mm:.2f}",
            )
        if action == "jog_zc_interface":
            dz_mm = float(payload.get("dz_mm", 0.0))
            return self.serial_board.send_commands(
                ["G91", f"G1 Z{_format_mm(dz_mm)} C{_format_mm(-dz_mm)} F300", "M400", "G90", "M114"],
                message=f"Live board moved interface Z by {dz_mm:.2f}",
            )
        raise ValueError(f"Unsupported live serial control action: {action}")

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
        if self.light_profiles_path is None or not self.light_profiles_path.exists():
            return default_profiles
        with self.light_profiles_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        loaded = {
            str(item["name"]): {
                "red": int(item["red"]),
                "green": int(item["green"]),
                "blue": int(item["blue"]),
            }
            for item in raw.get("profiles", [])
        }
        return loaded or default_profiles

    def _save_light_profiles(self) -> None:
        if self.light_profiles_path is None:
            return
        self.light_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                {"name": name, **channels}
                for name, channels in sorted(self.light_profiles.items())
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

    def _apply_light_profile(self, name: str, channels: dict[str, int]) -> None:
        setter = getattr(self.orchestrator.lights, "set_rgb", None)
        if callable(setter):
            setter(channels["red"], channels["green"], channels["blue"], profile_name=name)
            self.serial_board.set_lights_rgb(channels["red"], channels["green"], channels["blue"], profile_name=name)
            return
        self.orchestrator.lights.set_status(name)
        self.serial_board.set_lights_status(name)

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
        frame = Frame(
            frame_id=f"web-{int(time.time() * 1000)}",
            path=str(image_path),
            pile_id=None,
            metadata={"recognition_request": request_payload},
            captured_at_utc=datetime.now(UTC).isoformat(),
            camera_id="web_upload",
            source_mode="manual_web",
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
        return [
            {"name": "Automated sorting run", "status": "ready", "detail": "End-to-end in sim via the orchestrator."},
            {"name": "Live machine status", "status": "ready", "detail": "Phase, active command, pose, pile state, metrics."},
            {"name": "Motion control", "status": "ready", "detail": "Home, XY, Z, and idle-wait controls via MotionPort."},
            {"name": "Vacuum and lights", "status": "ready", "detail": "Manual I/O commands via VacuumPort and LightsPort."},
            {"name": "Card recognition", "status": "ready", "detail": "Manual image recognition plus review/fallback metadata."},
            {"name": "Card validation", "status": "ready", "detail": "Catalog-backed exact validation with suggestions."},
            {"name": "Run history", "status": "ready", "detail": "SQLite-backed recent run summaries and metrics."},
            {"name": "Camera preview", "status": "partial", "detail": "Web stream endpoint exists; current Pi adapter still needs real frame capture wiring."},
            {"name": "Operator review workflow", "status": "partial", "detail": "Recognition evidence exists; explicit correction/confirmation is a next hardware milestone."},
            {"name": "Hardware runtime", "status": "partial", "detail": "Adapters exist, but the repo currently documents sim as the supported end-to-end runtime."},
        ]

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

    def system_info(self, refresh_remote: bool = False) -> dict[str, Any]:
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
        }

    def update_from_remote(self) -> dict[str, Any]:
        before = self.system_info(refresh_remote=True)
        if not before["can_update"]:
            return {"ok": False, **before}
        pull = _run_git(["pull", "--ff-only", "origin", "main"], cwd=self.repo_root, timeout=120)
        after = self.system_info(refresh_remote=False)
        if pull.returncode != 0:
            return {
                "ok": False,
                **after,
                "message": pull.stderr.strip() or pull.stdout.strip() or "Update failed",
            }
        return {
            "ok": True,
            **after,
            "message": "Updated from origin/main. Restart the web process to run the new code.",
            "restart_required": before["current_sha"] != after["current_sha"],
        }


def create_web_app(
    orchestrator: Orchestrator,
    calibration: CalibrationProfile,
    slow_ms: int = 0,
    light_profiles_path: Path | None = None,
    calibration_path: Path | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    runtime = WebRuntime(
        orchestrator,
        calibration,
        slow_ms=slow_ms,
        light_profiles_path=light_profiles_path,
        calibration_path=calibration_path,
    )
    app.config["runtime"] = runtime

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/machine")
    def machine():
        return render_template("machine.html")

    @app.get("/movement")
    def movement():
        return render_template("movement.html")

    @app.get("/recognition")
    def recognition():
        return render_template("recognition.html")

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

    @app.post("/api/run/start")
    def api_start():
        return jsonify(runtime.start_run())

    @app.post("/api/run/stop")
    def api_stop():
        runtime.stop_run()
        return jsonify({"ok": True, "message": "Stop requested"})

    @app.post("/api/control/<action>")
    def api_control(action: str):
        try:
            return jsonify(runtime.control(action, request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/card/validate")
    def api_validate_card():
        return jsonify(runtime.validate_card(request.args.get("q", "")))

    @app.post("/api/recognition/run")
    def api_recognition_run():
        upload = request.files.get("image")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "message": "Image upload required"}), 400
        suffix = Path(upload.filename).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
        upload.save(temp_path)
        payload = {
            "mode": request.form.get("mode", "greenfield"),
            "backend": request.form.get("backend") or None,
            "prefer_visual_small_pool": request.form.get("prefer_visual_small_pool") == "true",
            "use_tracked_pool": request.form.get("use_tracked_pool") == "true",
            "track_result": request.form.get("track_result") == "true",
        }
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
        return jsonify(runtime.system_info(refresh_remote=request.args.get("refresh") == "true"))

    @app.post("/api/system/update")
    def api_system_update():
        status_code = 200
        payload = runtime.update_from_remote()
        if not payload.get("ok", False):
            status_code = 409
        return jsonify(payload), status_code

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
        try:
            result = runtime.serial_board.auto_connect() if not port else runtime.serial_board.connect(port, baud_rate)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/disconnect")
    def api_serial_disconnect():
        return jsonify(runtime.serial_board.disconnect())

    @app.post("/api/serial/send")
    def api_serial_send():
        payload = request.get_json(silent=True) or {}
        command = str(payload.get("command", "")).strip()
        try:
            return jsonify(runtime.serial_board.send_command(command))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.get("/api/serial/endstops")
    def api_serial_endstops():
        try:
            return jsonify(runtime.serial_board.read_endstops())
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/heartbeat")
    def api_serial_heartbeat():
        try:
            return jsonify(runtime.serial_board.send_command("M114"))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc), **runtime.serial_board.status()}), 400

    @app.post("/api/serial/bltouch/<action>")
    def api_serial_bltouch(action: str):
        try:
            return jsonify(runtime.serial_board.bltouch(action))
        except Exception as exc:
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


def _format_mm(value: float) -> str:
    return f"{float(value):.3f}"


def _package_version() -> str:
    try:
        return version("card-sorter-testbed")
    except PackageNotFoundError:
        pyproject_path = _repo_root() / "pyproject.toml"
        try:
            with pyproject_path.open("rb") as handle:
                return str(tomllib.load(handle)["project"]["version"])
        except Exception:
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
