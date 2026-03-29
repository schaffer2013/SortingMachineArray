from __future__ import annotations

from enum import Enum


class PileRole(str, Enum):
    FEEDER = "FEEDER"
    SORTING = "SORTING"
    COLLECTION = "COLLECTION"
    BLACKHOLE = "BLACKHOLE"
    TEMP = "TEMP"


class PileObservationState(str, Enum):
    UNKNOWN = "UNKNOWN"
    TOP_CARD_SEEN = "TOP_CARD_SEEN"
    EMPTY_SUSPECTED = "EMPTY_SUSPECTED"
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"

class WorkflowStep(Enum):
    MOVE_FROM_FEED = 0
    INITIAL_COLLECTION = 1
    SCATTER = 2
    GATHER = 3
    FINISH = 4
