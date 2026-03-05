from __future__ import annotations

from pathlib import Path

from sorter.adapters.persistence.scenario_loader import (
    distribute_cards_to_piles,
    write_scenario_fixture,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    card_names = [path.stem.replace("_", " ") for path in (root / "SimulatedCardImages").glob("*.jpg")]
    card_ids = [f"{name}#{index + 1}" for index, name in enumerate(card_names)]
    piles = distribute_cards_to_piles(card_ids, num_piles=20, num_empty_piles=5, seed=42)

    payload = {
        "name": "generated_fixture",
        "seed": 42,
        "grid": {"cols": 5, "rows": 4},
        "piles": [],
        "faults": [],
    }

    for index, stack in enumerate(piles):
        x_index = index % 5
        y_index = index // 5
        role = "SORTING"
        if y_index == 0 and x_index in {0, 1, 2}:
            role = "FEEDER"
        elif y_index == 3 and x_index in {0, 1, 2}:
            role = "COLLECTION"
        payload["piles"].append(
            {
                "pile_id": {"x_index": x_index, "y_index": y_index},
                "role": role,
                "cards": stack,
                "capacity": 85,
                "discovered": role != "FEEDER",
                "x_mm": 100 + x_index * 100,
                "y_mm": 100 + y_index * 100,
            }
        )

    out_path = root / "scenarios/fixtures/generated_fixture.json"
    write_scenario_fixture(out_path, payload)
    print({"fixture": str(out_path), "piles": len(payload["piles"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
