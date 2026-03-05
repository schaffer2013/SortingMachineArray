from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimFault:
    fault_type: str
    after_move: int
