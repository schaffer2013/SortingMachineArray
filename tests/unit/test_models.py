import math

from sorter.domain.enums import PileObservationState, PileRole
from sorter.domain.models import CardMeta, PileId, PileState


def test_pile_state_distance_from_uses_xy_mm_coordinates():
    left = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, x_mm=0.0, y_mm=0.0)
    right = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, x_mm=3.0, y_mm=4.0)

    assert math.isclose(left.distance_from(right), 5.0)
    assert math.isclose(right.distance_from(left), 5.0)


def test_card_meta_can_store_scryfall_id():
    meta = CardMeta(name="Snapcaster Mage", scryfall_id="11111111-2222-3333-4444-555555555555")

    assert meta.scryfall_id == "11111111-2222-3333-4444-555555555555"


def test_pile_state_observation_transitions_between_unknown_top_seen_and_empty_confirmed():
    pile = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10)

    assert pile.observation.state == PileObservationState.UNKNOWN
    assert pile.has_known_state() is False

    pile.mark_top_card_seen("Snapcaster Mage", confidence=0.9, source="sim_camera", frame_id="frame-1")
    assert pile.observation.state == PileObservationState.TOP_CARD_SEEN
    assert pile.observation.top_card_name == "Snapcaster Mage"
    assert pile.has_observed_top_card() is True
    assert pile.discovered is True

    pile.mark_empty_confirmed(source="sim_camera", frame_id="frame-2")
    assert pile.observation.state == PileObservationState.EMPTY_CONFIRMED
    assert pile.is_empty_confirmed() is True

    pile.mark_unknown()
    assert pile.observation.state == PileObservationState.UNKNOWN
    assert pile.discovered is False
