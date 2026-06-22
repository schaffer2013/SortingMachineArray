from __future__ import annotations

from dataclasses import replace
import sys
import types

import pytest

from sorter import bootstrap
from sorter.adapters.hardware.gpio_vacuum import GpioVacuumAdapter
from sorter.adapters.hardware.picamera2_camera import PiCamera2Adapter
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.web import create_web_app


class FakeRecognizer:
    pass


class FakeCamera:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class FakeVacuum:
    def __init__(self, *args, **kwargs) -> None:
        self.state = False

    def on(self) -> None:
        self.state = True

    def off(self) -> None:
        self.state = False

    def is_on(self) -> bool:
        return self.state


def test_hardware_runtime_rejects_sim_truth_backend(monkeypatch) -> None:
    settings = replace(AppSettings.from_env(), recognizer_backend="sim_truth")

    with pytest.raises(ValueError, match="Hardware runtime cannot use"):
        bootstrap._build_hardware_recognizer(settings, bootstrap.FileCardCatalog(settings.card_catalog_path))


def test_build_hardware_orchestrator_uses_real_adapter_path(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap, "PiCamera2Adapter", FakeCamera)
    monkeypatch.setattr(bootstrap, "GpioVacuumAdapter", FakeVacuum)
    monkeypatch.setattr(bootstrap, "FuzzyEnigmaRecognizerAdapter", lambda **kwargs: FakeRecognizer())

    settings = replace(AppSettings.from_env(), mode="hardware", recognizer_backend="moss_machine")
    calibration = CalibrationProfile.from_file(settings.calibration_path)

    orchestrator = bootstrap.build_hardware_orchestrator(settings, calibration)

    assert orchestrator.hardware_runtime is True
    assert orchestrator.world.scenario_name == "hardware"
    assert orchestrator.world.snapshot.piles
    assert isinstance(orchestrator.camera, FakeCamera)
    assert isinstance(orchestrator.vacuum, FakeVacuum)


def test_hardware_web_runtime_reports_direct_backend(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap, "PiCamera2Adapter", FakeCamera)
    monkeypatch.setattr(bootstrap, "GpioVacuumAdapter", FakeVacuum)
    monkeypatch.setattr(bootstrap, "FuzzyEnigmaRecognizerAdapter", lambda **kwargs: FakeRecognizer())

    settings = replace(AppSettings.from_env(), mode="hardware", recognizer_backend="moss_machine")
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    orchestrator = bootstrap.build_hardware_orchestrator(settings, calibration)
    app = create_web_app(orchestrator, calibration, runtime_mode="hardware")
    app.testing = True

    status = app.test_client().get("/api/status").get_json()

    assert status["runtime_mode"] == "hardware"
    assert status["runtime_target"] == "hardware_direct"
    assert "direct Pi adapters" in status["runtime_message"]


def test_picamera2_adapter_persists_frame_path(tmp_path, monkeypatch) -> None:
    captured_paths: list[str] = []

    class FakePicamera2:
        def create_still_configuration(self):
            return {"mode": "still"}

        def configure(self, config) -> None:
            self.config = config

        def start(self) -> None:
            self.started = True

        def capture_file(self, path: str) -> None:
            captured_paths.append(path)

    monkeypatch.setitem(sys.modules, "picamera2", types.SimpleNamespace(Picamera2=FakePicamera2))

    frame = PiCamera2Adapter(capture_dir=tmp_path).capture_frame()

    assert frame.path == captured_paths[0]
    assert frame.source_mode == "hardware"
    assert frame.camera_id == "picamera2"


def test_gpio_vacuum_adapter_drives_output_device(monkeypatch) -> None:
    events: list[str] = []

    class FakeOutputDevice:
        def __init__(self, pin: int, *, active_high: bool, initial_value: bool) -> None:
            events.append(f"init:{pin}:{active_high}:{initial_value}")

        def on(self) -> None:
            events.append("on")

        def off(self) -> None:
            events.append("off")

        def close(self) -> None:
            events.append("close")

    monkeypatch.setitem(sys.modules, "gpiozero", types.SimpleNamespace(OutputDevice=FakeOutputDevice))

    vacuum = GpioVacuumAdapter(relay_pin=22, active_high=False)
    vacuum.on()
    vacuum.off()
    vacuum.close()

    assert events == ["init:22:False:False", "on", "off", "close"]
    assert vacuum.is_on() is False