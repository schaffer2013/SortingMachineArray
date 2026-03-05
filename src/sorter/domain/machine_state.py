from __future__ import annotations

from dataclasses import dataclass

from sorter.domain.enums import LegacyStep, PileRole
from sorter.domain.models import MachineSnapshot, PileId


@dataclass(frozen=True)
class NextMove:
    from_pile: PileId
    to_pile: PileId


class LegacyWorkflowState:
    def __init__(self, snapshot: MachineSnapshot):
        self.snapshot = snapshot
        self.step = LegacyStep.MOVE_FROM_FEED

    def _piles_by_role(self, *roles: PileRole):
        role_set = set(roles)
        return [pile for pile in self.snapshot.piles.values() if pile.role in role_set]

    def _all_empty(self, piles) -> bool:
        return all(pile.is_empty() for pile in piles)

    def _find_move_from_feed(self):
        from_pile = next(
            (
                pile
                for pile in self._piles_by_role(PileRole.FEEDER)
                if not pile.discovered
            ),
            None,
        )
        to_pile = next(
            (
                pile
                for pile in self.snapshot.piles.values()
                if pile.role != PileRole.FEEDER and pile.discovered and not pile.is_full()
            ),
            None,
        )
        if from_pile and to_pile:
            return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)
        return None

    def _find_initial_collection(self):
        from_pile = next(
            (
                pile
                for pile in self.snapshot.piles.values()
                if pile.role != PileRole.FEEDER and not pile.is_empty()
            ),
            None,
        )
        to_pile = next(
            (
                pile
                for pile in self._piles_by_role(PileRole.FEEDER)
                if pile.discovered and not pile.is_full()
            ),
            None,
        )
        if from_pile and to_pile:
            return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)
        return None

    def _top_rank(self, pile, rank_lookup: dict[str, int]) -> int:
        top_card = pile.top_card_id()
        if top_card is None:
            return 10_000_000
        return rank_lookup.get(top_card, 10_000_000)

    def _find_scatter(self, rank_lookup: dict[str, int]):
        feeder = [pile for pile in self._piles_by_role(PileRole.FEEDER) if not pile.is_empty()]
        if not feeder:
            self.step = LegacyStep.GATHER
            return None
        from_pile = min(feeder, key=lambda pile: self._top_rank(pile, rank_lookup))
        from_rank = self._top_rank(from_pile, rank_lookup)
        target = next(
            (
                pile
                for pile in self._piles_by_role(PileRole.SORTING)
                if not pile.is_full()
                and (pile.is_empty() or self._top_rank(pile, rank_lookup) <= from_rank)
            ),
            None,
        )
        if target:
            return NextMove(from_pile=from_pile.pile_id, to_pile=target.pile_id)
        self.step = LegacyStep.GATHER
        return None

    def _find_gather(self, rank_lookup: dict[str, int]):
        sorting_non_empty = [pile for pile in self._piles_by_role(PileRole.SORTING) if not pile.is_empty()]
        if not sorting_non_empty:
            self.step = LegacyStep.FINISH
            return None
        from_pile = max(sorting_non_empty, key=lambda pile: self._top_rank(pile, rank_lookup))
        to_pile = next(
            (
                pile
                for pile in self._piles_by_role(PileRole.COLLECTION)
                if pile.discovered and not pile.is_full()
            ),
            None,
        )
        if to_pile is None:
            self.step = LegacyStep.FINISH
            return None
        return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)

    def plan_next(self, rank_lookup: dict[str, int]) -> NextMove | None:
        if self.step == LegacyStep.MOVE_FROM_FEED:
            return self._find_move_from_feed()
        if self.step == LegacyStep.INITIAL_COLLECTION:
            return self._find_initial_collection()
        if self.step == LegacyStep.SCATTER:
            return self._find_scatter(rank_lookup)
        if self.step == LegacyStep.GATHER:
            return self._find_gather(rank_lookup)
        return None

    def update_step(self):
        if self.step == LegacyStep.MOVE_FROM_FEED:
            feeders = self._piles_by_role(PileRole.FEEDER)
            if feeders and all(pile.discovered for pile in feeders):
                self.step = LegacyStep.INITIAL_COLLECTION
        elif self.step == LegacyStep.INITIAL_COLLECTION:
            sorting = self._piles_by_role(PileRole.SORTING)
            collection = self._piles_by_role(PileRole.COLLECTION)
            if self._all_empty(sorting) and self._all_empty(collection):
                self.step = LegacyStep.SCATTER
        elif self.step == LegacyStep.SCATTER:
            if not self._piles_by_role(PileRole.FEEDER):
                self.step = LegacyStep.GATHER
        elif self.step == LegacyStep.GATHER:
            sorting = self._piles_by_role(PileRole.SORTING)
            if self._all_empty(sorting):
                self.step = LegacyStep.FINISH
