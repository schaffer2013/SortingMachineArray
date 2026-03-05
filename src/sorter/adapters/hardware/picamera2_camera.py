from __future__ import annotations

from uuid import uuid4

from sorter.domain.models import PileId
from sorter.ports.camera import Frame


class PiCamera2Adapter:
    def capture_frame(self) -> Frame:
        return Frame(frame_id=f"frame-{uuid4().hex[:8]}", path=None, pile_id=None, metadata={"source": "picamera2"})

    def capture_top_card(self, pile_id: PileId) -> Frame:
        return Frame(frame_id=f"frame-{uuid4().hex[:8]}", path=None, pile_id=pile_id, metadata={"source": "picamera2"})
