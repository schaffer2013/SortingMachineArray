from __future__ import annotations

from dataclasses import replace
import re

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.web import app as web_app_module
from sorter.interfaces.web import create_web_app


def _client():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    return app.test_client()


def _sim_truth_settings():
    return replace(AppSettings.from_env(), recognizer_backend="sim_truth")


def test_web_pages_render():
    client = _client()
    for path in ("/", "/movement", "/machine", "/recognition", "/runs", "/system", "/about"):
        response = client.get(path)
        assert response.status_code == 200


def test_status_snapshot_and_capabilities_are_available():
    client = _client()
    status = client.get("/api/status").get_json()
    snapshot = client.get("/api/snapshot").get_json()
    capabilities = client.get("/api/capabilities").get_json()

    assert status["lifecycle"] == "IDLE"
    assert status["machine_initialized"] is False
    assert "pose" in status
    assert snapshot["piles"]
    assert any(item["name"] == "Camera preview" for item in capabilities["capabilities"])


def test_card_validation_uses_local_catalog():
    client = _client()
    response = client.get("/api/card/validate?q=Appeal%20to%20Eirdu")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["valid"] is True
    assert payload["match"]["name"] == "Appeal to Eirdu"


def test_light_profiles_can_be_created_and_applied(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    client = app.test_client()

    create_response = client.post(
        "/api/light-profiles",
        json={"name": "inspection-blue", "red": 1, "green": 2, "blue": 42},
    )
    apply_response = client.post("/api/control/light_profile", json={"name": "inspection-blue"})
    status = client.get("/api/status").get_json()

    assert create_response.status_code == 200
    assert apply_response.status_code == 200
    assert status["lights_profile"] == "inspection-blue"
    assert status["lights_rgb"] == [1, 2, 42]


def test_light_profile_is_sent_to_connected_serial_board(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    client = app.test_client()

    client.post(
        "/api/light-profiles",
        json={"name": "inspection-blue", "red": 1, "green": 2, "blue": 42},
    )
    response = client.post("/api/control/light_profile", json={"name": "inspection-blue"})

    assert response.status_code == 200
    assert runtime.serial_board.rgb_commands == [(1, 2, 42, "inspection-blue")]


def test_serial_api_lists_connects_sends_and_disconnects():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    client = app.test_client()

    ports = client.get("/api/serial/ports?auto=true").get_json()
    connect = client.post("/api/serial/connect", json={"port": "COM8", "baud_rate": 115200}).get_json()
    send = client.post("/api/serial/send", json={"command": "M150 R0 U0 B32"}).get_json()
    endstops = client.get("/api/serial/endstops").get_json()
    bltouch = client.post("/api/serial/bltouch/deploy").get_json()
    disconnect = client.post("/api/serial/disconnect").get_json()

    assert ports["ports"][0]["device"] == "COM8"
    assert connect["connected"] is True
    assert send["response"] == ["ok"]
    assert endstops["endstops"] == {"x_min": "open", "z_max": "triggered"}
    assert bltouch["bltouch_action"] == "deploy"
    assert bltouch["response"] == ["ok"]
    assert disconnect["connected"] is False


def test_connected_serial_board_takes_over_movement_controls():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    client = app.test_client()

    response = client.post("/api/control/jog_xy", json={"dx_mm": 5.0, "dy_mm": 0.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert "G1 X5.000 Y0.000 F600" in runtime.serial_board.sent_commands
    assert status["runtime_target"] == "hardware_serial"
    assert status["pose"]["x_mm"] == 5.0


def test_serial_error_clears_live_connection(monkeypatch):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.fail_next_command = True
    client = app.test_client()

    response = client.post("/api/serial/heartbeat")
    status = client.get("/api/status").get_json()

    assert response.status_code == 400
    assert status["serial_board"]["connected"] is False
    assert status["serial_board"]["session_open"] is False
    assert status["runtime_target"] == "sim"


def test_status_reports_busy_without_waiting_on_serial_lock():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    client = app.test_client()

    assert runtime.serial_board.command_lock.acquire(blocking=False) is True
    try:
        status = client.get("/api/status").get_json()
    finally:
        runtime.serial_board.command_lock.release()

    assert status["serial_board"]["busy"] is True


def test_active_navigation_tab_is_marked():
    client = _client()
    response = client.get("/movement")
    assert b'class="active" href="/movement"' in response.data


def test_movement_jog_controls_update_pose():
    client = _client()

    z_response = client.post("/api/control/jog_z", json={"dz_mm": 2.5})
    xy_response = client.post("/api/control/jog_xy", json={"dx_mm": 4.0, "dy_mm": -3.0})
    status = client.get("/api/status").get_json()

    assert z_response.status_code == 200
    assert xy_response.status_code == 200
    assert status["pose"]["x_mm"] == 4.0
    assert status["pose"]["y_mm"] == -3.0
    assert status["pose"]["z_mm"] == 2.5


def test_c_axis_control_updates_pose():
    client = _client()

    response = client.post("/api/control/move_c", json={"c_mm": 1.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert status["pose"]["c_mm"] == 1.0


def test_paired_zc_interface_jog_keeps_end_effector_height_fixed():
    client = _client()

    client.post("/api/control/move_z", json={"z_mm": 10.0})
    client.post("/api/control/move_c", json={"c_mm": 2.0})
    before = client.get("/api/status").get_json()["pose"]
    response = client.post("/api/control/jog_zc_interface", json={"dz_mm": 3.0})
    after = client.get("/api/status").get_json()["pose"]

    assert response.status_code == 200
    assert after["z_mm"] == 13.0
    assert after["c_mm"] == -1.0
    assert after["z_mm"] + after["c_mm"] == before["z_mm"] + before["c_mm"]


def test_system_api_reports_version_and_update_state():
    client = _client()
    payload = client.get("/api/system").get_json()

    assert re.fullmatch(r"\d+\.\d+\.\d+-[0-9a-f]+", payload["version"])
    assert payload["remote"] == "origin/main"
    assert "update_available" in payload
    assert "can_update" in payload


def test_system_update_refuses_when_not_safe(monkeypatch):
    client = _client()

    def fake_system_info(self, refresh_remote=False):
        return {
            "version": "0.1.0-abc1234",
            "package_version": "0.1.0",
            "current_sha": "abc1234",
            "current_branch": "feature/work",
            "dirty": False,
            "remote": "origin/main",
            "remote_sha": "def5678",
            "commits_behind": 1,
            "commits_ahead": 0,
            "update_available": True,
            "can_update": False,
            "message": "Switch to main before updating from the web UI",
            "restart_required": False,
        }

    monkeypatch.setattr(web_app_module.WebRuntime, "system_info", fake_system_info)

    response = client.post("/api/system/update")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["ok"] is False
    assert payload["message"] == "Switch to main before updating from the web UI"


def test_calibration_can_be_updated_from_web_app(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    calibration_path = tmp_path / "calibration.json"
    app = create_web_app(orchestrator, calibration, calibration_path=calibration_path)
    app.testing = True
    client = app.test_client()

    response = client.post(
        "/api/calibration",
        json={
            "camera_offset_x_mm": 4.5,
            "camera_offset_y_mm": -2.0,
            "camera_offset_z_mm": 11.0,
            "min_xy_travel_z_mm": 3.0,
            "z_home_mm": 245.0,
            "c_home_mm": 41.5,
            "pick_z_mm": 1.25,
            "place_z_mm": 2.5,
            "probe_enabled": True,
            "probe_retract_z_mm": 1.5,
            "probe_place_clearance_mm": 0.75,
            "probe_max_contact_z_mm": 8.0,
        },
    )
    status = client.get("/api/status").get_json()
    saved = CalibrationProfile.from_file(calibration_path)

    assert response.status_code == 200
    assert status["calibration"]["camera_offset_x_mm"] == 4.5
    assert status["calibration"]["camera_offset_y_mm"] == -2.0
    assert status["calibration"]["camera_offset_z_mm"] == 11.0
    assert status["calibration"]["min_xy_travel_z_mm"] == 3.0
    assert status["calibration"]["z_home_mm"] == 245.0
    assert status["calibration"]["c_home_mm"] == 41.5
    assert status["calibration"]["pick_z_mm"] == 1.25
    assert status["calibration"]["place_z_mm"] == 2.5
    assert status["calibration"]["probe_enabled"] is True
    assert status["calibration"]["probe_retract_z_mm"] == 1.5
    assert status["calibration"]["probe_place_clearance_mm"] == 0.75
    assert status["calibration"]["probe_max_contact_z_mm"] == 8.0
    assert saved.camera_offset_z_mm == 11.0
    assert saved.z_home_mm == 245.0
    assert saved.c_home_mm == 41.5
    assert saved.probe_enabled is True
    assert saved.probe_place_clearance_mm == 0.75


def test_web_xy_control_blocks_when_vacuum_z_is_too_low():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(min_xy_travel_z_mm=10.0)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    client = app.test_client()

    response = client.post("/api/control/move_xy", json={"x_mm": 100.0, "y_mm": 50.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 400
    assert "XY travel blocked" in response.get_json()["message"]
    assert status["pose"]["x_mm"] == 0.0
    assert status["pose"]["y_mm"] == 0.0


def test_machine_initialization_is_explicit_web_control():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        safe_z_mm=2.0,
        min_xy_travel_z_mm=5.0,
        c_home_mm=41.5,
    )
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    client = app.test_client()

    initial_status = client.get("/api/status").get_json()
    blocked_start_response = client.post("/api/run/start", json={})
    initialize_response = client.post("/api/control/initialize", json={})
    initialized_status = client.get("/api/status").get_json()

    assert initial_status["machine_initialized"] is False
    assert _pose_coordinates(initial_status["pose"]) == {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}
    assert blocked_start_response.get_json() == {
        "ok": False,
        "message": "Initialize machine before starting a run",
    }
    assert initialize_response.status_code == 200
    assert initialize_response.get_json()["ok"] is True
    assert initialized_status["machine_initialized"] is True
    assert initialized_status["phase"] == "IDLE"
    assert initialized_status["active_command"] is None
    assert _pose_coordinates(initialized_status["pose"]) == {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 5.0}
    assert initialized_status["pose"]["c_mm"] == 41.5


def test_web_home_sets_vertical_axes_to_configured_max():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        z_home_mm=245.0,
        c_home_mm=41.5,
    )
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    client = app.test_client()

    response = client.post("/api/control/home", json={})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert status["pose"]["x_mm"] == 0.0
    assert status["pose"]["y_mm"] == 0.0
    assert status["pose"]["z_mm"] == 245.0
    assert status["pose"]["c_mm"] == 41.5


def _pose_coordinates(pose):
    return {key: pose[key] for key in ("x_mm", "y_mm", "z_mm")}


class FakeSerialBoard:
    def __init__(self):
        self.connected = False
        self.port = None
        self.baud_rate = 115200
        self.last_error = None
        self.last_response = []
        self.last_endstops = {}
        self.live_pose = {}
        self.sent_commands = []
        self.rgb_commands = []
        self.fail_next_command = False
        self.connection_state = "disconnected"

    def status(self):
        return {
            "connected": self.connected,
            "session_open": self.connected,
            "connection_state": self.connection_state,
            "port": self.port,
            "baud_rate": self.baud_rate,
            "last_error": self.last_error,
            "last_response": self.last_response,
            "last_endstops": self.last_endstops,
            "live_pose": self.live_pose,
        }

    def list_ports(self):
        return [{"device": "COM8", "description": "USB Serial Device", "hwid": "USB"}]

    def auto_connect(self):
        return self.connect("COM8", self.baud_rate)

    def connect(self, port, baud_rate=115200):
        self.connected = True
        self.port = port
        self.baud_rate = baud_rate
        self.connection_state = "verified"
        self.last_response = ["FIRMWARE_NAME:test", "ok"]
        return {"ok": True, "message": f"Connected to {port}", **self.status()}

    def disconnect(self):
        self.connected = False
        self.port = None
        self.connection_state = "disconnected"
        return {"ok": True, "message": "Disconnected", **self.status()}

    def send_command(self, command):
        if self.fail_next_command:
            self.fail_next_command = False
            self.connected = False
            self.connection_state = "error"
            raise TimeoutError("serial heartbeat failed")
        self.sent_commands.append(command)
        if command == "M119":
            self.last_response = ["Reporting endstop status", "x_min: open", "z_max: TRIGGERED", "ok"]
        elif command == "M114":
            self.last_response = [
                f"X:{self.live_pose.get('x', 0):.2f} Y:{self.live_pose.get('y', 0):.2f} "
                f"Z:{self.live_pose.get('z', 0):.2f} C:{self.live_pose.get('c', 0):.2f} Count X:400"
            ]
        else:
            self.last_response = ["ok"]
        return {"ok": True, "message": f"Sent {command}", "response": self.last_response, **self.status()}

    def send_commands(self, commands, *, message):
        responses = []
        for command in commands:
            if command.startswith("G1 "):
                for token in command.split():
                    if token.startswith("X"):
                        self.live_pose["x"] = self.live_pose.get("x", 0.0) + float(token[1:])
                    if token.startswith("Y"):
                        self.live_pose["y"] = self.live_pose.get("y", 0.0) + float(token[1:])
                    if token.startswith("Z"):
                        self.live_pose["z"] = self.live_pose.get("z", 0.0) + float(token[1:])
                    if token.startswith("C"):
                        self.live_pose["c"] = self.live_pose.get("c", 0.0) + float(token[1:])
            result = self.send_command(command)
            responses.extend(result["response"])
        return {"ok": True, "message": message, "response": responses, **self.status()}

    def read_endstops(self):
        self.send_command("M119")
        self.last_endstops = {"x_min": "open", "z_max": "triggered"}
        return {"ok": True, "message": "Read endstop states", "endstops": self.last_endstops, **self.status()}

    def bltouch(self, action):
        self.last_response = ["ok"]
        return {
            "ok": True,
            "message": f"Sent {action}",
            "response": self.last_response,
            "bltouch_action": action,
            **self.status(),
        }

    def set_lights_status(self, status):
        self.last_response = [status]

    def set_lights_rgb(self, red, green, blue, *, profile_name=None):
        self.rgb_commands.append((red, green, blue, profile_name))
