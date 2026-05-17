from __future__ import annotations

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.web import create_web_app


def _client():
    settings = AppSettings.from_env()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    return app.test_client()


def test_web_pages_render():
    client = _client()
    for path in ("/", "/machine", "/recognition", "/runs", "/about"):
        response = client.get(path)
        assert response.status_code == 200


def test_status_snapshot_and_capabilities_are_available():
    client = _client()
    status = client.get("/api/status").get_json()
    snapshot = client.get("/api/snapshot").get_json()
    capabilities = client.get("/api/capabilities").get_json()

    assert status["lifecycle"] == "IDLE"
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
    settings = AppSettings.from_env()
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
    response = client.get("/machine")
    assert b'class="active" href="/machine"' in response.data
