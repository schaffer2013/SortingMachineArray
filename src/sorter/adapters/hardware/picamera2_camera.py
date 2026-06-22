from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from sorter.domain.models import PileId
from sorter.ports.camera import Frame


class PiCamera2Adapter:
    def __init__(self, *, capture_dir: Path, camera_id: str = "picamera2") -> None:
        self.capture_dir = capture_dir
        self.camera_id = camera_id
        self._camera = None

    def capture_frame(self) -> Frame:
        return self._capture(pile_id=None)

    def capture_top_card(self, pile_id: PileId) -> Frame:
        return self._capture(pile_id=pile_id)

    def _capture(self, pile_id: PileId | None) -> Frame:
        captured_at = datetime.now(UTC).isoformat()
        frame_id = f"frame-{uuid4().hex[:8]}"
        pile_suffix = "overview" if pile_id is None else pile_id.as_key().replace(",", "-")
        frame_path = self.capture_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{pile_suffix}-{frame_id}.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        self._camera_instance().capture_file(str(frame_path))
        return Frame(
            frame_id=frame_id,
            path=str(frame_path),
            pile_id=pile_id,
            metadata={"source": "picamera2", "camera_id": self.camera_id},
            captured_at_utc=captured_at,
            camera_id=self.camera_id,
            source_mode="hardware",
        )

    def _camera_instance(self):
        if self._camera is not None:
            return self._camera
        try:
            from picamera2 import Picamera2
        except Exception as exc:  # pragma: no cover - requires Raspberry Pi camera stack
            raise RuntimeError(
                "PiCamera2 hardware backend is unavailable. Install/enable picamera2 on the Raspberry Pi."
            ) from exc
        camera = Picamera2()
        camera.configure(camera.create_still_configuration())
        camera.start()
        self._camera = camera
        return camera
