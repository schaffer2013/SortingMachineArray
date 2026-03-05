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
