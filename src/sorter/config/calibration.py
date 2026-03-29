from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sorter.config.settings import load_json


@dataclass(frozen=True)
class CalibrationProfile:
    safe_z_mm: float
    pick_z_mm: float
    place_z_mm: float
    camera_offset_x_mm: float
    camera_offset_y_mm: float
    pile_xy_mm: dict[str, tuple[float, float]]
    probe_enabled: bool = False
    probe_retract_z_mm: float = 2.0
    probe_place_clearance_mm: float = 1.0
    probe_max_contact_z_mm: float | None = None

    def resolved_place_z_mm(self, *, probed_top_z_mm: float | None = None) -> float:
        if self.probe_enabled and probed_top_z_mm is not None:
            return float(probed_top_z_mm) + self.probe_place_clearance_mm
        return self.place_z_mm

    @staticmethod
    def from_file(path: Path) -> "CalibrationProfile":
        data = load_json(path)
        pile_map = {
            key: (float(value[0]), float(value[1]))
            for key, value in data.get("pile_xy_mm", {}).items()
        }
        return CalibrationProfile(
            safe_z_mm=float(data["safe_z_mm"]),
            pick_z_mm=float(data["pick_z_mm"]),
            place_z_mm=float(data["place_z_mm"]),
            probe_enabled=bool(data.get("probe_enabled", False)),
            probe_retract_z_mm=float(data.get("probe_retract_z_mm", 2.0)),
            probe_place_clearance_mm=float(data.get("probe_place_clearance_mm", 1.0)),
            probe_max_contact_z_mm=(
                float(data["probe_max_contact_z_mm"])
                if data.get("probe_max_contact_z_mm") is not None
                else None
            ),
            camera_offset_x_mm=float(data.get("camera_offset_x_mm", 0.0)),
            camera_offset_y_mm=float(data.get("camera_offset_y_mm", 0.0)),
            pile_xy_mm=pile_map,
        )
