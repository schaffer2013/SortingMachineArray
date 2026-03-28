from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class RecognitionPolicyConfig:
    min_confidence: float = 0.6
    allow_sim_truth_fallback: bool = False
    startup_scan_max_retries: int = 1
    verification_max_retries: int = 2

    @classmethod
    def from_file(cls, path: Path) -> "RecognitionPolicyConfig":
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(payload, dict):
            return cls()
        min_confidence = payload.get("verification_min_confidence", cls.min_confidence)
        allow_sim_truth_fallback = payload.get("allow_sim_truth_fallback", cls.allow_sim_truth_fallback)
        startup_scan_max_retries = payload.get("startup_scan_max_retries", cls.startup_scan_max_retries)
        verification_max_retries = payload.get("verification_max_retries", cls.verification_max_retries)
        try:
            min_confidence = float(min_confidence)
        except (TypeError, ValueError):
            min_confidence = cls.min_confidence
        try:
            startup_scan_max_retries = int(startup_scan_max_retries)
        except (TypeError, ValueError):
            startup_scan_max_retries = cls.startup_scan_max_retries
        try:
            verification_max_retries = int(verification_max_retries)
        except (TypeError, ValueError):
            verification_max_retries = cls.verification_max_retries
        return cls(
            min_confidence=min_confidence,
            allow_sim_truth_fallback=bool(allow_sim_truth_fallback),
            startup_scan_max_retries=max(0, startup_scan_max_retries),
            verification_max_retries=max(0, verification_max_retries),
        )
