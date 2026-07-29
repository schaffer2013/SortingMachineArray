from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import re
import tomllib

import pytest
from PIL import Image, ImageDraw

from sorter.bootstrap import build_sim_orchestrator
from sorter.adapters.hardware.marlin_motion import MarlinMotionAdapter
from sorter.adapters.hardware.marlin_transport import RecordingMarlinTransport
from sorter.application.card_back_detection import detect_card_back, refine_card_back_corners_to_truth
from sorter.application.card_back_training import CardBackTrainingStore
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces import web_runner
from sorter.interfaces.web import app as web_app_module
from sorter.interfaces.web import create_web_app
from sorter.ports.camera import Frame


def _client(runtime_mode: str = "hardware"):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = runtime_mode
    app.testing = True
    return app.test_client()


def _sim_truth_settings():
    return replace(AppSettings.from_env(), recognizer_backend="sim_truth")


def test_web_pages_render():
    client = _client()
    for path in ("/", "/movement", "/machine", "/recognition", "/card-back-training", "/runs", "/system", "/about"):
        response = client.get(path)
        assert response.status_code == 200


def test_card_back_training_defaults_to_local_data():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)

    root = app.config["runtime"].card_back_training.root

    assert root.name == "card_back_training"
    assert root.parent.name == "local_data"


def test_card_back_training_model_plan_capture_and_label(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = "simulation"
    app.config["runtime"].card_back_training = CardBackTrainingStore(tmp_path / "card_back_training")
    app.testing = True
    client = app.test_client()

    created = client.post("/api/card-back-training/models", json={"name": "corner model v1"}).get_json()
    model_id = created["model"]["model_id"]
    plan_response = client.post(
        "/api/card-back-training/plan",
        json={
            "box": {
                "min_x_mm": 80,
                "max_x_mm": 120,
                "min_y_mm": 90,
                "max_y_mm": 130,
                "min_z_mm": 8,
                "max_z_mm": 18,
            },
            "count": 5,
            "seed": 7,
            "light_min": 0,
            "light_max": 80,
        },
    )
    plan = plan_response.get_json()["plan"]
    capture_response = client.post(
        "/api/card-back-training/capture",
        json={
            "model_id": model_id,
            "point": plan[0]["point"],
            "lighting": plan[0]["lighting"],
            "run_detection": False,
            "split": "staged",
        },
    )
    captured = capture_response.get_json()["sample"]
    sample_id = captured["sample_id"]
    label_response = client.patch(
        f"/api/card-back-training/models/{model_id}/samples/{sample_id}",
        json={
            "split": "train",
            "truth_corners_px": {
                "nw": {"x": 10, "y": 12},
                "ne": {"x": 110, "y": 13},
                "se": {"x": 112, "y": 180},
                "sw": {"x": 11, "y": 179},
            },
        },
    )
    summary = client.get("/api/card-back-training").get_json()
    sample_payload_response = client.get(f"/api/card-back-training/models/{model_id}/samples/{sample_id}")
    image_response = client.get(f"/api/card-back-training/models/{model_id}/samples/{sample_id}/image.jpg")

    assert plan_response.status_code == 200
    assert len(plan) == 5
    assert all(80 <= item["point"]["x_mm"] <= 120 for item in plan)
    assert capture_response.status_code == 200
    assert captured["split"] == "staged"
    assert label_response.status_code == 200
    assert label_response.get_json()["sample"]["split"] == "train"
    assert summary["models"][0]["train_count"] == 1
    assert summary["models"][0]["truth_count"] == 1
    assert sample_payload_response.status_code == 200
    assert sample_payload_response.get_json()["sample"]["label"]["truth_corners_px"]["nw"] == [10.0, 12.0]
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/jpeg"


def test_card_back_training_delete_sample_and_model(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].card_back_training = CardBackTrainingStore(tmp_path / "card_back_training")
    app.testing = True
    client = app.test_client()

    created = client.post("/api/card-back-training/models", json={"name": "delete me"}).get_json()
    model_id = created["model"]["model_id"]
    capture_response = client.post(
        "/api/card-back-training/capture",
        json={"model_id": model_id, "run_detection": False, "split": "staged"},
    )
    sample_id = capture_response.get_json()["sample"]["sample_id"]

    delete_sample = client.delete(f"/api/card-back-training/models/{model_id}/samples/{sample_id}")
    missing_sample = client.get(f"/api/card-back-training/models/{model_id}/samples/{sample_id}")
    delete_model = client.delete(f"/api/card-back-training/models/{model_id}")
    summary = client.get("/api/card-back-training").get_json()

    assert delete_sample.status_code == 200
    assert delete_sample.get_json()["deleted_sample_id"] == sample_id
    assert missing_sample.status_code == 404
    assert delete_model.status_code == 200
    assert delete_model.get_json()["deleted_model_id"] == model_id
    assert summary["models"] == []


def test_card_back_training_capture_confirms_generated_camera_z_move(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        camera_offset_x_mm=10.0,
        camera_offset_y_mm=15.0,
        camera_offset_z_mm=5.0,
    )
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].card_back_training = CardBackTrainingStore(tmp_path / "card_back_training")
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["x"] = 79.502
    runtime.serial_board.live_pose["y"] = 69.503
    runtime.serial_board.live_pose["z"] = 150.0
    client = app.test_client()

    created = client.post("/api/card-back-training/models", json={"name": "live z capture"}).get_json()
    response = client.post(
        "/api/card-back-training/capture",
        json={
            "model_id": created["model"]["model_id"],
            "execute_motion": True,
            "run_detection": False,
            "point": {"x_mm": 89.502, "y_mm": 84.503, "z_mm": 149.51},
            "lighting": {"mode": "random_pixels", "pixels": [[0, 0, 0] for _ in range(16)]},
        },
    )

    assert response.status_code == 200
    assert "G1 X79.502 Y69.503 Z144.510 F1800" in runtime.serial_board.sent_commands
    assert "G1 X79.502 Y69.503 Z144.510 F6000" not in runtime.serial_board.sent_commands
    assert runtime.serial_board.live_pose["z"] == 144.51


