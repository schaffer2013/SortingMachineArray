from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Literal

from sorter.domain.enums import PileObservationState, PileRole


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
class PileObservation:
    state: PileObservationState = PileObservationState.UNKNOWN
    top_card_name: str | None = None
    confidence: float = 0.0
    source: str | None = None
    frame_id: str | None = None
    observed_at_utc: str | None = None

    def is_known(self) -> bool:
        return self.state != PileObservationState.UNKNOWN

    def has_top_card(self) -> bool:
        return self.state == PileObservationState.TOP_CARD_SEEN

    def is_empty_confirmed(self) -> bool:
        return self.state == PileObservationState.EMPTY_CONFIRMED


@dataclass
class PileState:
    pile_id: PileId
    role: PileRole
    capacity: int
    x_mm: float = 0.0
    y_mm: float = 0.0
    card_stack: list[str] = field(default_factory=list)
    discovered: bool = False
    stack_count_known: bool = False
    observation: PileObservation = field(default_factory=PileObservation)

    def __post_init__(self) -> None:
        if self.observation.state != PileObservationState.UNKNOWN:
            self.discovered = True
            return
        if self.discovered:
            self.stack_count_known = True
            if self.is_empty():
                self.mark_empty_confirmed(source="legacy_discovered")
            else:
                self.observation.state = PileObservationState.TOP_CARD_SEEN
                self.observation.confidence = 1.0
                self.observation.source = "legacy_discovered"

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

    def has_known_state(self) -> bool:
        return self.observation.is_known()

    def has_observed_top_card(self) -> bool:
        return self.observation.has_top_card()

    def has_known_count(self) -> bool:
        return self.stack_count_known

    def is_empty_confirmed(self) -> bool:
        return self.observation.is_empty_confirmed()

    def observation_is_stale(self, reference_utc: str, *, max_age_seconds: float) -> bool:
        if self.observation.observed_at_utc is None:
            return True
        observed_at = datetime.fromisoformat(self.observation.observed_at_utc)
        reference_at = datetime.fromisoformat(reference_utc)
        return (reference_at - observed_at).total_seconds() > max_age_seconds

    def mark_unknown(
        self,
        source: str | None = None,
        frame_id: str | None = None,
        observed_at_utc: str | None = None,
    ) -> None:
        self.discovered = False
        self.stack_count_known = False
        self.card_stack.clear()
        self.observation = PileObservation(
            source=source,
            frame_id=frame_id,
            observed_at_utc=observed_at_utc,
        )

    def mark_top_card_seen(
        self,
        card_name: str | None,
        confidence: float = 1.0,
        source: str | None = None,
        frame_id: str | None = None,
        observed_at_utc: str | None = None,
        count_known: bool | None = None,
    ) -> None:
        self.discovered = True
        if count_known is not None:
            self.stack_count_known = count_known
        self.observation = PileObservation(
            state=PileObservationState.TOP_CARD_SEEN,
            top_card_name=card_name,
            confidence=confidence,
            source=source,
            frame_id=frame_id,
            observed_at_utc=observed_at_utc,
        )

    def mark_empty_confirmed(
        self,
        confidence: float = 1.0,
        source: str | None = None,
        frame_id: str | None = None,
        observed_at_utc: str | None = None,
    ) -> None:
        self.discovered = True
        self.stack_count_known = True
        self.observation = PileObservation(
            state=PileObservationState.EMPTY_CONFIRMED,
            top_card_name=None,
            confidence=confidence,
            source=source,
            frame_id=frame_id,
            observed_at_utc=observed_at_utc,
        )

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
    scan_count: int = 0
    retry_count: int = 0
    review_required_count: int = 0
    fallback_count: int = 0
    low_confidence_count: int = 0
    confidence_band_counts: dict[str, int] = field(default_factory=dict)
    review_reason_counts: dict[str, int] = field(default_factory=dict)
    review_family_counts: dict[str, int] = field(default_factory=dict)


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
