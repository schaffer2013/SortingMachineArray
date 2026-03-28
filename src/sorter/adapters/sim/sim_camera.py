from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sorter.adapters.sim.sim_world import SimWorld
from sorter.domain.models import PileId
from sorter.ports.camera import Frame


class SimCameraAdapter:
    def __init__(self, world: SimWorld):
        self.world = world

    def capture_frame(self) -> Frame:
        return Frame(
            frame_id=f"frame-{uuid4().hex[:8]}",
            path=None,
            pile_id=None,
            metadata={"mode": "sim"},
            captured_at_utc=datetime.now(UTC).isoformat(),
            camera_id="sim_topdown",
            source_mode="sim",
        )

    def capture_top_card(self, pile_id: PileId) -> Frame:
        frame_id = f"frame-{uuid4().hex[:8]}"
        card_name = self.world.peek_top_card_name(pile_id)
        image_path = self.world.top_card_image_path(pile_id)
        top_id = self.world.peek_top_card_id(pile_id)
        card_meta = self.world.card_by_id.get(top_id) if top_id is not None else None
        return Frame(
            frame_id=frame_id,
            path=image_path,
            pile_id=pile_id,
            metadata={
                "card_name": card_name,
                "mode": "sim",
                "image_path": image_path,
                "card_id": top_id,
                "scryfall_id": card_meta.scryfall_id if card_meta is not None else None,
                "oracle_id": card_meta.oracle_id if card_meta is not None else None,
            },
            captured_at_utc=datetime.now(UTC).isoformat(),
            camera_id="sim_topdown",
            source_mode="sim",
        )
