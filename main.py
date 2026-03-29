from pathlib import Path

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.logging_setup import configure_app_logging
from sorter.interfaces.tkinter_debug import TkDebugUI


def main() -> int:
    project_root = Path(__file__).resolve().parent
    configure_app_logging(project_root)
    settings = AppSettings.from_env()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    ui = TkDebugUI(orchestrator, calibration, slow_ms=settings.slow_ms)
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())