from pathlib import Path
import json

from sorter.config.calibration import CalibrationProfile


def test_calibration_profile_reads_optional_probe_fields(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    path.write_text(
        json.dumps(
            {
                "safe_z_mm": 10.0,
                "pick_z_mm": 2.0,
                "place_z_mm": 3.0,
                "probe_enabled": True,
                "probe_retract_z_mm": 1.5,
                "probe_place_clearance_mm": 0.8,
                "probe_max_contact_z_mm": 7.5,
                "camera_offset_x_mm": 0.0,
                "camera_offset_y_mm": 0.0,
                "pile_positions_mm": [[100.0, 200.0]],
            }
        ),
        encoding="utf-8",
    )

    profile = CalibrationProfile.from_file(path)

    assert profile.probe_enabled is True
    assert profile.probe_retract_z_mm == 1.5
    assert profile.probe_place_clearance_mm == 0.8
    assert profile.probe_max_contact_z_mm == 7.5


def test_resolved_place_z_uses_probe_height_when_enabled() -> None:
    profile = CalibrationProfile(
        safe_z_mm=10.0,
        pick_z_mm=2.0,
        place_z_mm=3.0,
        camera_offset_x_mm=0.0,
        camera_offset_y_mm=0.0,
        pile_positions_mm=(),
        probe_enabled=True,
        probe_place_clearance_mm=1.25,
    )

    assert profile.resolved_place_z_mm(probed_top_z_mm=6.5) == 7.75


def test_resolved_place_z_falls_back_to_fixed_place_height() -> None:
    profile = CalibrationProfile(
        safe_z_mm=10.0,
        pick_z_mm=2.0,
        place_z_mm=3.0,
        camera_offset_x_mm=0.0,
        camera_offset_y_mm=0.0,
        pile_positions_mm=(),
    )

    assert profile.resolved_place_z_mm(probed_top_z_mm=6.5) == 3.0
