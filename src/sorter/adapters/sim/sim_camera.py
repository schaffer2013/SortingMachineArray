from __future__ import annotations

from uuid import uuid4

from sorter.adapters.sim.sim_world import SimWorld
from sorter.domain.models import PileId
from sorter.ports.camera import Frame


class SimCameraAdapter:
    def __init__(self, world: SimWorld):
        self.world = world

    def capture_frame(self) -> Frame:
        return Frame(frame_id=f"frame-{uuid4().hex[:8]}", path=None, pile_id=None, metadata={"mode": "sim"})

    def capture_top_card(self, pile_id: PileId) -> Frame:
        card_name = self.world.top_card_name(pile_id)
        return Frame(
            frame_id=f"frame-{uuid4().hex[:8]}",
            path=None,
            pile_id=pile_id,
            metadata={"card_name": card_name, "mode": "sim"},
        )
