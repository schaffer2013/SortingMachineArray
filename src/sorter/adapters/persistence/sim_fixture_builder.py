from __future__ import annotations

from pathlib import Path
import json

FEEDER_ROLE = "FEEDER"
_CLEAR_ROLES = {"FEEDER", "SORTING", "COLLECTION"}


def build_runtime_fixture(
    base_fixture_path: Path,
    shuffled_card_instance_ids: list[str],
    output_fixture_path: Path,
) -> Path:
    if not base_fixture_path.exists():
        raise FileNotFoundError(f"Base fixture not found: {base_fixture_path}")

    payload = json.loads(base_fixture_path.read_text(encoding="utf-8"))
    piles = payload.get("piles")
    if not isinstance(piles, list):
        raise ValueError("Fixture payload must include a 'piles' list")

    feeder_indexes: list[int] = []
    for index, pile in enumerate(piles):
        role = str(pile.get("role", "SORTING"))
        if role in _CLEAR_ROLES:
            pile["cards"] = []
        if role == FEEDER_ROLE:
            feeder_indexes.append(index)

    if not feeder_indexes:
        raise ValueError("Fixture must include at least one FEEDER pile")

    for card_index, card_id in enumerate(shuffled_card_instance_ids):
        pile_index = feeder_indexes[card_index % len(feeder_indexes)]
        piles[pile_index].setdefault("cards", []).append(card_id)

    payload["name"] = f"runtime_{payload.get('name', 'fixture')}"

    output_fixture_path.parent.mkdir(parents=True, exist_ok=True)
    output_fixture_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_fixture_path
