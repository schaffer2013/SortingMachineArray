from sorter.bootstrap import build_sim_orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.config.settings import AppSettings
from sorter.interfaces.pygame_debug import PygameDebugUI


def main() -> int:
    settings = AppSettings.from_env()
    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    ui = PygameDebugUI(orchestrator, calibration, slow_ms=settings.slow_ms)
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
