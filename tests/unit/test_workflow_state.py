from sorter.domain.enums import PileRole, WorkflowStep
from sorter.domain.machine_state import WorkflowState
from sorter.domain.models import MachineSnapshot, PileId, PileState


def test_swap_collection_and_feeder_roles_only_swaps_target_roles():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, discovered=True)
    collection = PileState(pile_id=PileId(1, 0), role=PileRole.COLLECTION, capacity=10, discovered=True)
    sorting = PileState(pile_id=PileId(2, 0), role=PileRole.SORTING, capacity=10, discovered=True)
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            collection.pile_id.as_key(): collection,
            sorting.pile_id.as_key(): sorting,
        }
    )
    workflow = WorkflowState(snapshot)

    workflow._swap_collection_and_feeder_roles()

    assert feeder.role == PileRole.COLLECTION
    assert collection.role == PileRole.FEEDER
    assert sorting.role == PileRole.SORTING


def test_set_pile_priorities_orders_each_role_group_by_distance_heuristic():
    feeder_best = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        x_mm=50.0,
        y_mm=0.0,
        discovered=True,
    )
    feeder_second = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.FEEDER,
        capacity=10,
        x_mm=0.0,
        y_mm=10.0,
        discovered=True,
    )
    collection_best = PileState(
        pile_id=PileId(0, 1),
        role=PileRole.COLLECTION,
        capacity=10,
        x_mm=50.0,
        y_mm=10.0,
        discovered=True,
    )
    collection_second = PileState(
        pile_id=PileId(1, 1),
        role=PileRole.COLLECTION,
        capacity=10,
        x_mm=0.0,
        y_mm=30.0,
        discovered=True,
    )
    sorting_best = PileState(
        pile_id=PileId(2, 0),
        role=PileRole.SORTING,
        capacity=10,
        x_mm=0.0,
        y_mm=0.0,
        discovered=True,
    )
    sorting_second = PileState(
        pile_id=PileId(3, 0),
        role=PileRole.SORTING,
        capacity=10,
        x_mm=100.0,
        y_mm=0.0,
        discovered=True,
    )

    snapshot = MachineSnapshot(
        piles={
            feeder_best.pile_id.as_key(): feeder_best,
            feeder_second.pile_id.as_key(): feeder_second,
            collection_best.pile_id.as_key(): collection_best,
            collection_second.pile_id.as_key(): collection_second,
            sorting_best.pile_id.as_key(): sorting_best,
            sorting_second.pile_id.as_key(): sorting_second,
        }
    )
    workflow = WorkflowState(snapshot)

    workflow._set_pile_priorities()

    assert [pile.pile_id for pile in workflow.sorted_feeder_collection_a] == [
        feeder_best.pile_id,
        feeder_second.pile_id,
    ]
    assert [pile.pile_id for pile in workflow.sorted_feeder_collection_b] == [
        collection_best.pile_id,
        collection_second.pile_id,
    ]
    assert [pile.pile_id for pile in workflow.sorted_sorting] == [
        sorting_best.pile_id,
        sorting_second.pile_id,
    ]


def test_move_from_feed_selects_expected_piles():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, card_stack=["a#1"], discovered=False)
    sorting = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, card_stack=[], discovered=True)
    snapshot = MachineSnapshot(piles={feeder.pile_id.as_key(): feeder, sorting.pile_id.as_key(): sorting})
    workflow = WorkflowState(snapshot)

    move = workflow.plan_next(rank_lookup={"a#1": 1})
    assert move is not None
    assert move.from_pile == feeder.pile_id
    assert move.to_pile == sorting.pile_id


def test_move_from_feed_waits_when_only_destination_is_unknown():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, card_stack=["a#1"], discovered=False)
    sorting = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, card_stack=[], discovered=False)
    snapshot = MachineSnapshot(piles={feeder.pile_id.as_key(): feeder, sorting.pile_id.as_key(): sorting})
    workflow = WorkflowState(snapshot)

    move = workflow.plan_next(rank_lookup={"a#1": 1})

    assert move is None


