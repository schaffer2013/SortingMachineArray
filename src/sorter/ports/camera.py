from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sorter.domain.models import PileId


@dataclass(frozen=True)
class Frame:
    frame_id: str
    path: str | None
    pile_id: PileId | None
    metadata: dict = field(default_factory=dict)
    captured_at_utc: str | None = None
    camera_id: str | None = None
    source_mode: str | None = None


class CameraPort(Protocol):
    def capture_frame(self) -> Frame: ...
    def capture_top_card(self, pile_id: PileId) -> Frame: ...
