from sorter.domain.enums import PileRole, LegacyStep
from sorter.domain.machine_state import LegacyWorkflowState
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
    workflow = LegacyWorkflowState(snapshot)

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
    workflow = LegacyWorkflowState(snapshot)

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
    workflow = LegacyWorkflowState(snapshot)

    move = workflow.plan_next(rank_lookup={"a#1": 1})
    assert move is not None
    assert move.from_pile == feeder.pile_id
    assert move.to_pile == sorting.pile_id


def test_step_transitions_to_initial_collection_when_feeders_discovered():
    feeder = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, card_stack=["a#1"], discovered=True)
    sorting = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, card_stack=[], discovered=True)
    snapshot = MachineSnapshot(piles={feeder.pile_id.as_key(): feeder, sorting.pile_id.as_key(): sorting})
    workflow = LegacyWorkflowState(snapshot)

    feeder.mark_empty_confirmed(source="test")
    workflow.update_step()
    assert workflow.step == LegacyStep.INITIAL_COLLECTION


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
    workflow = LegacyWorkflowState(snapshot)
    workflow.step = LegacyStep.INITIAL_COLLECTION

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
    workflow = LegacyWorkflowState(snapshot)
    workflow.step = LegacyStep.INITIAL_COLLECTION

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

    workflow = LegacyWorkflowState(snapshot)
    workflow._set_pile_priorities()
    workflow.step = LegacyStep.SCATTER
    scatter_move = workflow.plan_next(rank_lookup)
    assert scatter_move is not None
    assert scatter_move.from_pile == feeder_b.pile_id
    assert scatter_move.to_pile == sorting_a.pile_id

    workflow.step = LegacyStep.GATHER
    gather_move = workflow.plan_next(rank_lookup)
    assert gather_move is not None
    assert gather_move.from_pile == sorting_b.pile_id
    assert gather_move.to_pile == collection.pile_id
