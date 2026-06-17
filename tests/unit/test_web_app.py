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
        },
    )
    status = client.get("/api/status").get_json()
    saved = CalibrationProfile.from_file(calibration_path)

    assert response.status_code == 200
    assert status["calibration"]["camera_offset_x_mm"] == 4.5
    assert status["calibration"]["camera_offset_y_mm"] == -2.0
    assert status["calibration"]["camera_offset_z_mm"] == 11.0
    assert status["calibration"]["min_xy_travel_z_mm"] == 3.0
    assert saved.camera_offset_z_mm == 11.0


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


def _pose_coordinates(pose):
    return {key: pose[key] for key in ("x_mm", "y_mm", "z_mm")}
