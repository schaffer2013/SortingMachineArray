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
            camera_offset_x_mm=float(data.get("camera_offset_x_mm", 0.0)),
            camera_offset_y_mm=float(data.get("camera_offset_y_mm", 0.0)),
            pile_xy_mm=pile_map,
        )
