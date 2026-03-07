from sorter.domain.enums import PileRole, LegacyStep
from sorter.domain.machine_state import LegacyWorkflowState
from sorter.domain.models import MachineSnapshot, PileId, PileState


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

    workflow.update_step()
    assert workflow.step == LegacyStep.INITIAL_COLLECTION


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
