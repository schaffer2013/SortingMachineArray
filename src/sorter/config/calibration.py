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
    pile_positions_mm: tuple[tuple[float, float], ...]
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
        raw_positions = data.get("pile_positions_mm", data.get("pile_xy_mm", {}))
        if isinstance(raw_positions, list):
            pile_positions = tuple(
                (float(value[0]), float(value[1]))
                for value in raw_positions
            )
        elif isinstance(raw_positions, dict):
            ordered_values = []
            for _, value in raw_positions.items():
                ordered_values.append((float(value[0]), float(value[1])))
            pile_positions = tuple(ordered_values)
        else:
            pile_positions = ()
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
            pile_positions_mm=pile_positions,
        )
