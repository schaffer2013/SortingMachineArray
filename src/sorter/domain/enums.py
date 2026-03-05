from __future__ import annotations

from enum import Enum


class PileRole(str, Enum):
    FEEDER = "FEEDER"
    SORTING = "SORTING"
    COLLECTION = "COLLECTION"
    BLACKHOLE = "BLACKHOLE"
    TEMP = "TEMP"


class RunPhase(str, Enum):
    IDLE = "IDLE"
    DISCOVERING = "DISCOVERING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    FAULTED = "FAULTED"
    COMPLETED = "COMPLETED"


class LegacyStep(Enum):
    MOVE_FROM_FEED = 0
    INITIAL_COLLECTION = 1
    SCATTER = 2
    GATHER = 3
    FINISH = 4
