from __future__ import annotations

from pathlib import Path
import json

from sorter.adapters.persistence.sim_image_sync import sync_simulated_images


def test_sync_extracts_cards_from_generated_fixture(tmp_path: Path) -> None:
    fixture = {
        "name": "runtime_fixture",
        "seed": 42,
        "grid": {"cols": 2, "rows": 1},
        "piles": [
            {
                "pile_id": {"x_index": 0, "y_index": 0},
                "role": "FEEDER",
                "cards": ["Lightning Bolt#1", "Island#1", "Lightning Bolt#2"],
            },
            {
                "pile_id": {"x_index": 1, "y_index": 0},
                "role": "SORTING",
                "cards": [],
            },
        ],
    }
    fixture_path = tmp_path / "runtime_fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    summary = sync_simulated_images(
        project_root=tmp_path,
        fixture_path=fixture_path,
        image_dir=tmp_path / "SimulatedCardImages",
        log_path=tmp_path / "logs" / "simulated_cards.log",
        sim_card_list_path=None,
        auto_fetch=False,
    )

    assert summary.total_cards == 2
    assert summary.missing_before == 2
    assert summary.downloaded == 0
    assert summary.missing_after == 2


def test_sync_uses_set_specific_and_default_paths(tmp_path: Path) -> None:
    fixture = {
        "name": "runtime_fixture",
        "seed": 42,
        "grid": {"cols": 2, "rows": 1},
        "card_set_by_instance_id": {"Lightning Bolt#1": "6ed"},
        "piles": [
            {
                "pile_id": {"x_index": 0, "y_index": 0},
                "role": "FEEDER",
                "cards": ["Lightning Bolt#1", "Counterspell#1"],
            }
        ],
    }
    fixture_path = tmp_path / "runtime_fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    image_dir = tmp_path / "SimulatedCardImages"
    (image_dir / "6ed").mkdir(parents=True, exist_ok=True)
    (image_dir / "lea").mkdir(parents=True, exist_ok=True)
    (image_dir / "6ed" / "Lightning_Bolt.jpg").write_bytes(b"set")
    (image_dir / "lea" / "Counterspell.jpg").write_bytes(b"fallback-any-set")

    summary = sync_simulated_images(
        project_root=tmp_path,
        fixture_path=fixture_path,
        image_dir=image_dir,
        log_path=tmp_path / "logs" / "simulated_cards.log",
        sim_card_list_path=None,
        auto_fetch=False,
    )

    assert summary.total_cards == 2
    assert summary.missing_before == 0
    assert summary.missing_after == 0