def test_move_from_feed_waits_when_destination_count_is_unknown():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, card_stack=["a#1"], discovered=False)
    sorting = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, card_stack=["seen-top"], discovered=False)
    sorting.mark_top_card_seen("Seen Top", source="scan", count_known=False)
    snapshot = MachineSnapshot(piles={feeder.pile_id.as_key(): feeder, sorting.pile_id.as_key(): sorting})
    workflow = WorkflowState(snapshot)

    move = workflow.plan_next(rank_lookup={"a#1": 1, "seen-top": 2})

    assert move is None


def test_step_transitions_to_initial_collection_when_feeders_discovered():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, card_stack=["a#1"], discovered=True)
    sorting = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, card_stack=[], discovered=True)
    snapshot = MachineSnapshot(piles={feeder.pile_id.as_key(): feeder, sorting.pile_id.as_key(): sorting})
    workflow = WorkflowState(snapshot)

    feeder.mark_empty_confirmed(source="test")
    workflow.update_step()
    assert workflow.step == WorkflowStep.INITIAL_COLLECTION


def test_step_does_not_transition_to_initial_collection_while_any_feeder_is_unknown():
    feeder_known_empty = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, discovered=True)
    feeder_unknown = PileState(pile_id=PileId(1, 0), role=PileRole.FEEDER, capacity=10, discovered=False)
    sorting = PileState(pile_id=PileId(2, 0), role=PileRole.SORTING, capacity=10, card_stack=[], discovered=True)
    snapshot = MachineSnapshot(
        piles={
            feeder_known_empty.pile_id.as_key(): feeder_known_empty,
            feeder_unknown.pile_id.as_key(): feeder_unknown,
            sorting.pile_id.as_key(): sorting,
        }
    )
    workflow = WorkflowState(snapshot)

    feeder_known_empty.mark_empty_confirmed(source="test")
    workflow.update_step()

    assert workflow.step == WorkflowStep.MOVE_FROM_FEED


def test_initial_collection_allows_returning_multiple_cards_to_known_feeder():
    feeder = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=["seen-card"],
        discovered=True,
    )
    collection = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=["bottom", "top"],
        discovered=True,
    )
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            collection.pile_id.as_key(): collection,
        }
    )
    workflow = WorkflowState(snapshot)
    workflow.step = WorkflowStep.INITIAL_COLLECTION

    move = workflow.plan_next(rank_lookup={"top": 1})

    assert move is not None
    assert move.from_pile == collection.pile_id
    assert move.to_pile == feeder.pile_id


def test_initial_collection_keeps_using_feeder_after_first_returned_card_updates_observation():
    feeder = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=[],
        discovered=True,
    )
    collection = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=["first", "second"],
        discovered=True,
    )
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            collection.pile_id.as_key(): collection,
        }
    )
    workflow = WorkflowState(snapshot)
    workflow.step = WorkflowStep.INITIAL_COLLECTION

    feeder.mark_empty_confirmed(source="verification")
    first_move = workflow.plan_next(rank_lookup={"second": 1})
    assert first_move is not None
    assert first_move.to_pile == feeder.pile_id

    collection.card_stack.pop()
    feeder.card_stack.append("second")
    feeder.mark_top_card_seen("second", source="placement_assumption")

    second_move = workflow.plan_next(rank_lookup={"first": 2, "second": 1})

    assert second_move is not None
    assert second_move.from_pile == collection.pile_id
    assert second_move.to_pile == feeder.pile_id


