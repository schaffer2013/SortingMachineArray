from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

from sorter.domain.enums import PileRole


@dataclass(frozen=True)
class CardMeta:
    name: str
    scryfall_id: str | None = None
    oracle_id: str | None = None
    rarity: str | None = None
    colors: list[str] = field(default_factory=list)
    color_identity: list[str] = field(default_factory=list)
    card_types: list[str] = field(default_factory=list)
    supertypes: list[str] = field(default_factory=list)
    is_land: bool = False
    is_basic_land: bool = False
    mana_value: float | int | None = None
    market_price_usd: float | None = None
    # Legacy migration field: this is not an authoritative rank source.
    sort_rank: int | None = None


@dataclass(frozen=True)
class CardInstance:
    card_id: str
    meta: CardMeta


@dataclass(frozen=True)
class CardView:
    pile_id: "PileId"
    card_name: str | None
    confidence: float


@dataclass(frozen=True)
class PileId:
    x_index: int
    y_index: int

    def as_key(self) -> str:
        return f"{self.x_index},{self.y_index}"


@dataclass
class PileState:
    pile_id: PileId
    role: PileRole
    capacity: int
    x_mm: float = 0.0
    y_mm: float = 0.0
    card_stack: list[str] = field(default_factory=list)
    discovered: bool = False

    def num_cards(self) -> int:
        return len(self.card_stack)

    def is_empty(self) -> bool:
        return not self.card_stack

    def is_full(self) -> bool:
        return len(self.card_stack) >= self.capacity

    def top_card_id(self) -> str | None:
        if self.is_empty():
            return None
        return self.card_stack[-1]

    def bottom_card_id(self) -> str | None:
        if self.is_empty():
            return None
        return self.card_stack[0]

    def distance_from(self, other: "PileState") -> float:
        """Return Euclidean XY distance in millimeters to another pile."""
        return math.hypot(self.x_mm - other.x_mm, self.y_mm - other.y_mm)


@dataclass
class MachinePose:
    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0
    holding_card_id: str | None = None
    vacuum_on: bool = False


@dataclass
class RunMetrics:
    move_count: int = 0
    distance_mm: float = 0.0
    failures: int = 0


@dataclass
class RunState:
    phase: Literal[
        "IDLE",
        "DISCOVERING",
        "PLANNING",
        "EXECUTING",
        "VERIFYING",
        "FAULTED",
        "COMPLETED",
    ] = "IDLE"
    faults: list[str] = field(default_factory=list)
    active_command: str | None = None
    metrics: RunMetrics = field(default_factory=RunMetrics)


@dataclass
class MachineSnapshot:
    piles: dict[str, PileState]
    pose: MachinePose = field(default_factory=MachinePose)
    run_state: RunState = field(default_factory=RunState)

    def get_pile(self, pile_id: PileId) -> PileState | None:
        return self.piles.get(pile_id.as_key())
