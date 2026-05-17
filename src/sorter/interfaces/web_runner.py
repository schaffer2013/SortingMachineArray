from pathlib import Path

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.logging_setup import configure_app_logging
from sorter.interfaces.web import create_web_app


def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    configure_app_logging(project_root)
    settings = AppSettings.from_env(project_root)
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    app = create_web_app(
        orchestrator,
        calibration,
        slow_ms=settings.slow_ms,
        light_profiles_path=project_root / "config" / "light_profiles.json",
    )
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
