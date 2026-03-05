from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sorter.domain.models import PileId


@dataclass(frozen=True)
class Frame:
    frame_id: str
    path: str | None
    pile_id: PileId | None
    metadata: dict


class CameraPort(Protocol):
    def capture_frame(self) -> Frame: ...
    def capture_top_card(self, pile_id: PileId) -> Frame: ...
