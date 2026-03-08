from __future__ import annotations

import logging
from pathlib import Path


def configure_app_logging(project_root: Path, console_level: int = logging.INFO) -> Path:
    """Configure a single consolidated application log file.

    All module loggers propagate to root, so one file handler captures workflow,
    orchestrator, and adapter logs together.
    """
    log_dir = project_root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "sorter.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    resolved_log_path = str(log_path.resolve())
    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == resolved_log_path
        for handler in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )
        root_logger.addHandler(file_handler)

    has_console_handler = any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s - %(message)s"))
        root_logger.addHandler(console_handler)

    return log_path