def test_rank_lookup_drives_scatter_and_gather_top_of_pile_choices():
    feeder_a = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=["fa-low", "fa-top"],
        discovered=True,
    )
    feeder_b = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=["fb-low", "fb-top"],
        discovered=True,
    )
    sorting_a = PileState(
        pile_id=PileId(2, 0),
        role=PileRole.SORTING,
        capacity=10,
        card_stack=["sa-base", "sa-top"],
        discovered=True,
    )
    sorting_b = PileState(
        pile_id=PileId(3, 0),
        role=PileRole.SORTING,
        capacity=10,
        card_stack=["sb-base", "sb-top"],
        discovered=True,
    )
    collection = PileState(
        pile_id=PileId(0, 1),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=[],
        discovered=True,
    )

    snapshot = MachineSnapshot(
        piles={
            feeder_a.pile_id.as_key(): feeder_a,
            feeder_b.pile_id.as_key(): feeder_b,
            sorting_a.pile_id.as_key(): sorting_a,
            sorting_b.pile_id.as_key(): sorting_b,
            collection.pile_id.as_key(): collection,
        }
    )
    rank_lookup = {
        "fa-top": 20,
        "fb-top": 5,
        "sa-top": 3,
        "sb-top": 8,
    }

    workflow = WorkflowState(snapshot)
    workflow._set_pile_priorities()
    workflow.step = WorkflowStep.SCATTER
    scatter_move = workflow.plan_next(rank_lookup)
    assert scatter_move is not None
    assert scatter_move.from_pile == feeder_b.pile_id
    assert scatter_move.to_pile == sorting_a.pile_id

    workflow.step = WorkflowStep.GATHER
    gather_move = workflow.plan_next(rank_lookup)
    assert gather_move is not None
    assert gather_move.from_pile == sorting_b.pile_id
    assert gather_move.to_pile == collection.pile_id


def test_scatter_ignores_sorting_destinations_with_unknown_count():
    feeder = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=["feed-top"],
        discovered=True,
    )
    sorting_unknown = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.SORTING,
        capacity=10,
        card_stack=["unknown-top"],
        discovered=False,
    )
    sorting_unknown.mark_top_card_seen("Unknown Top", source="scan", count_known=False)
    sorting_known = PileState(
        pile_id=PileId(2, 0),
        role=PileRole.SORTING,
        capacity=10,
        card_stack=[],
        discovered=True,
    )
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            sorting_unknown.pile_id.as_key(): sorting_unknown,
            sorting_known.pile_id.as_key(): sorting_known,
        }
    )
    workflow = WorkflowState(snapshot)
    workflow._set_pile_priorities()
    workflow.step = WorkflowStep.SCATTER

    move = workflow.plan_next(rank_lookup={"feed-top": 1, "unknown-top": 2})

    assert move is not None
    assert move.to_pile == sorting_known.pile_id


def test_gather_ignores_collection_destinations_with_unknown_count():
    feeder = PileState(
        pile_id=PileId(0, 0),
        role=PileRole.FEEDER,
        capacity=10,
        card_stack=[],
        discovered=True,
    )
    collection_unknown = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=["col-top"],
        discovered=False,
    )
    collection_unknown.mark_top_card_seen("Collection Top", source="scan", count_known=False)
    collection_known = PileState(
        pile_id=PileId(2, 0),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=[],
        discovered=True,
    )
    sorting = PileState(
        pile_id=PileId(3, 0),
        role=PileRole.SORTING,
        capacity=10,
        card_stack=["sort-top"],
        discovered=True,
    )
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            collection_unknown.pile_id.as_key(): collection_unknown,
            collection_known.pile_id.as_key(): collection_known,
            sorting.pile_id.as_key(): sorting,
        }
    )
    workflow = WorkflowState(snapshot)
    workflow._set_pile_priorities()
    workflow.step = WorkflowStep.GATHER

    move = workflow.plan_next(rank_lookup={"sort-top": 5, "col-top": 10})

    assert move is not None
    assert move.to_pile == collection_known.pile_id


def test_all_sorted_requires_known_counts_before_finishing():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, discovered=True)
    feeder.mark_empty_confirmed(source="test")
    collection = PileState(
        pile_id=PileId(1, 0),
        role=PileRole.COLLECTION,
        capacity=10,
        card_stack=["only-top"],
        discovered=False,
    )
    collection.mark_top_card_seen("Only Top", source="scan", count_known=False)
    snapshot = MachineSnapshot(
        piles={
            feeder.pile_id.as_key(): feeder,
            collection.pile_id.as_key(): collection,
        }
    )
    workflow = WorkflowState(snapshot)

    assert workflow._all_sorted(snapshot.piles.values(), rank_lookup={"only-top": 1}) is False
