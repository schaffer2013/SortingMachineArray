from __future__ import annotations

from pathlib import Path

from sorter.adapters.sim.sim_camera import SimCameraAdapter
from sorter.adapters.sim.sim_world import SimWorld
from sorter.domain.enums import PileObservationState
from sorter.domain.models import PileId


def test_sim_camera_capture_updates_pile_observation_state():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=1, y_index=0)
    camera = SimCameraAdapter(world)

    frame = camera.capture_top_card(pile_id)
    pile = world.snapshot.get_pile(pile_id)

    assert frame.pile_id == pile_id
    assert pile is not None
    assert pile.observation.state == PileObservationState.TOP_CARD_SEEN
    assert pile.observation.frame_id == frame.frame_id
    assert pile.observation.top_card_name is not None


def test_all_piles_start_undiscovered_before_startup_scan():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=1, y_index=0)
    pile = world.snapshot.get_pile(pile_id)

    assert pile is not None
    assert pile.has_known_state() is False
    assert pile.has_known_count() is False
    assert pile.card_stack == []


def test_snapshot_does_not_expose_full_hidden_stack_for_undiscovered_feeder():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=0, y_index=0)
    pile = world.snapshot.get_pile(pile_id)

    assert pile is not None
    assert pile.card_stack == []
    assert len(world.hidden_piles[pile_id.as_key()]) > 0
    assert world.top_card_image_path(pile_id) is None


def test_capture_reveals_only_top_card_without_leaking_full_hidden_stack():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=0, y_index=0)
    camera = SimCameraAdapter(world)
    hidden_count = len(world.hidden_piles[pile_id.as_key()])

    frame = camera.capture_top_card(pile_id)
    pile = world.snapshot.get_pile(pile_id)

    assert frame.pile_id == pile_id
    assert pile is not None
    assert len(pile.card_stack) == 1
    assert pile.has_known_count() is False
    assert len(world.hidden_piles[pile_id.as_key()]) == hidden_count


def test_pick_reveals_next_source_top_card_immediately():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=1, y_index=0)
    camera = SimCameraAdapter(world)
    hidden_before = list(world.hidden_piles[pile_id.as_key()])

    camera.capture_top_card(pile_id)
    world.pick_from(pile_id)
    pile = world.snapshot.get_pile(pile_id)

    assert pile is not None
    assert pile.observation.state == PileObservationState.TOP_CARD_SEEN
    assert pile.top_card_id() == hidden_before[-2]
    assert pile.has_known_count() is False


def test_pick_uses_hidden_stack_even_when_snapshot_stack_is_initially_unknown():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=0, y_index=0)
    pile = world.snapshot.get_pile(pile_id)
    hidden_before = len(world.hidden_piles[pile_id.as_key()])

    assert pile is not None
    assert pile.card_stack == []

    world.pick_from(pile_id)

    assert world.held_card_id is not None
    assert len(world.hidden_piles[pile_id.as_key()]) == hidden_before - 1
    assert pile is not None
    if world.hidden_piles[pile_id.as_key()]:
        assert len(pile.card_stack) == 1
        assert pile.observation.state == PileObservationState.TOP_CARD_SEEN
        assert pile.has_known_count() is False
    else:
        assert pile.card_stack == []
        assert pile.observation.state == PileObservationState.EMPTY_CONFIRMED
        assert pile.has_known_count() is True
