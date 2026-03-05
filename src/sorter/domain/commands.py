from __future__ import annotations

from dataclasses import dataclass

from sorter.domain.models import PileId


@dataclass(frozen=True)
class HomeAxes:
    pass


@dataclass(frozen=True)
class MoveXY:
    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class MoveZ:
    z_mm: float


@dataclass(frozen=True)
class VacuumOn:
    pass


@dataclass(frozen=True)
class VacuumOff:
    pass


@dataclass(frozen=True)
class CaptureTopCard:
    pile_id: PileId


@dataclass(frozen=True)
class PickCard:
    pile_id: PileId


@dataclass(frozen=True)
class PlaceCard:
    pile_id: PileId


@dataclass(frozen=True)
class SetLights:
    status: str


@dataclass(frozen=True)
class AbortRun:
    reason: str
