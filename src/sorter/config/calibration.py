from __future__ import annotations

from dataclasses import dataclass, replace
import json
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
    camera_offset_z_mm: float = 0.0
    min_xy_travel_z_mm: float = 0.0
    probe_enabled: bool = False
    probe_retract_z_mm: float = 2.0
    probe_place_clearance_mm: float = 1.0
    probe_max_contact_z_mm: float | None = None

    def resolved_place_z_mm(self, *, probed_top_z_mm: float | None = None) -> float:
        if self.probe_enabled and probed_top_z_mm is not None:
            return float(probed_top_z_mm) + self.probe_place_clearance_mm
        return self.place_z_mm

    def camera_baseline_xy_for_vacuum_target(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Return the vacuum-baseline XY pose that places the camera over a target."""
        return (
            float(x_mm) - self.camera_offset_x_mm,
            float(y_mm) - self.camera_offset_y_mm,
        )

    def camera_z_for_vacuum_z(self, z_mm: float) -> float:
        return float(z_mm) + self.camera_offset_z_mm

    def xy_travel_z_mm(self) -> float:
        return max(self.safe_z_mm, self.min_xy_travel_z_mm)

    def assert_xy_travel_safe(self, current_vac_z_mm: float) -> None:
        if float(current_vac_z_mm) < self.min_xy_travel_z_mm:
            raise ValueError(
                "XY travel blocked: vacuum Z "
                f"{float(current_vac_z_mm):.2f} mm is below the configured "
                f"minimum {self.min_xy_travel_z_mm:.2f} mm"
            )

    def with_updates(self, **updates: float) -> "CalibrationProfile":
        numeric_fields = {
            "safe_z_mm",
            "pick_z_mm",
            "place_z_mm",
            "camera_offset_x_mm",
            "camera_offset_y_mm",
            "camera_offset_z_mm",
            "min_xy_travel_z_mm",
            "probe_retract_z_mm",
            "probe_place_clearance_mm",
            "probe_max_contact_z_mm",
        }
        clean_updates = {
            key: None if value is None else float(value)
            for key, value in updates.items()
            if key in numeric_fields
        }
        return replace(self, **clean_updates)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "safe_z_mm": self.safe_z_mm,
            "pick_z_mm": self.pick_z_mm,
            "place_z_mm": self.place_z_mm,
            "probe_enabled": self.probe_enabled,
            "probe_retract_z_mm": self.probe_retract_z_mm,
            "probe_place_clearance_mm": self.probe_place_clearance_mm,
            "probe_max_contact_z_mm": self.probe_max_contact_z_mm,
            "camera_offset_x_mm": self.camera_offset_x_mm,
            "camera_offset_y_mm": self.camera_offset_y_mm,
            "camera_offset_z_mm": self.camera_offset_z_mm,
            "min_xy_travel_z_mm": self.min_xy_travel_z_mm,
            "pile_positions_mm": [[x_mm, y_mm] for x_mm, y_mm in self.pile_positions_mm],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.to_json_dict(), handle, indent=2)
            handle.write("\n")

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
            camera_offset_z_mm=float(data.get("camera_offset_z_mm", 0.0)),
            min_xy_travel_z_mm=float(data.get("min_xy_travel_z_mm", data["safe_z_mm"])),
            pile_positions_mm=pile_positions,
        )
