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


def test_pick_invalidates_source_observation_until_next_capture():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "data/generated/runtime_fixture.json")
    pile_id = PileId(x_index=1, y_index=0)
    camera = SimCameraAdapter(world)

    camera.capture_top_card(pile_id)
    world.pick_from(pile_id)
    pile = world.snapshot.get_pile(pile_id)

    assert pile is not None
    assert pile.observation.state == PileObservationState.UNKNOWN
