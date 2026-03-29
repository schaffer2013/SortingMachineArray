from __future__ import annotations

from dataclasses import dataclass
import logging

from sorter.domain.enums import PileRole, WorkflowStep
from sorter.domain.models import MachineSnapshot, PileId


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NextMove:
    from_pile: PileId
    to_pile: PileId


class WorkflowState:
    def __init__(self, snapshot: MachineSnapshot):
        self.snapshot = snapshot
        self.step = WorkflowStep.MOVE_FROM_FEED
        self.priority_feeder_collection_a = None
        self.priority_feeder_collection_b = None
        self.priority_sorting = None
        logger.debug("workflow initialized: step=%s piles=%s", self.step.name, len(snapshot.piles))

    def _set_step(self, new_step: WorkflowStep, reason: str) -> None:
        if self.step == new_step:
            return
        old_step = self.step
        self.step = new_step
        logger.debug("workflow step transition: %s -> %s reason=%s", old_step.name, new_step.name, reason)

    def _piles_by_role(self, *roles: PileRole):
        role_set = set(roles)
        return [pile for pile in self.snapshot.piles.values() if pile.role in role_set]

    def _swap_collection_and_feeder_roles(self) -> None:
        role_swaps: dict[str, PileRole] = {}
        for pile in self.snapshot.piles.values():
            if pile.role == PileRole.COLLECTION:
                role_swaps[pile.pile_id.as_key()] = PileRole.FEEDER
            elif pile.role == PileRole.FEEDER:
                role_swaps[pile.pile_id.as_key()] = PileRole.COLLECTION

        for pile_key, new_role in role_swaps.items():
            self.snapshot.piles[pile_key].role = new_role

    def _all_empty(self, piles) -> bool:
        return all(pile.is_empty() for pile in piles)

    def _can_accept_move_from_feed(self, pile) -> bool:
        if pile.role == PileRole.FEEDER:
            return False
        if not pile.has_known_count():
            return True
        return not pile.is_full()

    def _all_sorted(self, piles, rank_lookup: dict[str, int]) -> bool:
        # If all piles are discovered. 
        # If all feeder piles are empty. 
        # If all sorting piles are empty.
        # If all collection piles are fully sorted in the correct order (not inverse). 
        # (Each collection pile is fully sorted AND the bottom card of each collection pile is higher rank than the top card of the previous collection pile, if any.)
        if not all(pile.has_known_state() and pile.has_known_count() for pile in piles):
            return False
        feeder_piles = [pile for pile in piles if pile.role == PileRole.FEEDER]
        if any(not pile.is_empty() for pile in feeder_piles):
            return False
        sorting_piles = [pile for pile in piles if pile.role == PileRole.SORTING]
        if any(not pile.is_empty() for pile in sorting_piles):
            return False
        collection_piles = [pile for pile in piles if pile.role == PileRole.COLLECTION]
        if len(collection_piles) == 1:
            return self._single_pile_sorted(collection_piles[0], rank_lookup)
        for pile in collection_piles:
            if not self._single_pile_sorted(pile, rank_lookup):
                return False
        for i in range(len(collection_piles) - 1):
            bottom_card = collection_piles[i].bottom_card_id()
            top_card = collection_piles[i + 1].top_card_id()
            if bottom_card is None or top_card is None:
                return False
            if rank_lookup.get(bottom_card, 10_000_000) >= rank_lookup.get(top_card, 10_000_000):
                return False
        return True
    
    def _single_pile_sorted(self, pile, rank_lookup: dict[str, int]) -> bool:
        # If the pile is empty, it's sorted.
        if pile.is_empty() or len(pile.card_stack) == 1:
            return True
        # If any card is higher rank than the card below it, it's not sorted.
        for i in range(len(pile.card_stack) - 1):
            top_card = pile.card_stack[i]
            below_card = pile.card_stack[i + 1]
            if rank_lookup.get(top_card, 10_000_000) < rank_lookup.get(below_card, 10_000_000):
                return False
        return True

    def _find_move_from_feed(self):
        from_pile = next(
            (
                pile
                for pile in self._piles_by_role(PileRole.FEEDER)
                if not pile.is_empty_confirmed()
            ),
            None,
        )
        to_pile = next(
            (
                pile
                for pile in self.snapshot.piles.values()
                if self._can_accept_move_from_feed(pile)
            ),
            None,
        )
        if from_pile and to_pile:
            logger.debug(
                "planned MOVE_FROM_FEED move: from=%s to=%s",
                from_pile.pile_id.as_key(),
                to_pile.pile_id.as_key(),
            )
            return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)
        logger.debug("no MOVE_FROM_FEED move available")
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
                if pile.has_known_count() and not pile.is_full()
            ),
            None,
        )
        if from_pile and to_pile:
            logger.debug(
                "planned INITIAL_COLLECTION move: from=%s to=%s",
                from_pile.pile_id.as_key(),
                to_pile.pile_id.as_key(),
            )
            return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)
        logger.debug("no INITIAL_COLLECTION move available")
        return None

    def _top_rank(self, pile, rank_lookup: dict[str, int]) -> int:
        top_card = pile.top_card_id()
        if top_card is None:
            return 10_000_000
        return rank_lookup.get(top_card, 10_000_000)

    def _find_scatter(self, rank_lookup: dict[str, int]):
        if self.priority_sorting is None:
            raise RuntimeError("Workflow scatter planning requested before pile priorities were set")
        feeder = [pile for pile in self._piles_by_role(PileRole.FEEDER) if not pile.is_empty()]
        if not feeder:
            self._set_step(WorkflowStep.GATHER, "all feeder piles empty during scatter")
            return None
        from_pile = min(feeder, key=lambda pile: self._top_rank(pile, rank_lookup))
        from_rank = self._top_rank(from_pile, rank_lookup)
        target = None
        for sorting_pile in self.priority_sorting:
            if (
                sorting_pile.has_known_state()
                and sorting_pile.has_known_count()
                and not sorting_pile.is_full()
                and (sorting_pile.is_empty() or self._top_rank(sorting_pile, rank_lookup) <= from_rank)
            ):
                target = sorting_pile
                break
        if target:
            logger.debug(
                "planned SCATTER move: from=%s rank=%s to=%s",
                from_pile.pile_id.as_key(),
                from_rank,
                target.pile_id.as_key(),
            )
            return NextMove(from_pile=from_pile.pile_id, to_pile=target.pile_id)
        self._set_step(WorkflowStep.GATHER, "no sorting target available during scatter")
        logger.debug("no SCATTER move available")
        return None

    def _find_gather(self, rank_lookup: dict[str, int]):
        if self.priority_feeder_collection_a is None or self.priority_feeder_collection_b is None:
            raise RuntimeError("Workflow gather planning requested before pile priorities were set")
        sorting_non_empty = [pile for pile in self._piles_by_role(PileRole.SORTING) if not pile.is_empty()]
        if self._all_sorted(self.snapshot.piles.values(), rank_lookup):
            self._set_step(WorkflowStep.FINISH, "collection piles fully sorted")
            return None
        if not sorting_non_empty:
            feed_empty = all(pile.is_empty() for pile in self._piles_by_role(PileRole.FEEDER))
            if feed_empty:
                self._swap_collection_and_feeder_roles()
            self._set_step(WorkflowStep.SCATTER, "all sorting piles empty during gather")
            return None
        from_pile = max(sorting_non_empty, key=lambda pile: self._top_rank(pile, rank_lookup))
        # TODO: If we have multiple collection piles, we may want to swap the priority of them to better riffle sort them.
        # Effectively, this would gather into a rotating priority of collection piles, to better interleave cards when gathering from multiple sorting piles with different ranks at the top.
        priority_collection = self.priority_feeder_collection_a if self.priority_feeder_collection_a[0].role == PileRole.COLLECTION else self.priority_feeder_collection_b
        to_pile = next(
            (
                pile
                for pile in priority_collection
                if pile.has_known_count() and not pile.is_full()
            ),
            None,
        )
        if to_pile is None:
            self._set_step(WorkflowStep.FINISH, "no collection destination available")
            raise RuntimeError("no collection destination available during gather")
        logger.debug(
            "planned GATHER move: from=%s to=%s",
            from_pile.pile_id.as_key(),
            to_pile.pile_id.as_key(),
        )
        return NextMove(from_pile=from_pile.pile_id, to_pile=to_pile.pile_id)

    def _set_pile_priorities(self):
        # Create a dict or list of piles to be iterated through in a specific order in the move planning functions, 
        # to prefer certain piles over others when multiple are valid targets.
        # a and b are here because they get swapped, but they'll always be the same role as each other
        self.priority_feeder_collection_a = self._piles_by_role(PileRole.FEEDER)
        self.priority_feeder_collection_b = self._piles_by_role(PileRole.COLLECTION)
        self.priority_sorting = self._piles_by_role(PileRole.SORTING)

        # Create a priority order for piles to prefer certain piles over others when multiple are valid targets.
        # For feeders and gather targets, prefer piles that have the lowest cumulative distance
        # to all sorting piles, to encourage more efficient paths.
        # For scatter targets, prefer piles that have the lowest cumulative distance to feeder and collection piles,
        # to encourage more efficient paths and keep piles more spatially grouped.
        
        # Create a temp dict of pile_key to priority value, then assign to piles after to avoid issues with mutating piles while iterating them.
        temp_priorities = {}
        for pile in self.priority_feeder_collection_a:
            temp_priorities[pile.pile_id.as_key()] = sum(
                pile.distance_from(other) for other in self.priority_sorting
            )
        for pile in self.priority_feeder_collection_b:
            temp_priorities[pile.pile_id.as_key()] = sum(
                pile.distance_from(other) for other in self.priority_sorting
            )
        for pile in self.priority_sorting:
            feeder_and_collection = self._piles_by_role(PileRole.FEEDER, PileRole.COLLECTION)
            temp_priorities[pile.pile_id.as_key()] = sum(
                pile.distance_from(fc) for fc in feeder_and_collection
            )

        # Now sort piles by their priority value without mutating them while iterating, and assign the final priority order to the piles.
        self.sorted_feeder_collection_a = sorted(self.priority_feeder_collection_a, key=lambda pile: temp_priorities[pile.pile_id.as_key()])
        self.sorted_feeder_collection_b = sorted(self.priority_feeder_collection_b, key=lambda pile: temp_priorities[pile.pile_id.as_key()])
        self.sorted_sorting = sorted(self.priority_sorting, key=lambda pile: temp_priorities[pile.pile_id.as_key()])
        return True

    def plan_next(self, rank_lookup: dict[str, int]) -> NextMove | None:
        if self.step == WorkflowStep.MOVE_FROM_FEED:
            return self._find_move_from_feed()
        if self.step == WorkflowStep.INITIAL_COLLECTION:
            return self._find_initial_collection()
        if self.step == WorkflowStep.SCATTER:
            return self._find_scatter(rank_lookup)
        if self.step == WorkflowStep.GATHER:
            return self._find_gather(rank_lookup)
        return None

    def update_step(self):
        if self.step == WorkflowStep.MOVE_FROM_FEED:
            feeders = self._piles_by_role(PileRole.FEEDER)
            if feeders and all(pile.is_empty_confirmed() for pile in feeders):
                self._set_step(WorkflowStep.INITIAL_COLLECTION, "all feeder piles discovered")
        elif self.step == WorkflowStep.INITIAL_COLLECTION:
            sorting = self._piles_by_role(PileRole.SORTING)
            collection = self._piles_by_role(PileRole.COLLECTION)
            if self._all_empty(sorting) and self._all_empty(collection):
                self._set_pile_priorities()
                self._set_step(WorkflowStep.SCATTER, "sorting and collection piles empty")
        elif self.step == WorkflowStep.SCATTER:
            if not self._piles_by_role(PileRole.FEEDER):
                self._set_step(WorkflowStep.GATHER, "no feeder piles configured")
        elif self.step == WorkflowStep.GATHER:
            sorting = self._piles_by_role(PileRole.SORTING)
            if self._all_empty(sorting):
                self._set_step(WorkflowStep.FINISH, "sorting piles emptied")
