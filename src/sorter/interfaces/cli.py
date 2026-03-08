from __future__ import annotations

import argparse
from pathlib import Path

from sorter.bootstrap import build_sim_orchestrator
from sorter.config.settings import AppSettings
from sorter.config.calibration import CalibrationProfile
from sorter.interfaces.logging_setup import configure_app_logging


def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    configure_app_logging(project_root)

    parser = argparse.ArgumentParser(description="Card sorter test bed CLI")
    parser.add_argument("--mode", choices=["sim", "hardware"], default="sim")
    parser.add_argument("--slow-ms", type=int, default=None, help="Delay per atomic command in milliseconds")
    args = parser.parse_args()

    settings = AppSettings.from_env()
    if args.mode != settings.mode:
        settings = AppSettings(
            mode=args.mode,
            random_seed=settings.random_seed,
            scenario_fixture=settings.scenario_fixture,
            card_catalog_path=settings.card_catalog_path,
            sqlite_path=settings.sqlite_path,
            calibration_path=settings.calibration_path,
            sort_policy_path=settings.sort_policy_path,
            slow_ms=settings.slow_ms,
            auto_image_sync=settings.auto_image_sync,
            project_root=settings.project_root,
        )

    if settings.mode != "sim":
        raise NotImplementedError("Hardware bootstrap is provided via scripts/hardware_smoke_test.py")

    orchestrator = build_sim_orchestrator(settings)
    calibration = CalibrationProfile.from_file(settings.calibration_path)
    slow_ms = settings.slow_ms if args.slow_ms is None else max(0, args.slow_ms)
    result = orchestrator.run_once(calibration, per_command_delay_s=slow_ms / 1000.0)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
