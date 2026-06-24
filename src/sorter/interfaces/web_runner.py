from pathlib import Path

from sorter.bootstrap import build_hardware_orchestrator, build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.logging_setup import configure_app_logging
from sorter.interfaces.web import create_web_app


def _local_data_path(project_root: Path, filename: str) -> Path:
    return project_root / "local_data" / filename


def _load_calibration(project_root: Path, settings: AppSettings) -> tuple[CalibrationProfile, Path]:
    local_path = _local_data_path(project_root, "calibration.json")
    calibration_path = local_path if local_path.exists() else settings.calibration_path
    return CalibrationProfile.from_file(calibration_path), local_path


def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    configure_app_logging(project_root)
    settings = AppSettings.from_env(project_root)
    calibration, writable_calibration_path = _load_calibration(project_root, settings)
    if settings.mode == "hardware":
        orchestrator = build_hardware_orchestrator(settings, calibration)
        runtime_mode = "hardware"
    else:
        orchestrator = build_sim_orchestrator(settings)
        runtime_mode = "simulation"
    app = create_web_app(
        orchestrator,
        calibration,
        slow_ms=settings.slow_ms,
        light_profiles_path=_local_data_path(project_root, "light_profiles.json"),
        light_profiles_seed_path=project_root / "config" / "light_profiles.json",
        calibration_path=writable_calibration_path,
        runtime_mode=runtime_mode,
    )
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
