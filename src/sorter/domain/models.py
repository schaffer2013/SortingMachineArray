from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sorter.domain.enums import PileRole


RARITY_ORDER = {
    "MYTHIC": 1,
    "RARE": 1,
    "OTHER": 3,
}

TYPE_ORDER = {
    "creature": 1,
    "artifact": 1,
    "battle": 1,
    "instant": 1,
    "sorcery": 1,
    "planeswalker": 1,
    "enchantment": 1,
    "non-basic land": 8,
    "basic land": 9,
    "other": 10,
}

COLOR_ORDER = {
    "white": 1,
    "blue": 2,
    "black": 3,
    "red": 4,
    "green": 5,
    "multi": 6,
    "colorless": 7,
    "default": 8,
}


@dataclass(frozen=True)
class CardMeta:
    name: str
    rarity: str = "OTHER"
    card_type: str = "other"
    color: str = "default"
    sort_rank: int = 99999


@dataclass(frozen=True)
class CardInstance:
    card_id: str
    meta: CardMeta

    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            RARITY_ORDER.get(self.meta.rarity, RARITY_ORDER["OTHER"]),
            TYPE_ORDER.get(self.meta.card_type, TYPE_ORDER["other"]),
            COLOR_ORDER.get(self.meta.color, COLOR_ORDER["default"]),
            self.meta.name,
        )


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