def test_card_back_training_capture_waits_after_motion_before_image(tmp_path, monkeypatch):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        camera_offset_x_mm=10.0,
        camera_offset_y_mm=15.0,
        camera_offset_z_mm=5.0,
    )
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].card_back_training = CardBackTrainingStore(tmp_path / "card_back_training")
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    sleeps = []
    monkeypatch.setattr(web_app_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = app.test_client()

    created = client.post("/api/card-back-training/models", json={"name": "settle capture"}).get_json()
    response = client.post(
        "/api/card-back-training/capture",
        json={
            "model_id": created["model"]["model_id"],
            "execute_motion": True,
            "run_detection": False,
            "settle_ms": 150,
            "point": {"x_mm": 89.502, "y_mm": 84.503, "z_mm": 149.51},
        },
    )

    assert response.status_code == 200
    assert sleeps[:2] == [1.0, 0.15]


def test_card_back_detect_endpoint_supports_opencv_method(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    image_path = tmp_path / "card-back.jpg"
    image = Image.new("RGB", (900, 650), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((220, 80, 620, 640), fill="#3b2418")
    draw.rectangle((245, 110, 595, 610), fill="#9b6239")
    draw.ellipse((295, 145, 545, 545), outline="#53348a", width=10, fill="#d08a54")
    image.save(image_path)
    orchestrator.camera = StaticImageCamera(image_path)
    client = app.test_client()

    response = client.post("/api/card-back/detect", json={"detection_method": "opencv"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["found"] is True
    assert payload["detection_method"] == "opencv"
    assert "corner_refinement" not in payload


def test_status_snapshot_and_capabilities_are_available():
    client = _client()
    status = client.get("/api/status").get_json()
    snapshot = client.get("/api/snapshot").get_json()
    capabilities = client.get("/api/capabilities").get_json()

    assert status["lifecycle"] == "IDLE"
    assert status["runtime_mode"] == "hardware"
    assert status["runtime_target"] == "hardware_unavailable"
    assert status["machine_initialized"] is False
    assert "pose" in status
    assert snapshot["piles"]
    assert any(item["name"] == "Camera preview" for item in capabilities["capabilities"])


def test_saved_positions_crud_persists_to_local_json(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, runtime_mode="simulation")
    app.testing = True
    app.config["runtime"].saved_positions_path = tmp_path / "saved_positions.json"
    client = app.test_client()

    created = client.post(
        "/api/saved-positions",
        json={"name": "Input stack", "x_mm": 12.3456, "y_mm": 23.4567, "z_mm": 34.5678},
    )

    assert created.status_code == 200
    position = created.get_json()["position"]
    assert position["name"] == "Input stack"
    assert position["x_mm"] == 12.346
    assert json.loads((tmp_path / "saved_positions.json").read_text(encoding="utf-8"))["positions"][0]["id"] == position["id"]

    updated = client.patch(
        f"/api/saved-positions/{position['id']}",
        json={"name": "Camera check", "x_mm": 40, "y_mm": 41, "z_mm": 42},
    )
    listed = client.get("/api/saved-positions")

    assert updated.status_code == 200
    assert listed.get_json()["positions"] == updated.get_json()["positions"]
    assert listed.get_json()["positions"][0]["name"] == "Camera check"

    deleted = client.delete(f"/api/saved-positions/{position['id']}")

    assert deleted.status_code == 200
    assert client.get("/api/saved-positions").get_json()["positions"] == []


def test_saved_position_go_requires_all_axes_homed(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, runtime_mode="simulation")
    app.testing = True
    app.config["runtime"].saved_positions_path = tmp_path / "saved_positions.json"
    client = app.test_client()
    position = client.post(
        "/api/saved-positions",
        json={"name": "Blocked", "x_mm": 10, "y_mm": 20, "z_mm": 30},
    ).get_json()["position"]

    response = client.post(f"/api/saved-positions/{position['id']}/go", json={"coordinate_space": "vacuum"})

    assert response.status_code == 400
    assert response.get_json()["message"] == "Home all axes before going to a saved XYZ position"


def test_saved_position_go_supports_vacuum_and_camera_coordinates(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        camera_offset_x_mm=10.0,
        camera_offset_y_mm=15.0,
        camera_offset_z_mm=5.0,
    )
    app = create_web_app(orchestrator, calibration, runtime_mode="simulation")
    app.testing = True
    app.config["runtime"].saved_positions_path = tmp_path / "saved_positions.json"
    client = app.test_client()
    position = client.post(
        "/api/saved-positions",
        json={"name": "Dual coordinate", "x_mm": 80, "y_mm": 90, "z_mm": 100},
    ).get_json()["position"]

    client.post("/api/control/home")
    vacuum = client.post(f"/api/saved-positions/{position['id']}/go", json={"coordinate_space": "vacuum"})
    vacuum_pose = client.get("/api/status").get_json()["pose"]
    camera = client.post(f"/api/saved-positions/{position['id']}/go", json={"coordinate_space": "camera"})
    camera_pose = client.get("/api/status").get_json()["pose"]

    assert vacuum.status_code == 200
    assert vacuum.get_json()["coordinate_space"] == "vacuum"
    assert vacuum_pose["x_mm"] == pytest.approx(80.0)
    assert vacuum_pose["y_mm"] == pytest.approx(90.0)
    assert vacuum_pose["z_mm"] == pytest.approx(100.0)
    assert camera.status_code == 200
    assert camera.get_json()["coordinate_space"] == "camera"
    assert camera_pose["x_mm"] == pytest.approx(70.0)
    assert camera_pose["y_mm"] == pytest.approx(75.0)
    assert camera_pose["z_mm"] == pytest.approx(95.0)


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
    app.config["runtime"].runtime_mode = "simulation"
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


def test_light_profiles_seed_from_tracked_config_and_save_to_local_data(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    seed_path = tmp_path / "config" / "light_profiles.json"
    local_path = tmp_path / "local_data" / "light_profiles.json"
    seed_path.parent.mkdir(parents=True)
    seed_path.write_text(
        json.dumps({"profiles": [{"name": "seeded", "red": 1, "green": 2, "blue": 3}]}),
        encoding="utf-8",
    )
    app = create_web_app(
        orchestrator,
        calibration,
        light_profiles_path=local_path,
        light_profiles_seed_path=seed_path,
    )
    app.config["runtime"].runtime_mode = "simulation"
    app.testing = True
    client = app.test_client()

    seeded = client.get("/api/light-profiles").get_json()["profiles"]
    created = client.post(
        "/api/light-profiles",
        json={"name": "local", "red": 4, "green": 5, "blue": 6},
    )
    saved = json.loads(local_path.read_text(encoding="utf-8"))

    assert created.status_code == 200
    assert any(profile["name"] == "seeded" for profile in seeded)
    assert local_path.exists()
    assert {profile["name"] for profile in saved["profiles"]} == {"seeded", "local"}


def test_web_runner_prefers_local_calibration_and_writes_local_path(tmp_path):
    settings = _sim_truth_settings()
    base = CalibrationProfile.from_file(settings.calibration_path).to_json_dict()
    tracked_path = tmp_path / "config" / "calibration.json"
    local_path = tmp_path / "local_data" / "calibration.json"
    tracked_path.parent.mkdir(parents=True)
    local_path.parent.mkdir(parents=True)
    tracked_path.write_text(json.dumps({**base, "camera_offset_z_mm": 1.0}), encoding="utf-8")
    local_path.write_text(json.dumps({**base, "camera_offset_z_mm": 9.0}), encoding="utf-8")
    local_settings = replace(settings, calibration_path=tracked_path)

    calibration, writable_path = web_runner._load_calibration(tmp_path, local_settings)

    assert calibration.camera_offset_z_mm == 9.0
    assert writable_path == local_path


def test_light_profile_is_sent_to_connected_serial_board(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    client = app.test_client()

    client.post(
        "/api/light-profiles",
        json={"name": "inspection-blue", "red": 1, "green": 2, "blue": 42},
    )
    response = client.post("/api/control/light_profile", json={"name": "inspection-blue"})

    assert response.status_code == 200
    assert runtime.serial_board.rgb_commands == [(1, 2, 42, "inspection-blue")]


def test_lighting_optimizer_sweeps_camera_frames_and_applies_best(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = "simulation"
    app.testing = True
    orchestrator.camera = BrightnessCamera(orchestrator.lights, tmp_path)
    client = app.test_client()

    response = client.post(
        "/api/lights/optimize",
        json={"max_samples": 6, "settle_ms": 0, "target_brightness": 96},
    )
    payload = response.get_json()
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert payload["best"]["red"] == 96
    assert payload["best"]["green"] == 96
    assert payload["best"]["blue"] == 96
    assert len(payload["samples"]) == 6
    assert status["lights_profile"] == "optimized"
    assert status["lights_rgb"] == [96, 96, 96]


def test_lighting_optimizer_scores_requested_crop(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = "simulation"
    app.testing = True
    orchestrator.camera = SplitBrightnessCamera(orchestrator.lights, tmp_path)
    client = app.test_client()

    response = client.post(
        "/api/lights/optimize",
        json={
            "max_samples": 6,
            "settle_ms": 0,
            "target_brightness": 96,
            "crop": {"left": 0, "top": 0, "right": 50, "bottom": 100},
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["best"]["red"] == 96
    assert payload["crop"] == {"left": 0.0, "top": 0.0, "right": 0.5, "bottom": 1.0}


def test_lighting_optimizer_can_select_single_led(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    orchestrator.camera = SingleLedCamera(orchestrator.lights, tmp_path, preferred_led=2)
    client = app.test_client()

    response = client.post(
        "/api/lights/optimize",
        json={
            "mode": "single_led",
            "max_samples": 4,
            "settle_ms": 0,
            "target_brightness": 96,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["mode"] == "single_led"
    assert payload["best"]["led_index"] == 2
    assert payload["best"]["pixels"][2] == [96, 96, 96]
    assert sum(1 for pixel in payload["best"]["pixels"] if any(pixel)) == 1
    assert runtime.serial_board.pixel_displays[-1] == payload["best"]["pixels"]


def test_lighting_score_penalizes_glare():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    runtime = app.config["runtime"]

    balanced = Image.new("RGB", (40, 40), (96, 96, 96))
    glare = Image.new("RGB", (40, 40), (96, 96, 96))
    for x in range(20, 40):
        for y in range(40):
            glare.putpixel((x, y), (255, 245, 245))

    balanced_score = runtime._score_lighting_frame(balanced, target_brightness=96)
    glare_score = runtime._score_lighting_frame(glare, target_brightness=96)

    assert glare_score["glare_fraction"] > balanced_score["glare_fraction"]
    assert glare_score["score"] < balanced_score["score"]


def test_card_back_detector_finds_synthetic_card_back():
    image = Image.new("RGB", (900, 650), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((220, 80, 620, 640), fill="#3b2418")
    draw.rectangle((245, 110, 595, 610), fill="#9b6239")
    draw.ellipse((295, 145, 545, 545), outline="#53348a", width=10, fill="#d08a54")
    draw.text((310, 180), "MAGIC", fill="#ced9e8")
    draw.rectangle((330, 510, 510, 548), fill="#f5f0df")

    detection = detect_card_back(image)

    assert detection.found is True
    assert detection.confidence > 0.55
    assert detection.center_px is not None
    assert detection.component_bbox_px is not None
    assert detection.estimated_card_bbox_px is not None
    assert detection.estimated_card_bbox_px[0] < detection.component_bbox_px[0]
    assert 350 <= detection.center_px[0] <= 500
    assert 300 <= detection.center_px[1] <= 430


def test_card_back_corner_refinement_improves_truth_alignment():
    import cv2
    import numpy as np

    truth_path = (
        Path(__file__).parents[2]
        / "src"
        / "sorter"
        / "interfaces"
        / "web"
        / "static"
        / "card-back-truth.jpg"
    )
    truth = Image.open(truth_path).convert("RGB").resize((630, 880))
    canvas = Image.new("RGB", (1100, 1300), "#111827")
    source = np.array(
        [
            [0.0, 0.0],
            [629.0, 0.0],
            [629.0, 879.0],
            [0.0, 879.0],
        ],
        dtype="float32",
    )
    actual_corners = ((260.0, 170.0), (880.0, 205.0), (835.0, 1085.0), (220.0, 1030.0))
    destination = np.array(actual_corners, dtype="float32")
    matrix = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(np.array(truth), matrix, canvas.size)
    mask = cv2.warpPerspective(np.full((880, 630), 255, dtype="uint8"), matrix, canvas.size)
    frame = np.array(canvas)
    frame[mask > 0] = warped[mask > 0]
    camera_image = Image.fromarray(frame)
    loose_corners = ((244.0, 184.0), (865.0, 188.0), (856.0, 1066.0), (238.0, 1047.0))

    refined_corners, metrics = refine_card_back_corners_to_truth(camera_image, loose_corners, truth)

    assert metrics["applied"] is True
    assert metrics["method"] == "bounded_card_back_feature_search"
    assert metrics["refined_score"] > metrics["initial_score"]
    assert metrics["final_circle_fit"]["truth_circle_count"] == 5
    assert metrics["final_circle_fit"]["detected_circle_count"] == 5
    initial_center_error = metrics["initial_circle_fit"]["mean_center_error_px"]
    final_center_error = metrics["final_circle_fit"]["mean_center_error_px"]
    assert final_center_error is not None
    assert initial_center_error is None or final_center_error < initial_center_error
    assert metrics["final_feature_fit"]["oval"]["score"] > 0
    assert metrics["final_feature_fit"]["corner_orbs"]["truth_orb_count"] == 4
    assert metrics["final_feature_fit"]["corner_orbs"]["mean_center_error_px"] < 5
    assert metrics["corner_orb_seed"]["matched_orb_count"] >= 3
    assert metrics["max_corner_adjust_px"] > 0
    for refined, actual in zip(refined_corners, actual_corners):
        assert abs(refined[0] - actual[0]) < 30
        assert abs(refined[1] - actual[1]) < 30


def test_card_back_detect_endpoint_uses_camera_without_motion(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.runtime_mode = "hardware"
    runtime.hardware_runtime = True
    image_path = tmp_path / "card-back.jpg"
    image = Image.new("RGB", (900, 650), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((220, 80, 620, 640), fill="#3b2418")
    draw.rectangle((245, 110, 595, 610), fill="#9b6239")
    draw.ellipse((295, 145, 545, 545), outline="#53348a", width=10, fill="#d08a54")
    image.save(image_path)
    orchestrator.camera = StaticImageCamera(image_path)
    transport = RecordingMarlinTransport()
    orchestrator.motion = MarlinMotionAdapter(transport=transport)
    client = app.test_client()

    response = client.post("/api/card-back/detect", json={})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["found"] is True
    assert payload["warped_image_data_url"].startswith("data:image/jpeg;base64,")
    assert payload["warped_image_size"] == [630, 880]
    assert payload["initial_corners_px"]
    assert payload["corner_refinement"]["method"] == "bounded_card_back_feature_search"
    assert transport.command_log == []
    assert runtime.last_card_back_detection["found"] is True
    assert "warped_image_data_url" not in runtime.last_card_back_detection


def test_camera_page_has_card_back_truth_overlay_controls():
    client = _client()

    response = client.get("/camera")

    assert response.status_code == 200
    assert b'id="camera-card-detect"' in response.data
    assert b'id="camera-card-truth-toggle"' in response.data
    assert b'id="camera-card-truth-overlay"' in response.data
    assert b"/static/card-back-truth.jpg" in response.data


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


def test_serial_session_records_recent_command_log():
    session = web_app_module.SerialBoardSession()
    session.transport = RecordingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    first = session.send_command("M119")
    second = session.send_command("M114")

    log = second["serial_command_log"]
    assert first["serial_command_log"][0]["command"] == "M119"
    assert log[-2]["command"] == "M119"
    assert log[-2]["response"] == ["M119 response", "ok"]
    assert log[-2]["ok"] is True
    assert log[-2]["sent_at"].endswith("Z")
    assert log[-1]["command"] == "M114"
    assert log[-1]["response"] == ["M114 response", "ok"]


def test_serial_session_adopts_shared_transport_without_owning_it():
    shared_transport = RecordingTransport(serial_port="COM8")
    session = web_app_module.SerialBoardSession(shared_transport=shared_transport)

    connect = session.connect("COM8", 115200)
    disconnect = session.disconnect()

    assert connect["ok"] is True
    assert shared_transport.commands == ["M115"]
    assert disconnect["ok"] is True
    assert shared_transport.closed is False


def test_serial_session_persists_and_reloads_command_log(tmp_path):
    log_path = tmp_path / "serial_commands.jsonl"
    first_session = web_app_module.SerialBoardSession(serial_log_path=log_path)
    first_session.transport = RecordingTransport()
    first_session.port = "COM8"
    first_session.connection_state = "verified"
    first_session.last_success_monotonic = web_app_module.time.monotonic()

    first_session.send_command("G1 Z9.000 F300")
    restored_session = web_app_module.SerialBoardSession(serial_log_path=log_path)
    status = restored_session.status()
    saved_entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert saved_entries[-1]["kind"] == "command"
    assert saved_entries[-1]["command"] == "G1 Z9.000 F300"
    assert status["serial_command_log"][-1]["command"] == "G1 Z9.000 F300"
    assert status["serial_command_log"][-1]["response"] == ["G1 Z9.000 F300 response", "ok"]


def test_serial_session_records_status_polls_separately():
    session = web_app_module.SerialBoardSession()
    session.transport = RecordingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    session.send_command("M119")
    session.read_endstops()
    session.send_status_poll("M114")

    status = session.status()
    command_log = status["serial_command_log"]
    poll_log = status["serial_poll_log"]
    assert [entry["command"] for entry in command_log] == ["M119"]
    assert [entry["command"] for entry in poll_log] == ["M119", "M114"]


def test_serial_session_skips_automatic_polls_when_busy():
    session = web_app_module.SerialBoardSession()
    session.transport = RecordingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()
    session.last_endstops = {"x_min": "open"}

    session.command_lock.acquire()
    try:
        status_poll = session.send_status_poll("M114")
        endstop_poll = session.read_endstops(poll=True)
    finally:
        session.command_lock.release()

    assert status_poll["ok"] is False
    assert status_poll["message"] == "Skipped status poll; serial board is busy"
    assert endstop_poll["ok"] is False
    assert endstop_poll["message"] == "Skipped endstop poll; serial board is busy"
    assert endstop_poll["endstops"] == {"x_min": "open"}
    assert session.status()["serial_poll_log"] == []


def test_serial_session_reports_connection_transition_without_open_session():
    session = web_app_module.SerialBoardSession()
    session.port = "COM8"
    session.connection_state = "connecting"

    status = session.status()

    assert status["connected"] is False
    assert status["session_open"] is False
    assert status["connection_state"] == "connecting"
    assert status["port"] == "COM8"


def test_serial_session_disconnect_is_idempotent():
    session = web_app_module.SerialBoardSession()

    result = session.disconnect()

    assert result["ok"] is True
    assert result["message"] == "Already disconnected"
    assert result["connection_state"] == "disconnected"


def test_serial_session_marks_marlin_kill_as_controller_fault():
    session = web_app_module.SerialBoardSession()
    session.transport = FaultingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    with pytest.raises(RuntimeError, match="Printer halted"):
        session.send_command("G28 Y")

    status = session.status()
    log = status["serial_command_log"][-1]
    assert status["controller_fault"] is True
    assert status["connection_state"] == "faulted"
    assert status["session_open"] is False
    assert log["command"] == "G28 Y"
    assert log["response"] == ["Error:Printer halted. kill() called!"]
    assert log["error"] == "Marlin rejected 'G28 Y': Error:Printer halted. kill() called!"


def test_serial_session_marks_marlin_stopped_response_as_controller_fault():
    session = web_app_module.SerialBoardSession()
    session.transport = StoppedResponseTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    with pytest.raises(RuntimeError, match="Printer stopped"):
        session.send_command("G1 Z161.490 F300")

    status = session.status()
    log = status["serial_command_log"][-1]
    assert status["controller_fault"] is True
    assert status["connection_state"] == "faulted"
    assert status["session_open"] is True
    assert log["ok"] is False
    assert log["command"] == "G1 Z161.490 F300"
    assert log["error"] == "Printer stopped due to errors. Fix the error and use M999 to restart."


def test_serial_session_keeps_last_500_lines_per_log():
    session = web_app_module.SerialBoardSession()
    session.transport = RecordingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    for index in range(505):
        session.send_command(f"M118 E1 test-{index}")
        session.send_status_poll("M114")

    status = session.status()
    command_log = status["serial_command_log"]
    poll_log = status["serial_poll_log"]
    assert len(command_log) == 500
    assert command_log[0]["command"] == "M118 E1 test-5"
    assert command_log[-1]["command"] == "M118 E1 test-504"
    assert len(poll_log) == 500
    assert all(entry["command"] == "M114" for entry in poll_log)


def test_runtime_mode_defaults_to_hardware_and_can_select_simulation():
    client = _client()

    initial = client.get("/api/runtime").get_json()
    update = client.post("/api/runtime", json={"mode": "simulation"}).get_json()

    assert initial["runtime_mode"] == "hardware"
    assert initial["status"]["runtime_target"] == "hardware_unavailable"
    assert update["runtime_mode"] == "simulation"
    assert update["status"]["runtime_target"] == "simulation"


def test_hardware_controls_do_not_fall_back_to_sim_when_disconnected():
    client = _client()

    response = client.post("/api/control/jog_xy", json={"dx_mm": 5.0, "dy_mm": 0.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 400
    assert "serial board is not verified live" in response.get_json()["message"]
    assert status["pose"]["x_mm"] == 0.0
    assert status["runtime_target"] == "hardware_unavailable"


def test_explicit_simulation_runtime_enables_sim_controls():
    client = _client()

    client.post("/api/runtime", json={"mode": "simulation"})
    response = client.post("/api/control/jog_xy", json={"dx_mm": 5.0, "dy_mm": 0.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert status["runtime_target"] == "simulation"
    assert status["pose"]["x_mm"] == 5.0


def test_hardware_panels_are_grouped_by_domain():
    client = _client()

    machine = client.get("/machine")
    recognition = client.get("/recognition")
    movement = client.get("/movement")
    system = client.get("/system")

    assert b'id="pixel-grid"' in machine.data
    assert b"16-LED ring editor" in machine.data
    assert b'id="lighting-opt-mode"' in machine.data
    assert b'value="24"' in machine.data
    assert b'value="95"' in machine.data
    assert b'name="backend"' in recognition.data
    assert b'<option value="fuzzy_enigma"' in recognition.data
    assert b'<option value="visual_retrieval"' in recognition.data
    assert b'<option value="moss_machine"' in recognition.data
    assert b'<option value="sim_truth"' in recognition.data
    assert b'name="moss_threshold" type="number" min="1" max="80" step="1" value="80"' in recognition.data
    assert b'id="recognition-crop-overlay"' in recognition.data
    assert b'id="recognition-crop-preview"' in recognition.data
    assert b'id="recognition-crop-reset"' in recognition.data
    assert b'id="recognition-summary"' in recognition.data
    assert b'id="endstop-state"' in movement.data
    assert b'id="bltouch-probe"' in movement.data
    assert b'data-control="home_x"' in movement.data
    assert b'data-control="home_c"' in movement.data
    assert b'id="serial-command-form"' in system.data
    assert b'id="runtime-mode"' in system.data
    assert b'id="theme-mode"' in system.data
    assert b'id="submodule-list"' in system.data
    assert b'id="collection-details"' in system.data
    assert b'id="collection-open"' in system.data
    assert b'id="endstop-state"' not in system.data
    assert b'id="bltouch-probe"' not in system.data


def test_expected_card_mode_alias_maps_to_reevaluation():
    assert web_app_module._normalize_web_recognition_mode("expected_card") == "reevaluation"
    assert web_app_module._normalize_web_recognition_mode("expected-card") == "reevaluation"
    assert web_app_module._normalize_web_recognition_mode("confirmation") == "confirmation"


def test_neopixel_pixel_display_requires_hardware_and_sends_all_pixels():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    client = app.test_client()
    pixels = [[index, index + 1, index + 2] for index in range(16)]

    response = client.post("/api/neopixel/display", json={"pixels": pixels})

    assert response.status_code == 200
    assert runtime.serial_board.pixel_displays == [pixels]
    assert runtime.serial_board.sent_commands[0] == "M150 I0 R0 U1 B2"
    assert runtime.serial_board.sent_commands[-1] == "M150 I15 R15 U16 B17"


def test_neopixel_pixel_display_rejects_without_live_hardware():
    client = _client()
    pixels = [[0, 0, 0] for _ in range(16)]

    response = client.post("/api/neopixel/display", json={"pixels": pixels})

    assert response.status_code == 400
    assert "serial board is not verified live" in response.get_json()["message"]


def test_neopixel_pixel_profiles_can_be_saved_and_listed(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    client = app.test_client()
    pixels = [[index, index + 1, index + 2] for index in range(16)]

    solid_response = client.post(
        "/api/light-profiles",
        json={"name": "solid-blue", "red": 0, "green": 0, "blue": 32},
    )
    pixel_response = client.post(
        "/api/neopixel/profiles",
        json={"name": "chase", "pixels": pixels},
    )
    solid_profiles = client.get("/api/light-profiles").get_json()["profiles"]
    pixel_profiles = client.get("/api/neopixel/profiles").get_json()["profiles"]

    assert solid_response.status_code == 200
    assert pixel_response.status_code == 200
    assert any(profile["name"] == "solid-blue" for profile in solid_profiles)
    assert pixel_profiles == [{"name": "chase", "pixels": pixels}]


def test_neopixel_profile_options_include_solid_and_pixel_profiles(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    client = app.test_client()
    pixels = [[index, index + 1, index + 2] for index in range(16)]

    client.post("/api/light-profiles", json={"name": "fault", "red": 16, "green": 0, "blue": 0})
    client.post("/api/neopixel/profiles", json={"name": "mich", "pixels": pixels})

    profiles = client.get("/api/neopixel/profile-options").get_json()["profiles"]

    fault = next(profile for profile in profiles if profile["name"] == "fault")
    mich = next(profile for profile in profiles if profile["name"] == "mich")
    assert fault["kind"] == "solid"
    assert fault["pixels"] == [[16, 0, 0] for _ in range(16)]
    assert mich == {"name": "mich", "kind": "pixel", "pixels": pixels}


def test_neopixel_profiles_can_be_deleted_by_kind(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration, light_profiles_path=tmp_path / "light_profiles.json")
    app.testing = True
    client = app.test_client()
    pixels = [[index, index + 1, index + 2] for index in range(16)]

    client.post("/api/light-profiles", json={"name": "fault", "red": 16, "green": 0, "blue": 0})
    client.post("/api/neopixel/profiles", json={"name": "mich", "pixels": pixels})
    solid_delete = client.delete("/api/neopixel/profiles", json={"kind": "solid", "name": "fault"})
    pixel_delete = client.delete("/api/neopixel/profiles", json={"kind": "pixel", "name": "mich"})

    profiles = client.get("/api/neopixel/profile-options").get_json()["profiles"]

    assert solid_delete.status_code == 200
    assert pixel_delete.status_code == 200
    assert all(profile["name"] not in {"fault", "mich"} for profile in profiles)


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


def test_connected_serial_board_takes_over_direct_hardware_movement_controls():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    setattr(orchestrator, "hardware_runtime", True)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    client = app.test_client()

    response = client.post("/api/control/move_xy", json={"x_mm": 100.0, "y_mm": 50.0})

    assert response.status_code == 200
    assert "G1 X100.000 Y50.000 F6000" in runtime.serial_board.sent_commands


def test_camera_space_z_move_applies_camera_offset_in_simulation():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(camera_offset_z_mm=5.0)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = "simulation"
    app.testing = True
    client = app.test_client()

    response = client.post("/api/control/move_z", json={"z_mm": 12.0, "coordinate_space": "camera"})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert status["pose"]["z_mm"] == 7.0
    assert "camera Z" in response.get_json()["message"]


def test_camera_space_z_move_applies_camera_offset_for_live_serial():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(camera_offset_z_mm=5.0)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["z"] = 7.0
    client = app.test_client()

    response = client.post("/api/control/move_z", json={"z_mm": 12.0, "coordinate_space": "camera"})

    assert response.status_code == 200
    assert "G1 Z7.000 F1200" in runtime.serial_board.sent_commands
    assert "camera Z" in response.get_json()["message"]


def test_live_serial_move_vacuum_xy_includes_requested_vacuum_z():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["x"] = 100.0
    runtime.serial_board.live_pose["y"] = 50.0
    runtime.serial_board.live_pose["z"] = 10.0
    client = app.test_client()

    response = client.post("/api/control/move_xy", json={"x_mm": 100.0, "y_mm": 50.0, "z_mm": 12.0})

    assert response.status_code == 200
    assert "G1 X100.000 Y50.000 Z12.000 F1800" in runtime.serial_board.sent_commands
    assert "G1 X100.000 Y50.000 Z12.000 F6000" not in runtime.serial_board.sent_commands
    assert runtime.serial_board.live_pose["z"] == 12.0


def test_live_serial_move_camera_xy_includes_camera_space_z_offset():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(
        camera_offset_x_mm=10.0,
        camera_offset_y_mm=15.0,
        camera_offset_z_mm=5.0,
    )
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose.update({"x": 90.0, "y": 35.0, "z": 5.0})
    client = app.test_client()

    response = client.post(
        "/api/control/move_camera_xy",
        json={"x_mm": 100.0, "y_mm": 50.0, "z_mm": 12.0, "coordinate_space": "camera"},
    )

    assert response.status_code == 200
    assert "G1 X90.000 Y35.000 Z7.000 F1800" in runtime.serial_board.sent_commands
    assert "G1 X90.000 Y35.000 Z7.000 F6000" not in runtime.serial_board.sent_commands
    assert runtime.serial_board.live_pose["z"] == 7.0


def test_live_serial_xyz_feedrate_caps_z_component_with_tunable_limit():
    feedrate = web_app_module._live_xyz_feedrate_mm_per_min(
        current_x_mm=0.0,
        current_y_mm=0.0,
        current_z_mm=0.0,
        target_x_mm=3.0,
        target_y_mm=4.0,
        target_z_mm=5.0,
    )

    assert web_app_module.MAX_SERIAL_COMBINED_Z_SPEED_MM_PER_S == 30.0
    assert feedrate == pytest.approx((30.0 * 60.0) * ((3.0**2 + 4.0**2 + 5.0**2) ** 0.5) / 5.0)


def test_live_serial_z_jog_uses_absolute_target_not_relative_mode():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["z"] = 10.0
    client = app.test_client()

    response = client.post("/api/control/jog_z", json={"dz_mm": -1.0})

    assert response.status_code == 200
    assert "G91" not in runtime.serial_board.sent_commands
    assert runtime.serial_board.sent_commands[-3:] == ["G1 Z9.000 F300", "M400", "M114"]
    assert runtime.serial_board.live_pose["z"] == 9.0


def test_live_serial_unknown_position_jog_uses_limited_relative_move():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["x"] = 0.0
    runtime.serial_board.live_pose["y"] = 0.0
    client = app.test_client()

    response = client.post("/api/control/jog_z", json={"dz_mm": -1.0})
    max_allowed = client.post("/api/control/jog_z", json={"dz_mm": -5.0})
    too_large = client.post("/api/control/jog_z", json={"dz_mm": -6.0})

    assert response.status_code == 200
    assert runtime.serial_board.sent_commands[:5] == ["G91", "G1 Z-1.000 F300", "M400", "G90", "M114"]
    assert max_allowed.status_code == 200
    assert too_large.status_code == 400
    assert "exceeds 5.00 mm" in too_large.get_json()["message"]


def test_live_serial_homed_z_allows_large_jog():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["z"] = 100.0
    client = app.test_client()

    home = client.post("/api/control/home_z", json={})
    jog = client.post("/api/control/jog_z", json={"dz_mm": -10.0})

    assert home.status_code == 200
    assert jog.status_code == 200
    assert "G1 Z90.000 F300" in runtime.serial_board.sent_commands


def test_live_serial_large_absolute_z_move_is_refused_without_confirmation():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    runtime.serial_board.live_pose["z"] = 100.0
    client = app.test_client()

    refused = client.post("/api/control/move_z", json={"z_mm": 1.0})
    confirmed = client.post("/api/control/move_z", json={"z_mm": 1.0, "confirm_large_move": True})

    assert refused.status_code == 400
    assert "Refusing Z absolute move" in refused.get_json()["message"]
    assert confirmed.status_code == 200
    assert "G1 Z1.000 F1200" in runtime.serial_board.sent_commands


def test_direct_hardware_z_jog_sends_relative_move_without_known_position():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    transport = RecordingMarlinTransport()
    orchestrator.motion = MarlinMotionAdapter(transport=transport)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.runtime_mode = "hardware"
    runtime.hardware_runtime = True
    client = app.test_client()

    response = client.post("/api/control/jog_z", json={"dz_mm": -1.0})

    assert response.status_code == 200
    assert transport.command_log == ["G91", "G1 Z-1.000 F300", "M400", "G90"]


def test_direct_hardware_camera_space_z_move_applies_camera_offset():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    transport = RecordingMarlinTransport()
    orchestrator.motion = MarlinMotionAdapter(transport=transport)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(camera_offset_z_mm=5.0)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.runtime_mode = "hardware"
    runtime.hardware_runtime = True
    client = app.test_client()

    response = client.post("/api/control/move_z", json={"z_mm": 12.0, "coordinate_space": "camera"})

    assert response.status_code == 200
    assert transport.command_log == ["G90", "G1 Z7.000 F1200"]
    assert "camera Z" in response.get_json()["message"]


def test_direct_hardware_homed_z_allows_large_jog():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    transport = RecordingMarlinTransport()
    orchestrator.motion = MarlinMotionAdapter(transport=transport)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.runtime_mode = "hardware"
    runtime.hardware_runtime = True
    client = app.test_client()

    home = client.post("/api/control/home_z", json={})
    jog = client.post("/api/control/jog_z", json={"dz_mm": -10.0})

    assert home.status_code == 200
    assert jog.status_code == 200
    assert transport.command_log[-4:] == ["G91", "G1 Z-10.000 F300", "M400", "G90"]


def test_control_requests_are_written_to_persistent_audit_log(tmp_path):
    client = _client(runtime_mode="simulation")
    runtime = client.application.config["runtime"]
    runtime.control_audit_path = tmp_path / "control_audit.jsonl"

    response = client.post("/api/control/jog_z", json={"dz_mm": 1.0})

    assert response.status_code == 200
    entries = [json.loads(line) for line in runtime.control_audit_path.read_text(encoding="utf-8").splitlines()]
    assert entries[-1]["action"] == "jog_z"
    assert entries[-1]["payload"] == {"dz_mm": 1.0}
    assert entries[-1]["ok"] is True
    assert entries[-1]["runtime_target"] == "simulation"


def test_debug_events_log_api_and_ui_events(tmp_path):
    client = _client(runtime_mode="simulation")
    runtime = client.application.config["runtime"]
    runtime.debug_events_path = tmp_path / "debug_events.jsonl"

    event = client.post("/api/debug/event", json={"event": "ui.button.click", "details": {"id": "save"}})
    status = client.get("/api/status")

    assert event.status_code == 200
    assert status.status_code == 200
    entries = [json.loads(line) for line in runtime.debug_events_path.read_text(encoding="utf-8").splitlines()]
    assert any(entry["event"] == "ui.button.click" and entry["details"]["id"] == "save" for entry in entries)
    assert any(entry["event"] == "api.call" and entry["details"]["path"] == "/api/debug/event" for entry in entries)
    assert any(entry["event"] == "api.call" and entry["details"]["path"] == "/api/status" for entry in entries)


def test_serial_session_writes_debug_events():
    events = []
    session = web_app_module.SerialBoardSession(event_logger=lambda event, details: events.append((event, details)))
    session.transport = RecordingTransport()
    session.port = "COM8"
    session.connection_state = "verified"
    session.last_success_monotonic = web_app_module.time.monotonic()

    session.send_command("M114")

    assert any(event == "serial.command" and details["command"] == "M114" for event, details in events)


def test_serial_connect_uses_short_probe_timeout(monkeypatch):
    created = []

    class FakeConnection:
        timeout = None

    class FakeTransport:
        def __init__(self, *, serial_port, baud_rate, timeout_seconds):
            self.serial_port = serial_port
            self.baud_rate = baud_rate
            self.initial_timeout_seconds = timeout_seconds
            self.timeout_seconds = timeout_seconds
            self.connection = FakeConnection()
            created.append(self)

        def open(self):
            return self.connection

        def send_command(self, command):
            return ["FIRMWARE_NAME:test", "ok"]

        def close(self):
            pass

    monkeypatch.setattr(web_app_module, "MarlinSerialTransport", FakeTransport)
    session = web_app_module.SerialBoardSession()

    result = session.connect("COM8", 115200)

    assert result["ok"] is True
    assert created[0].serial_port == "COM8"
    assert created[0].initial_timeout_seconds == web_app_module.SERIAL_CONNECT_TIMEOUT_SECONDS
    assert created[0].timeout_seconds == web_app_module.SERIAL_COMMAND_TIMEOUT_SECONDS
    assert created[0].connection.timeout == web_app_module.SERIAL_COMMAND_TIMEOUT_SECONDS


def test_hardware_home_controls_send_axis_specific_and_grouped_sequences():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(orchestrator, calibration)
    app.testing = True
    runtime = app.config["runtime"]
    runtime.serial_board = FakeSerialBoard()
    runtime.serial_board.connect("COM8", 115200)
    client = app.test_client()

    home_c = client.post("/api/control/home_c", json={})
    home_all = client.post("/api/control/home", json={})

    assert home_c.status_code == 200
    assert home_all.status_code == 200
    assert "G28 C" in runtime.serial_board.sent_commands
    assert runtime.serial_board.sent_commands[-3:] == ["G28 Z C", "G28 X Y", "M114"]


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
    assert status["runtime_target"] == "hardware_unavailable"


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
    client = _client("simulation")

    z_response = client.post("/api/control/jog_z", json={"dz_mm": 2.5})
    xy_response = client.post("/api/control/jog_xy", json={"dx_mm": 4.0, "dy_mm": -3.0})
    status = client.get("/api/status").get_json()

    assert z_response.status_code == 200
    assert xy_response.status_code == 200
    assert status["pose"]["x_mm"] == 4.0
    assert status["pose"]["y_mm"] == -3.0
    assert status["pose"]["z_mm"] == 2.5


def test_c_axis_control_updates_pose():
    client = _client("simulation")

    response = client.post("/api/control/move_c", json={"c_mm": 1.0})
    status = client.get("/api/status").get_json()

    assert response.status_code == 200
    assert status["pose"]["c_mm"] == 1.0


def test_paired_zc_interface_jog_keeps_end_effector_height_fixed():
    client = _client("simulation")

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
    with Path("pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]

    assert re.fullmatch(r"\d+\.\d+\.\d+-[0-9a-f]+", payload["version"])
    assert payload["package_version"] == project_version
    assert payload["version"].startswith(f"{project_version}-")
    assert payload["remote"] == "origin/main"
    assert "update_available" in payload
    assert "can_update" in payload
    assert "visual_index" in payload
    assert payload["visual_index"]["configured_refresh_days"] == 7
    assert payload["visual_index"]["refresh_options"] == [1, 3, 7, 14, 30, 60, 90]
    assert [item["name"] for item in payload["submodules"]] == [
        "fuzzy-enigma",
        "magic-the-collecting",
    ]


def test_collection_service_api_reports_unconfigured_adapter():
    payload = _client().get("/api/collection-service").get_json()

    assert payload["configured"] is False
    assert payload["available"] is False
    assert payload["status"] == "unconfigured"


def test_system_update_refuses_when_not_safe(monkeypatch):
    client = _client()

    def fake_system_info(self, refresh_remote=False, refresh_visual_index=False):
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


def test_system_update_schedules_restart_after_successful_pull(monkeypatch):
    client = _client()
    states = iter(
        [
            {
                "version": "0.4.0-abc1234",
                "package_version": "0.4.0",
                "current_sha": "abc1234",
                "current_branch": "main",
                "dirty": False,
                "remote": "origin/main",
                "remote_sha": "def5678",
                "commits_behind": 1,
                "commits_ahead": 0,
                "update_available": True,
                "can_update": True,
                "message": None,
                "restart_required": False,
            },
            {
                "version": "0.4.0-def5678",
                "package_version": "0.4.0",
                "current_sha": "def5678",
                "current_branch": "main",
                "dirty": False,
                "remote": "origin/main",
                "remote_sha": "def5678",
                "commits_behind": 0,
                "commits_ahead": 0,
                "update_available": False,
                "can_update": False,
                "message": "Already up to date",
                "restart_required": False,
            },
        ]
    )
    scheduled = []

    monkeypatch.setattr(
        web_app_module.WebRuntime,
        "system_info",
        lambda self, refresh_remote=False, refresh_visual_index=False: next(states),
    )
    monkeypatch.setattr(
        web_app_module,
        "_run_git",
        lambda args, cwd, timeout=10: web_app_module.subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(
        web_app_module,
        "_run_deploy_script",
        lambda repo_root, timeout=900: web_app_module.subprocess.CompletedProcess(["deploy"], 0, "", ""),
    )
    monkeypatch.setattr(web_app_module, "_schedule_web_process_restart", lambda: scheduled.append(True) or True)

    response = client.post("/api/system/update")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["restart_required"] is True
    assert payload["restart_scheduled"] is True
    assert scheduled == [True]
    assert payload["message"] == "Updated from origin/main, installed dependencies, and restarting the web process."


def test_system_update_reports_deploy_install_failure(monkeypatch):
    client = _client()
    states = iter(
        [
            {
                "version": "0.4.0-abc1234",
                "package_version": "0.4.0",
                "current_sha": "abc1234",
                "current_branch": "main",
                "dirty": False,
                "remote": "origin/main",
                "remote_sha": "def5678",
                "commits_behind": 1,
                "commits_ahead": 0,
                "update_available": True,
                "can_update": True,
                "message": None,
                "restart_required": False,
            },
            {
                "version": "0.4.0-def5678",
                "package_version": "0.4.0",
                "current_sha": "def5678",
                "current_branch": "main",
                "dirty": False,
                "remote": "origin/main",
                "remote_sha": "def5678",
                "commits_behind": 0,
                "commits_ahead": 0,
                "update_available": False,
                "can_update": False,
                "message": "Already up to date",
                "restart_required": False,
            },
        ]
    )

    monkeypatch.setattr(
        web_app_module.WebRuntime,
        "system_info",
        lambda self, refresh_remote=False, refresh_visual_index=False: next(states),
    )
    monkeypatch.setattr(
        web_app_module,
        "_run_git",
        lambda args, cwd, timeout=10: web_app_module.subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(
        web_app_module,
        "_run_deploy_script",
        lambda repo_root, timeout=900: web_app_module.subprocess.CompletedProcess(["deploy"], 2, "", "install failed"),
    )
    monkeypatch.setattr(web_app_module, "_schedule_web_process_restart", lambda: False)

    response = client.post("/api/system/update")
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["ok"] is False
    assert payload["message"] == "install failed"
    assert payload["deploy_returncode"] == 2


def test_system_visual_index_policy_endpoint_can_save_refresh_days():
    client = _client()
    runtime = client.application.config["runtime"]
    runtime.set_visual_index_policy = lambda refresh_days: {
        "configured_refresh_days": refresh_days,
        "message": "saved",
        "refresh_options": [1, 3, 7, 14, 30, 60, 90],
    }

    response = client.post("/api/system/visual-index/policy", json={"refresh_days": 14})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["configured_refresh_days"] == 14
    assert payload["message"] == "saved"


def test_system_visual_index_refresh_endpoint_returns_refresh_status():
    client = _client()
    runtime = client.application.config["runtime"]
    runtime.refresh_visual_index = lambda: {
        "configured_refresh_days": 7,
        "refreshing": True,
        "message": "started",
        "refresh_options": [1, 3, 7, 14, 30, 60, 90],
    }

    response = client.post("/api/system/visual-index/refresh")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["configured_refresh_days"] == 7
    assert payload["refreshing"] is True
    assert payload["message"] == "started"


def test_calibration_can_be_updated_from_web_app(tmp_path):
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    calibration_path = tmp_path / "calibration.json"
    app = create_web_app(orchestrator, calibration, calibration_path=calibration_path)
    app.config["runtime"].runtime_mode = "simulation"
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
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert "Calibration saved" in payload["message"]
    assert payload["calibration"]["camera_offset_z_mm"] == 11.0
    assert payload["saved_path"] == str(calibration_path)
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


def test_machine_page_has_calibration_save_message_target():
    client = _client()

    response = client.get("/machine")

    assert response.status_code == 200
    assert b'id="calibration-message"' in response.data


def test_web_xy_control_blocks_when_vacuum_z_is_too_low():
    settings = _sim_truth_settings()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path).with_updates(min_xy_travel_z_mm=10.0)
    app = create_web_app(orchestrator, calibration)
    app.config["runtime"].runtime_mode = "simulation"
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
    app.config["runtime"].runtime_mode = "simulation"
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
    app.config["runtime"].runtime_mode = "simulation"
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


class BrightnessCamera:
    def __init__(self, lights, capture_dir: Path):
        self.lights = lights
        self.capture_dir = capture_dir
        self.index = 0

    def capture_frame(self):
        red, green, blue = getattr(self.lights, "last_rgb", (0, 0, 0))
        brightness = max(0, min(255, int((red + green + blue) / 3)))
        path = self.capture_dir / f"lighting-{self.index}.jpg"
        self.index += 1
        Image.new("RGB", (48, 48), (brightness, brightness, brightness)).save(path)
        return Frame(
            frame_id=f"lighting-{self.index}",
            path=str(path),
            pile_id=None,
            metadata={},
            captured_at_utc="2026-01-01T00:00:00Z",
            camera_id="brightness-test",
            source_mode="test",
        )


class SplitBrightnessCamera:
    def __init__(self, lights, capture_dir: Path):
        self.lights = lights
        self.capture_dir = capture_dir
        self.index = 0

    def capture_frame(self):
        red, green, blue = getattr(self.lights, "last_rgb", (0, 0, 0))
        brightness = max(0, min(255, int((red + green + blue) / 3)))
        path = self.capture_dir / f"split-lighting-{self.index}.jpg"
        self.index += 1
        image = Image.new("RGB", (80, 40), (250, 250, 250))
        for x in range(0, 40):
            for y in range(40):
                image.putpixel((x, y), (brightness, brightness, brightness))
        image.save(path)
        return Frame(
            frame_id=f"split-lighting-{self.index}",
            path=str(path),
            pile_id=None,
            metadata={},
            captured_at_utc="2026-01-01T00:00:00Z",
            camera_id="split-brightness-test",
            source_mode="test",
        )


class SingleLedCamera:
    def __init__(self, lights, capture_dir: Path, *, preferred_led: int):
        self.lights = lights
        self.capture_dir = capture_dir
        self.preferred_led = preferred_led
        self.index = 0

    def capture_frame(self):
        pixels = getattr(self.lights, "last_pixels", [[0, 0, 0] for _ in range(16)])
        lit_index = next((index for index, pixel in enumerate(pixels) if any(pixel)), None)
        brightness = 96 if lit_index == self.preferred_led else 32
        path = self.capture_dir / f"single-led-{self.index}.jpg"
        self.index += 1
        Image.new("RGB", (48, 48), (brightness, brightness, brightness)).save(path)
        return Frame(
            frame_id=f"single-led-{self.index}",
            path=str(path),
            pile_id=None,
            metadata={},
            captured_at_utc="2026-01-01T00:00:00Z",
            camera_id="single-led-test",
            source_mode="test",
        )


class StaticImageCamera:
    def __init__(self, image_path: Path):
        self.image_path = image_path
        self.index = 0

    def capture_frame(self):
        self.index += 1
        return Frame(
            frame_id=f"static-{self.index}",
            path=str(self.image_path),
            pile_id=None,
            metadata={},
            captured_at_utc="2026-01-01T00:00:00Z",
            camera_id="static-card-back-test",
            source_mode="test",
        )


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
        self.pixel_displays = []
        self.fail_next_command = False
        self.connection_state = "disconnected"
        self.absolute_mode = True

    def status(self):
        return {
            "connected": self.connected,
            "session_open": self.connected,
            "connection_state": self.connection_state,
            "controller_fault": False,
            "busy": False,
            "port": self.port,
            "baud_rate": self.baud_rate,
            "last_error": self.last_error,
            "last_response": self.last_response,
            "last_endstops": self.last_endstops,
            "serial_command_log": [],
            "serial_poll_log": [],
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

    def send_status_poll(self, command):
        return self.send_command(command)

    def send_commands(self, commands, *, message):
        responses = []
        for command in commands:
            if command == "G90":
                self.absolute_mode = True
            elif command == "G91":
                self.absolute_mode = False
            elif command.startswith("G1 "):
                for token in command.split():
                    if token.startswith("X"):
                        value = float(token[1:])
                        self.live_pose["x"] = value if self.absolute_mode else self.live_pose.get("x", 0.0) + value
                    if token.startswith("Y"):
                        value = float(token[1:])
                        self.live_pose["y"] = value if self.absolute_mode else self.live_pose.get("y", 0.0) + value
                    if token.startswith("Z"):
                        value = float(token[1:])
                        self.live_pose["z"] = value if self.absolute_mode else self.live_pose.get("z", 0.0) + value
                    if token.startswith("C"):
                        value = float(token[1:])
                        self.live_pose["c"] = value if self.absolute_mode else self.live_pose.get("c", 0.0) + value
            result = self.send_command(command)
            responses.extend(result["response"])
        return {"ok": True, "message": message, "response": responses, **self.status()}

    def read_endstops(self, *, poll=False):
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

    def set_neopixel_pixels(self, pixels):
        normalized = [[int(red), int(green), int(blue)] for red, green, blue in pixels]
        self.pixel_displays.append(normalized)
        for index, (red, green, blue) in enumerate(normalized):
            self.sent_commands.append(f"M150 I{index} R{red} U{green} B{blue}")
        self.last_response = ["ok"] * len(normalized)
        return {
            "ok": True,
            "message": "Applied 16-pixel NeoPixel display",
            "response": self.last_response,
            **self.status(),
        }


class RecordingTransport:
    def __init__(self, serial_port="COM8"):
        self.serial_port = serial_port
        self.baud_rate = 115200
        self.timeout_seconds = 2.0
        self.commands = []
        self.closed = False

    def send_command(self, command, *, wait_for_ok=True):
        self.commands.append(command)
        return [f"{command} response", "ok"]

    def close(self):
        self.closed = True


class FaultingTransport:
    def __init__(self):
        self.closed = False

    def send_command(self, command, *, wait_for_ok=True):
        error = RuntimeError(f"Marlin rejected {command!r}: Error:Printer halted. kill() called!")
        error.responses = ["Error:Printer halted. kill() called!"]
        raise error

    def close(self):
        self.closed = True


class StoppedResponseTransport:
    def __init__(self):
        self.closed = False

    def send_command(self, command, *, wait_for_ok=True):
        return [
            "Printer stopped due to errors. Fix the error and use M999 to restart.",
            "//action:notification STOPPED.",
            "ok",
        ]

    def close(self):
        self.closed = True
