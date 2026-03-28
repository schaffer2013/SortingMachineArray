from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class RecognitionPolicyConfig:
    min_confidence: float = 0.6
    allow_sim_truth_fallback: bool = False

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
        try:
            min_confidence = float(min_confidence)
        except (TypeError, ValueError):
            min_confidence = cls.min_confidence
        return cls(
            min_confidence=min_confidence,
            allow_sim_truth_fallback=bool(allow_sim_truth_fallback),
        )
