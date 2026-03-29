from __future__ import annotations

from pathlib import Path
import json

from sorter.adapters.persistence.sim_fixture_builder import build_runtime_fixture


def test_build_runtime_fixture_distributes_cards_round_robin_across_feeders(tmp_path: Path) -> None:
    base_fixture = {
        "name": "base",
        "seed": 42,
        "grid": {"cols": 2, "rows": 2},
        "piles": [
            {
                "pile_id": {"x_index": 0, "y_index": 0},
                "role": "FEEDER",
                "cards": ["Old#1"],
                "capacity": 85,
                "discovered": False,
                "x_mm": 100,
                "y_mm": 100,
            },
            {
                "pile_id": {"x_index": 1, "y_index": 0},
                "role": "FEEDER",
                "cards": ["Old#2"],
                "capacity": 85,
                "discovered": False,
                "x_mm": 200,
                "y_mm": 100,
            },
            {
                "pile_id": {"x_index": 0, "y_index": 1},
                "role": "SORTING",
                "cards": ["Old#3"],
                "capacity": 85,
                "discovered": True,
                "x_mm": 100,
                "y_mm": 200,
            },
            {
                "pile_id": {"x_index": 1, "y_index": 1},
                "role": "COLLECTION",
                "cards": ["Old#4"],
                "capacity": 85,
                "discovered": True,
                "x_mm": 200,
                "y_mm": 200,
            },
        ],
        "faults": [],
    }

    base_path = tmp_path / "base_fixture.json"
    output_path = tmp_path / "generated" / "runtime_fixture.json"
    base_path.write_text(json.dumps(base_fixture), encoding="utf-8")

    result_path = build_runtime_fixture(
        base_fixture_path=base_path,
        shuffled_card_instance_ids=["A#1", "B#1", "C#1", "D#1", "E#1"],
        output_fixture_path=output_path,
        card_set_by_instance_id={"A#1": "6ed", "C#1": "lea"},
    )

    generated = json.loads(result_path.read_text(encoding="utf-8"))
    piles = generated["piles"]

    assert piles[0]["cards"] == ["A#1", "C#1", "E#1"]
    assert piles[1]["cards"] == ["B#1", "D#1"]
    assert piles[2]["cards"] == []
    assert piles[3]["cards"] == []
    assert piles[0]["x_mm"] == 100
    assert piles[1]["y_mm"] == 100
    assert generated["name"] == "runtime_base"
    assert generated["card_set_by_instance_id"] == {"A#1": "6ed", "C#1": "lea"}


def test_build_runtime_fixture_falls_back_to_all_piles_when_no_feeders_exist(tmp_path: Path) -> None:
    base_fixture = {
        "name": "base",
        "seed": 42,
        "grid": {"cols": 2, "rows": 1},
        "piles": [
            {
                "pile_id": {"x_index": 0, "y_index": 0},
                "role": "SORTING",
                "cards": ["Old#1"],
                "capacity": 85,
                "discovered": True,
                "x_mm": 100,
                "y_mm": 100,
            },
            {
                "pile_id": {"x_index": 1, "y_index": 0},
                "role": "COLLECTION",
                "cards": ["Old#2"],
                "capacity": 85,
                "discovered": True,
                "x_mm": 200,
                "y_mm": 100,
            },
        ],
        "faults": [],
    }

    base_path = tmp_path / "base_fixture.json"
    output_path = tmp_path / "generated" / "runtime_fixture.json"
    base_path.write_text(json.dumps(base_fixture), encoding="utf-8")

    result_path = build_runtime_fixture(
        base_fixture_path=base_path,
        shuffled_card_instance_ids=["A#1", "B#1", "C#1"],
        output_fixture_path=output_path,
    )

    generated = json.loads(result_path.read_text(encoding="utf-8"))
    piles = generated["piles"]

    assert piles[0]["cards"] == ["A#1", "C#1"]
    assert piles[1]["cards"] == ["B#1"]
